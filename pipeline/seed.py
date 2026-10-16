"""브이월드에서 직접 받은 파일 → data/seed/{시군구}/{법정동}_{parcels|zones|owners}.json.gz (+ dongs.json.gz)
fetch.py는 seed가 있으면 브이월드 API 대신 이걸 씀 (해외 IP 차단 우회).
  python -m pipeline.seed 11650 연속지적도.zip 용도지역.zip 토지소유정보.csv
- shp(zip 또는 .shp): PNU 컬럼 있으면 지적도, 없으면 용도지역으로 판단. 좌표계는 .prj로 읽어 WGS84 변환
- csv: 토지소유정보 (cp949/utf-8 자동)"""
import sys, io, csv, gzip, json, re, zipfile
from collections import defaultdict
from pathlib import Path
import numpy as np
import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely import STRtree, set_precision, transform
from .common import ROOT

SEED = ROOT / 'data' / 'seed'
OWN = {'pnu': ['고유번호', 'pnu'], 'lndcgrCodeNm': ['지목명', '지목'], 'lndpclAr': ['토지면적', '면적'],
       'pblntfPclnd': ['공시지가'], 'posesnSeCodeNm': ['소유구분명', '소유구분'], 'ownshipChgDe': ['소유권변동일자', '변동일자'],
       'cnrsPsnCo': ['공유인수'], 'cnrsPsnSn': ['공유인일련번호', '일련번호'], 'buldDongNm': ['건물동명', '동명'],
       'buldHoNm': ['건물호명', '호명'], 'ldCodeNm': ['법정동명']}
norm = lambda s: re.sub(r'[\s()㎡_\-]', '', s).lower()


def read_shp(path):
    """→ (필드명 목록, [(shapely geom WGS84, props)])"""
    if str(path).endswith('.zip'):
        z = zipfile.ZipFile(path)
        base = next(n[:-4] for n in z.namelist() if n.lower().endswith('.shp'))
        part = lambda ext: io.BytesIO(z.read(next(n for n in z.namelist() if n.lower() == (base + ext).lower())))
        prj = z.read(next(n for n in z.namelist() if n.lower() == (base + '.prj').lower())).decode('latin1')
        r = shapefile.Reader(shp=part('.shp'), dbf=part('.dbf'), shx=part('.shx'), encoding='cp949')
    else:
        r = shapefile.Reader(str(path), encoding='cp949')
        prj = Path(path).with_suffix('.prj').read_text(encoding='latin1')
    t = Transformer.from_crs(CRS.from_wkt(prj), 4326, always_xy=True)
    tf = lambda xy: np.column_stack(t.transform(xy[:, 0], xy[:, 1]))
    names = [f[0] for f in r.fields[1:]]
    return names, [(transform(shape(s.shape.__geo_interface__), tf), dict(zip(names, s.record))) for s in r.iterShapeRecords()]


def read_owners(path, sgg):
    raw = Path(path).read_bytes()
    text = next(raw.decode(e) for e in ('utf-8-sig', 'cp949') if not _bad(raw, e))
    rd = csv.DictReader(io.StringIO(text))
    loose = lambda c, h: norm(c) in norm(h) and ('법정' in c or '법정' not in h)  # '동명'이 '법정동명'에 걸리지 않게
    col = {k: next((h for h in rd.fieldnames for c in cs if norm(c) == norm(h)), None)
           or next((h for h in rd.fieldnames for c in cs if loose(c, h)), None) for k, cs in OWN.items()}
    print('소유정보 컬럼 매핑:', col, flush=True)
    if not col['pnu']: sys.exit(f'고유번호 컬럼을 못 찾음: {rd.fieldnames}')
    return [{k: (r[h] or '').strip() for k, h in col.items() if h} for r in rd if r[col['pnu']].startswith(sgg)]


def _bad(raw, enc):
    try: raw.decode(enc); return False
    except UnicodeDecodeError: return True


def save(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()))


def main(sgg, *files):
    parcels, zones, owners = [], [], []
    for f in files:
        if f.lower().endswith('.csv'):
            owners += read_owners(f, sgg)
            continue
        names, rows = read_shp(f)
        if any(n.upper() == 'PNU' for n in names):
            k = {n.upper(): n for n in names}
            parcels += [(g, str(p[k['PNU']]), str(p.get(k.get('JIBUN', ''), ''))) for g, p in rows if str(p[k['PNU']]).startswith(sgg)]
        else:
            nm = next((n for n in names if n.upper() in ('DGM_NM', 'UNAME', 'PRPOS_AREA_DSTRC_NM')), names[-1])
            zones += [(g, str(p[nm])) for g, p in rows]
        print(f, len(rows), names, flush=True)

    by = defaultdict(list)
    for g, pnu, jb in parcels: by[pnu[:10]].append((g, pnu, jb))
    own = defaultdict(list)
    for r in owners: own[r['pnu'][:10]].append(r)
    nm = {r['pnu'][:10]: r.get('ldCodeNm', '') for r in owners}
    tree = STRtree([g for g, _ in zones]) if zones else None
    d, dongs = SEED / sgg, []
    for p10, ps in sorted(by.items()):
        u = unary_union([g.buffer(0) for g, _, _ in ps])
        dongs.append(dict(type='Feature', geometry=mapping(set_precision(u.simplify(1e-5), 1e-6)),
                          properties=dict(emd_cd=p10[:8], full_nm=nm.get(p10, ''), emd_kor_nm=nm.get(p10, '').split(' ')[-1])))
        save(d / f'{p10}_parcels.json.gz', [dict(type='Feature', geometry=mapping(set_precision(g, 1e-7)), properties=dict(pnu=pnu, jibun=jb))
                                            for g, pnu, jb in ps])
        zi = tree.query(u, predicate='intersects') if tree else []
        save(d / f'{p10}_zones.json.gz', [dict(type='Feature', geometry=mapping(set_precision(zones[i][0].intersection(u.envelope), 1e-6)),
                                               properties=dict(uname=zones[i][1])) for i in zi])
        if owners: save(d / f'{p10}_owners.json.gz', own.get(p10, []))
        print(p10, nm.get(p10, ''), f'필지 {len(ps)}, 용도지역 {len(zi)}, 소유 {len(own.get(p10, []))}', flush=True)
    save(d / 'dongs.json.gz', dongs)


if __name__ == '__main__':
    main(*sys.argv[1:])
