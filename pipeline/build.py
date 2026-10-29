"""seed(브이월드) + raw(건축물대장) → site/data/{법정동}.geojson (필지별 지표) + dongs.geojson (동 경계·요약)"""
import sys, json, math, re
from collections import defaultdict
from shapely.geometry import shape, mapping
from shapely import STRtree, set_precision
from .common import regions, OUT, SEED, rd
from .metrics import agg_bldgs, pnu_of

dump = lambda p, feats: p.write_text(json.dumps(dict(type='FeatureCollection', features=feats), ensure_ascii=False,
                                                separators=(',', ':')), encoding='utf-8')


def m2(g):  # 위경도 면적 → ㎡ (근사)
    return g.area * 111320 * 110540 * math.cos(math.radians(g.centroid.y))


def build_dong(sgg, p10, parcels):
    zs = [(shape(f['geometry']), f['properties'].get('uname', '')) for f in rd(sgg, f'{p10}_zones.json') or []]
    tree = STRtree([g for g, _ in zs])
    own = rd(sgg, f'{p10}_owners.json') or {}  # {pnu: 집계}
    bld = defaultdict(list)
    for b in rd(sgg, f'{p10}_bldgs.json') or []: bld[pnu_of(b)].append(b)

    feats = []
    for f in parcels:
        pnu, g = f['properties']['pnu'], shape(f['geometry'])
        if g.is_empty: continue
        pt = g.representative_point()
        z = next((zs[i][1] for i in tree.query(pt, predicate='within')), '') if zs else ''
        jb = f['properties'].get('jibun', '')
        o = own.get(pnu) or dict(ol=None, oh=None, pub=0, ar=round(m2(g), 1), jm=re.sub(r'^[\d\-\s산]+', '', jb), gj=0, cg='')
        p = dict(p=pnu, j=jb, z=z, **o, **agg_bldgs(bld.get(pnu, [])), cx=round(pt.x, 6), cy=round(pt.y, 6))
        if p['ol'] is None: p['ol'] = p['oh'] = 0 if p['pub'] else max(p['ho'], 1); p['oe'] = 1  # 소유정보 없음 → 호수 또는 1인
        feats.append(dict(type='Feature', geometry=mapping(set_precision(g, 1e-6)), properties=p))
    dump(OUT / f'{p10}.geojson', feats)
    s = lambda k: sum(x['properties'][k] for x in feats)
    return dict(np=len(feats), nb=s('nb'), no=s('no'), nu=s('nu'), ol=s('ol'), oe=sum(x['properties'].get('oe', 0) for x in feats))


def main(arg):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'dongs.geojson'
    dongs = {f['properties']['c']: f for f in json.loads(path.read_text(encoding='utf-8'))['features']} if path.exists() else {}
    for sgg in regions(arg):
        for f in rd(sgg, 'dongs.json') or []:
            pr, g = f['properties'], shape(f['geometry'])
            p10 = pr['emd_cd'] + '00'
            parcels = rd(sgg, f'{p10}_parcels.json')
            if not parcels: continue
            sm = build_dong(sgg, p10, parcels)
            nm = pr.get('full_nm') or next((' '.join(b['platPlc'].split()[:3]) for b in rd(sgg, f'{p10}_bldgs.json') or []
                                            if b.get('platPlc')), p10)  # 파일로 올린 동은 이름이 없어 건축물대장 주소로
            dongs[p10] = dict(type='Feature', geometry=mapping(set_precision(g.simplify(1e-5), 1e-6)),
                              properties=dict(c=p10, n=nm, b=[round(v, 5) for v in g.bounds],
                                              r=round(sm['no'] / sm['nb'], 3) if sm['nb'] else None, **sm))
            print(p10, nm, sm, flush=True)
    if (SEED / 'redev.json.gz').exists():  # 건축규제 구역 오버레이 (UD210)
        dump(OUT / 'redev.geojson', rd('', 'redev.json'))
    dump(path, list(dongs.values()))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'seeded')
