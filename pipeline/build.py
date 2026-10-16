"""data/raw → site/data/{법정동}.geojson (필지별 지표) + site/data/dongs.geojson (동 경계·요약)"""
import sys, json, math, re
from collections import defaultdict
from shapely.geometry import shape, mapping
from shapely import STRtree, set_precision
from .common import regions, RAW, OUT
from .metrics import agg_bldgs, agg_owners, pnu_of

load = lambda p: json.loads(p.read_text(encoding='utf-8')) if p.exists() else []


def m2(g):  # 위경도 면적 → ㎡ (근사)
    return g.area * 111320 * 110540 * math.cos(math.radians(g.centroid.y))


def build_dong(sgg, p10):
    d = RAW / sgg
    zs = [(shape(f['geometry']), f['properties'].get('uname', '')) for f in load(d / f'{p10}_zones.json')]
    tree = STRtree([g for g, _ in zs])
    own, bld = defaultdict(list), defaultdict(list)
    for r in load(d / f'{p10}_owners.json'): own[r['pnu']].append(r)
    for b in load(d / f'{p10}_bldgs.json'): bld[pnu_of(b)].append(b)

    feats = []
    for f in load(d / f'{p10}_parcels.json'):
        pnu, g = f['properties']['pnu'], shape(f['geometry'])
        pt = g.representative_point()
        z = next((zs[i][1] for i in tree.query(pt, predicate='within')), '') if zs else ''
        jb = f['properties'].get('jibun', '')
        o = agg_owners(own.get(pnu))
        if o is None:  # 소유정보 없음 → 집합건물 호수 또는 1인으로 대체
            o = dict(ol=None, oh=None, pub=0, ar=round(m2(g), 1), jm=re.sub(r'^[\d\-\s산]+', '', jb), gj=0, cg='')
        p = dict(p=pnu, j=jb, z=z, **o, **agg_bldgs(bld.get(pnu, [])), cx=round(pt.x, 6), cy=round(pt.y, 6))
        if p['ol'] is None: p['ol'] = p['oh'] = 0 if p['pub'] else max(p['ho'], 1); p['oe'] = 1
        feats.append(dict(type='Feature', geometry=mapping(set_precision(g, 1e-6)), properties=p))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{p10}.geojson').write_text(json.dumps(dict(type='FeatureCollection', features=feats),
                                                   ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    s = lambda k: sum(x['properties'][k] for x in feats)
    return dict(np=len(feats), nb=s('nb'), no=s('no'), nu=s('nu'), ol=s('ol'))


def main(arg):
    path = OUT / 'dongs.geojson'
    dongs = {f['properties']['c']: f for f in (load(path) or {'features': []})['features']}
    for sgg in regions(arg):
        for f in load(RAW / sgg / 'dongs.json'):
            pr, g = f['properties'], shape(f['geometry'])
            p10 = pr['emd_cd'] + '00'
            if not (RAW / sgg / f'{p10}_parcels.json').exists(): continue
            sm = build_dong(sgg, p10)
            dongs[p10] = dict(type='Feature', geometry=mapping(set_precision(g.simplify(1e-5), 1e-6)),
                              properties=dict(c=p10, n=pr.get('full_nm') or pr.get('emd_kor_nm', ''),
                                              b=[round(v, 5) for v in g.bounds],
                                              r=round(sm['no'] / sm['nb'], 3) if sm['nb'] else None, **sm))
            print(p10, dongs[p10]['properties']['n'], sm, flush=True)
    path.write_text(json.dumps(dict(type='FeatureCollection', features=list(dongs.values())),
                               ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'test')
