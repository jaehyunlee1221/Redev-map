"""정비사업 성공가능성 모델용 구역 변수 (GitHub에서 실행: 건축물대장 원본이 여기 있음)
  구역 = 정비구역 경계(zonepoly) 또는 해제구역(위치+면적 → 같은 면적의 원)
  기준연도(ref) 시점으로 노후도·건물수를 다시 계산 → 해제 뒤 새로 지은 빌라가 '해제라서 노후도 낮음'으로 섞이지 않게
  python -m pipeline.features  → data/raw/zone_features.json (+ DUMP=1이면 로그로)"""
import os, re, json, math, gzip, base64
from collections import defaultdict
from shapely.geometry import shape, Point
from shapely import STRtree
from shapely.affinity import scale
from .common import RAW, OUT, rd, regions
from .metrics import pnu_of, year, num, R
from .released import norm

FAR = {'제1종전용주거지역': 100, '제2종전용주거지역': 120, '제1종일반주거지역': 150, '제2종일반주거지역': 200, '제3종일반주거지역': 250,
       '준주거지역': 400, '중심상업지역': 1000, '일반상업지역': 800, '근린상업지역': 600, '유통상업지역': 600,
       '전용공업지역': 200, '일반공업지역': 200, '준공업지역': 400, '보전녹지지역': 50, '생산녹지지역': 50, '자연녹지지역': 50}
LANDMARK = dict(cityhall=(126.9780, 37.5665), gangnam=(127.0276, 37.4979), yeouido=(126.9246, 37.5219))
m_per_deg = lambda y: (111320 * math.cos(math.radians(y)), 110540)


