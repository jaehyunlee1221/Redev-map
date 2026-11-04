"""seed(브이월드) + raw(건축물대장) → site/data/{법정동}.geojson (필지별 지표) + dongs.geojson (동 경계·요약)"""
import os, sys, json, math, re
from collections import defaultdict
from shapely.geometry import shape, mapping
from shapely import STRtree, set_precision, make_valid
from .common import regions, OUT, SEED, rd
from .metrics import agg_bldgs, pnu_of

dump = lambda p, feats: p.write_text(json.dumps(dict(type='FeatureCollection', features=feats), ensure_ascii=False,
                                                separators=(',', ':')), encoding='utf-8')


def snap(g):  # 좌표 정밀도 1e-6으로 → 꼬인 도형은 고쳐서, 그래도 안 되면 원본 그대로
    for fix in (lambda: g, lambda: make_valid(g)):
        try: return mapping(set_precision(fix(), 1e-6))
        except Exception: pass
    return mapping(g)


def m2(g):  # 위경도 면적 → ㎡ (근사)
    return g.area * 111320 * 110540 * math.cos(math.radians(g.centroid.y))


LU_SHOW = re.compile(r'정비|촉진|지구단위|고도지구|경관지구|역사문화|문화재|개발제한|최고높이|층이하|도시계획시설|도로')  # 팝업에 보일 토지이용계획
KEEP = {'nb', 'ol', 'oh', 'no', 'nn', 'pub'}  # 0이어도 남길 속성 (지도 색칠에 씀)


FARLOG = []


def far(p):
    """현재 용적률(%) → p['fr']. 아파트 단지는 건물 전부가 대표 지번 한 필지에 등록돼 필지 면적으로 나누면 수만 %가 됨
    → 대장에 적힌 용적률(vlRat) 우선, 없으면 연면적 ÷ max(필지 면적, 대장상 대지면적), 그래도 1,500% 넘으면 표시 안 함"""
    pa, vr = p.pop('pa', 0), p.pop('vr', 0)
    if not p.get('va'): return
    den = max(p.get('ar') or 0, pa or 0)
    old = round(p['va'] / p['ar'] * 100) if p.get('ar') else None
    fr = vr or (round(p['va'] / den * 100) if den else None)
    if fr and fr > 1500: fr = None
    if fr: p['fr'] = fr
    if old and old > 1500 and len(FARLOG) < 2000: FARLOG.append((p['p'], p.get('j'), old, fr, vr, pa, p.get('ar'), p.get('nb')))


def build_dong(sgg, p10, parcels):
    zs = [(shape(f['geometry']), f['properties'].get('uname', '')) for f in rd(sgg, f'{p10}_zones.json') or []]
    tree = STRtree([g for g, _ in zs])
    own = rd(sgg, f'{p10}_owners.json') or {}  # {pnu: 집계}
    lu = rd(sgg, f'{p10}_landuse.json') or {}  # 토지이용계획 {pnu: [[코드, 저촉여부]]}
    lun = {c: n for c, n in lu.get('_c', {}).items() if LU_SHOW.search(n or '')}
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
        p = dict(p=pnu, j=jb, z=z, **o, **agg_bldgs(bld.get(pnu, [])), cx=round(pt.x, 6), cy=round(pt.y, 6),
                 lu='·'.join(dict.fromkeys(lun[c] + ('(저촉)' if a == '2' else '') for c, a in lu.get(pnu, []) if c in lun)))
        if p['ol'] is None: p['ol'] = p['oh'] = 0 if p['pub'] else max(p['ho'], 1); p['oe'] = 1  # 소유정보 없음 → 호수 또는 1인
        far(p)
        feats.append(dict(type='Feature', geometry=snap(g), properties={k: v for k, v in p.items() if v not in (None, '', 0) or k in KEEP}))
    (OUT / 'p').mkdir(exist_ok=True)  # 구역 그리기 통계용: 속성만 (지도 표시는 벡터타일)
    (OUT / 'p' / f'{p10}.json').write_text(json.dumps([f['properties'] for f in feats], ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    with open(OUT / 'parcels.ndjson', 'a', encoding='utf-8') as nd:  # → tippecanoe → parcels.pmtiles
        for f in feats:
            nd.write(json.dumps(f, ensure_ascii=False, separators=(',', ':')) + '\n')
            if f['properties'].get('j'):  # 지번 라벨용 점 (다른 레이어)
                nd.write(json.dumps(dict(type='Feature', tippecanoe=dict(layer='lb', minzoom=15), properties=dict(j=f['properties']['j']),
                                         geometry=dict(type='Point', coordinates=[f['properties']['cx'], f['properties']['cy']])),
                                    ensure_ascii=False, separators=(',', ':')) + '\n')
    s = lambda k: sum(x['properties'].get(k, 0) for x in feats)
    return dict(np=len(feats), nb=s('nb'), no=s('no'), nu=s('nu'), ol=s('ol'), oe=sum(x['properties'].get('oe', 0) for x in feats))


def main(arg):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'dongs.geojson'
    dongs = {f['properties']['c']: f for f in json.loads(path.read_text(encoding='utf-8'))['features']} if path.exists() else {}
    (OUT / 'parcels.ndjson').unlink(missing_ok=True)
    for sgg in regions(arg):
        for f in rd(sgg, 'dongs.json') or []:
            pr, g = f['properties'], shape(f['geometry'])
            p10 = pr['emd_cd'] + '00'
            parcels = rd(sgg, f'{p10}_parcels.json')
            if not parcels: continue
            sm = build_dong(sgg, p10, parcels)
            nm = pr.get('full_nm') or next((' '.join(b['platPlc'].split()[:3]) for b in rd(sgg, f'{p10}_bldgs.json') or []
                                            if b.get('platPlc')), p10)  # 파일로 올린 동은 이름이 없어 건축물대장 주소로
            dongs[p10] = dict(type='Feature', geometry=snap(g.simplify(1e-5)),
                              properties=dict(c=p10, n=nm, b=[round(v, 5) for v in g.bounds],
                                              r=round(sm['no'] / sm['nb'], 3) if sm['nb'] else None, **sm))
            print(p10, nm, sm, flush=True)
    if (SEED / 'redev.json.gz').exists():  # 건축규제 구역 오버레이 (UD210)
        dump(OUT / 'redev.geojson', rd('', 'redev.json'))
    dump(path, list(dongs.values()))
    if FARLOG:  # 용적률 보정 확인용
        print(f'용적률 보정: 필지 면적 기준 1,500% 넘던 필지 {len(FARLOG)}개 → 대장 용적률 사용 {sum(1 for x in FARLOG if x[4])} · 대지면적으로 계산 '
              f'{sum(1 for x in FARLOG if x[3] and not x[4])} · 표시 안 함 {sum(1 for x in FARLOG if not x[3])}', flush=True)
        for x in FARLOG[:12]: print('  (pnu, 지번, 이전%, 보정%, 대장용적률, 대장대지, 필지면적, 동수)', x, flush=True)
    import time  # 데이터 버전: 바뀌면 브라우저가 캐시를 버리고 새로 받음
    (OUT / 'version.json').write_text(json.dumps(dict(v=os.environ.get('GITHUB_RUN_ID') or str(int(time.time())))), encoding='utf-8')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'seeded')