def dist_m(a, b):
    kx, ky = m_per_deg((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * kx, (a[1] - b[1]) * ky)


class Parcels:
    """모든 구의 필지 대표점 + 속성(빌드 결과 site/data/p) + 원본 건물(data/raw bldgs)을 공간 색인"""
    def __init__(self):
        self.props, pts = [], []
        for f in sorted((OUT / 'p').glob('*.json')):
            for p in json.loads(f.read_text(encoding='utf-8')):
                self.props.append(p); pts.append(Point(p['cx'], p['cy']))
        self.tree = STRtree(pts)
        self.bld = defaultdict(list)
        for sgg in regions('seeded'):
            for d in rd(sgg, 'dongs.json') or []:
                for b in rd(sgg, f"{d['properties']['emd_cd']}00_bldgs.json") or []:
                    if str(b.get('mainAtchGbCd', '0')) == '0': self.bld[pnu_of(b)].append(b)
        st = RAW / 'stations.json'
        self.st = json.loads(st.read_text(encoding='utf-8')) if st.exists() else []
        mk = RAW / 'market.json'
        self.mk = json.loads(mk.read_text(encoding='utf-8')) if mk.exists() else {}

    def inside(self, g):
        return [self.props[i] for i in self.tree.query(g, predicate='contains')]


def old_at(b, ref):  # ref년 기준 노후 여부 (그때 있던 건물만)
    y = year(b.get('useAprDay'))
    if y is None: return None
    rc = any(k in (b.get('strctCdNm') or '') for k in R['rc_keywords'])
    return ref - y >= R['old_years']['rc' if rc else 'other']


def features(P, g, ref, sgg=None):
    ps = P.inside(g)
    if not ps: return None
    ar = sum(p.get('ar', 0) for p in ps) or 1
    ha = ar / 1e4
    bs = [b for p in ps for b in P.bld.get(p['p'], [])]
    pre = [b for b in bs if (year(b.get('useAprDay')) or 0) <= ref]       # 기준연도에 이미 있던 건물 (미상 포함)
    post = [b for b in bs if (year(b.get('useAprDay')) or 0) > ref]
    olds = [old_at(b, ref) for b in pre]
    ages = [ref - year(b.get('useAprDay')) for b in pre if year(b.get('useAprDay'))]
    dae = [p for p in ps if p.get('jm') == '대']
    zs = defaultdict(float)
    for p in ps: zs[p.get('z') or '미상'] += p.get('ar', 0)
    far_allow = sum(FAR.get(z, 0) * a for z, a in zs.items()) / ar
    far_now = sum(num(b.get('vlRatEstmTotArea')) or num(b.get('totArea')) for b in pre) / ar * 100
    c = g.centroid
    gj = [p['gj'] for p in ps if p.get('gj')]
    st = min((dist_m((c.x, c.y), (s['x'], s['y'])) for s in P.st), default=None)
    sg = sgg or ps[0]['p'][:5]
    mk = lambda key: P.mk.get(key) or {}
    m_gu = next((mk(f'{sg}|{y}') for y in range(ref, ref + 4) if mk(f'{sg}|{y}')), {})
    jip = sum(1 for b in pre if '집합' in (b.get('regstrGbCdNm') or ''))
    f = dict(
        area_ha=round(ha, 3), n_parcel=len(ps), n_bldg=len(pre), bldg_per_ha=len(pre) / ha,
        old_ratio=(sum(o is True for o in olds) / len(pre)) if pre else None,
        unknown_ratio=(sum(o is None for o in olds) / len(pre)) if pre else None,
        age_mean=(sum(ages) / len(ages)) if ages else None,
        new_after_ref=len(post) / max(len(pre), 1),                     # 기준연도 이후 신축 비율 (지분쪼개기·사업 이탈 신호)
        post_hh=sum(int(num(b.get('hhldCnt'))) for b in post),          # 기준연도 이후 생긴 세대수 → 크면 그 자리에 새 아파트 (사업 완료 확인용)
        post_apt_y=min((year(b.get('useAprDay')) for b in post if num(b.get('hhldCnt')) >= 100), default=None),
        new5_before_ref=sum(1 for a in ages if a < 5) / max(len(pre), 1),
        jiphap_ratio=jip / max(len(pre), 1),                            # 다세대·연립 등 집합건물 비율
        owners=sum(p.get('ol', 0) for p in ps), owners_per_ha=sum(p.get('ol', 0) for p in ps) / ha,
        owners_hi=sum(p.get('oh', 0) for p in ps),
        hh_per_ha=sum(int(num(b.get('hhldCnt')) + num(b.get('fmlyCnt'))) for b in pre) / ha,
        small_ratio=(sum(1 for p in dae if p.get('ar', 0) < R['small_parcel_m2']) / len(dae)) if dae else None,
        pub_ratio=sum(p.get('ar', 0) for p in ps if p.get('pub')) / ar,
        road_ratio=sum(p.get('ar', 0) for p in ps if p.get('jm') == '도로') / ar,
        dae_ratio=sum(p.get('ar', 0) for p in dae) / ar,
        far_allow=far_allow, far_now=far_now, far_room=far_allow - far_now,
        z1=zs.get('제1종일반주거지역', 0) / ar + zs.get('제1종전용주거지역', 0) / ar + zs.get('제2종전용주거지역', 0) / ar,
        z2=zs.get('제2종일반주거지역', 0) / ar, z3=zs.get('제3종일반주거지역', 0) / ar,
        zcom=sum(a for z, a in zs.items() if '상업' in z or '준주거' in z) / ar, zgreen=sum(a for z, a in zs.items() if '녹지' in z) / ar,
        gj_med=sorted(gj)[len(gj) // 2] if gj else None,
        lu_plan=sum(p.get('ar', 0) for p in ps if '지구단위' in (p.get('lu') or '')) / ar,
        lu_heritage=sum(p.get('ar', 0) for p in ps if re.search('문화|역사|고도|경관', p.get('lu') or '')) / ar,
        station_m=st,
        **{f'{k}_km': dist_m((c.x, c.y), v) / 1000 for k, v in LANDMARK.items()},
        apt_gu=m_gu.get('m'), apt_gu_new=m_gu.get('mn'),
        seoul=int(sg.startswith('11')), sgg=sg, cx=round(c.x, 6), cy=round(c.y, 6))
    sh = lambda key, vals: sum(p.get('ar', 0) for p in ps if p.get(key) in vals) / ar  # 면적 비율
    for k, v in LT_VARS.items(): f[k] = sh('lt', v)
    known = sh('ot', OT_ALL)
    for k, v in OT_VARS.items(): f[k] = sh('ot', v) / known if known > 0.3 else None  # 소유자 유형은 소유정보가 있는 면적 기준 (v3 수집 전엔 대부분 없음)
    f['n_relig'] = sum(1 for p in ps if p.get('lt') == '종교'); f['n_school'] = sum(1 for p in ps if p.get('lt') == '학교')
    if f['apt_gu_new'] and f['gj_med']: f['price_gap'] = f['apt_gu_new'] * 1e4 / f['gj_med']  # 신축 아파트 ㎡가 / 공시지가 ㎡가 → 사업성 근사
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()}


LT_VARS = dict(lt_apt={'공동주택'}, lt_house={'단독주택'}, lt_nbhd={'근린생활'}, lt_comm={'상업·업무'}, lt_relig={'종교'}, lt_school={'학교'},
               lt_road={'도로'}, lt_park={'공원'}, lt_vacant={'나대지'})  # 토지 유형별 면적 비율 (build.land_type)
OT_VARS = dict(ow_ind={'개인'}, ow_corp={'법인'}, ow_pub={'국공유'}, ow_clan={'종중', '종교단체'})  # 소유자 유형별 면적 비율
OT_ALL = {'개인', '법인', '국공유', '종중', '종교단체', '기타'}


def circle(x, y, area_m2):  # 면적이 같은 원 (위경도 비율 보정)
    r = math.sqrt(max(area_m2, 1000) / math.pi)
    kx, ky = m_per_deg(y)
    return scale(Point(x, y).buffer(r / kx, 32), 1, kx / ky, origin=(x, y))


def ty(s):
    """사업 유형을 출처와 상관없이 같은 기준으로: 도시정비형(도시환경) / 주택정비형(주택재개발) / 재건축"""
    s = s or ''
    return '재건축' if '재건축' in s else '도시정비형' if re.search('도시정비|도시환경', s) else '주택정비형'


def zone_areas():
    """구역 이름(정규화) → 면적㎡: 서울플랜+ 정비사업 현황, 없으면 정비구역 결정고시 이력의 마지막 변경 후 면적"""
    out = {}
    up = lambda n: json.loads((RAW / 'upis' / f'{n}.json').read_text(encoding='utf-8')) if (RAW / 'upis' / f'{n}.json').exists() else []
    for r in sorted(up('upisRebuild') + up('upisNewtown'), key=lambda r: r['RPT_MNG_CD'][8:16]):
        v = str(r.get('AREA_CHG_AFTR') or '')
        if r['RPT_TYPE'] not in ('폐지', '실효') and re.fullmatch(r'[\d.]+', v) and float(v) > 500: out[norm(r['RGN_NM'])] = float(v)
    for r in up('vnBsnsNmtn'):
        if (r.get('BSNS_AREA') or 0) > 500: out[norm(r.get('BSNS_NAME'))] = float(r['BSNS_AREA'])  # AREA는 연면적 → 구역면적은 BSNS_AREA
    out.pop('', None)
    return out


def main():
    P = Parcels()
    print(f'필지 {len(P.props)} · 건물 {sum(map(len, P.bld.values()))} · 역 {len(P.st)} · 실거래 요약 {len(P.mk)}', flush=True)
    zs = json.loads((OUT / 'zones.geojson').read_text(encoding='utf-8'))['features']
    polys = {f['properties']['zi']: shape(f['geometry']) for f in json.loads((OUT / 'zonepoly.geojson').read_text(encoding='utf-8'))['features']
             if 'zi' in f['properties']} if (OUT / 'zonepoly.geojson').exists() else {}
    area = zone_areas()
    rows = []
    for i, z in enumerate(zs):
        pr = z['properties']
        if pr.get('c'): continue  # 서울플랜+에서 덧붙인 사업(신통기획·모아타운 등)은 모델 대상 아님
        ref = int((pr.get('zd') or pr.get('cm') or pr.get('jo') or '2026')[:4])
        ref = min(max(ref, 2006), 2026)
        meta = {k: pr.get(k) for k in ('t', 's', 'si', 'pp', 'gp', 'eh', 'bh', 'zd', 'cm', 'jo', 'sa', 'gc', 'ij', 'cs')}
        g = polys.get(i)
        if g is not None:
            f = features(P, g, ref)
            if f: rows.append(dict(kind='active', id=i, name=pr.get('n'), ref=ref, ty=ty(pr.get('t')), **meta, **f))
            a, src = g.area * m_per_deg(g.centroid.y)[0] * m_per_deg(g.centroid.y)[1], '경계'
            x, y = g.centroid.x, g.centroid.y
        else:  # 경계가 아직 없으면(토지이용계획 미수집) 서울시 고시 면적으로 원
            a, src = area.get(norm(pr.get('n'))), '고시'
            x, y = z['geometry']['coordinates']
            if not a: continue
        f = features(P, circle(x, y, a), ref)  # 해제구역과 같은 방식(원) → 비교용
        if f: rows.append(dict(kind='active_c', id=i, name=pr.get('n'), ref=ref, area_src=src, ty=ty(pr.get('t')), **meta, **f))
    rel = RAW / 'released.json'  # 해제구역 (pipeline.released: 서울시 정비구역 결정고시 이력의 폐지·실효)
    if rel.exists():
        for r in json.loads(rel.read_text(encoding='utf-8')):
            if not r.get('x'): continue
            ref = int(str(r.get('ref') or r.get('rd') or '2012')[:4])
            f = features(P, circle(r['x'], r['y'], r.get('area') or 30000), min(max(ref, 2006), 2026))  # 위치=대표 지번 → 같은 면적의 원 (근사)
            if f: rows.append(dict(kind='released', name=r.get('n'), ref=ref, rd=r.get('rd'), zd=r.get('zd'), t=r.get('kind'), ty=ty(r.get('t')), **f))
    done = RAW / 'completed.json'  # 완료 추정 구역 (해제 이력 없이 진행 목록에서 빠진 곳) → 성공 사례 후보
    if done.exists():
        for r in json.loads(done.read_text(encoding='utf-8')):
            if not r.get('x'): continue
            f = features(P, circle(r['x'], r['y'], r.get('area') or 30000), min(max(r['ref'], 2006), 2026))
            if f: rows.append(dict(kind='done', name=r.get('n'), ref=r['ref'], zd=r.get('zd'), dd=r.get('dd'), t=r.get('kind'), ty=ty(r.get('t')), **f))
    out = RAW / 'zone_features.json'
    out.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    print(f'구역 변수 {len(rows)}개 (진행 {sum(r["kind"] == "active" for r in rows)} · 진행-원 {sum(r["kind"] == "active_c" for r in rows)} · 해제 {sum(r["kind"] == "released" for r in rows)} · 완료추정 {sum(r["kind"] == "done" for r in rows)})', flush=True)
    if os.environ.get('DUMP'): print('FEATDUMP', base64.b64encode(gzip.compress(json.dumps(rows, ensure_ascii=False).encode())).decode(), flush=True)


if __name__ == '__main__':
    main()
