"""투자 계산용 구역별 기초 숫자 (계산 자체는 지도에서 가정값을 바꿔 가며 함)
  - 매수 대상: 재개발·가로주택 등 → 구역 안 연립·다세대(빌라) 최근 24개월 매매 / 아파트 재건축 → 구역 안 아파트 매매
  - 대지지분: 빌라는 실거래의 대지권 면적(landAr), 아파트는 구역 안 대지 면적 ÷ 기존 세대수
  - 공시지가: 그 필지(빌라) 또는 구역 대지 중위(아파트)의 현재 개별공시지가
  - 전세: 같은 대상의 최근 24개월 전세(월세 0) 보증금 중위 (활용승인 전이면 없음)
  - 남은 기간: 서울 정비사업의 단계별 날짜로 단계 사이 중위 기간을 구해 현재 단계부터 착공까지 + 착공→입주 3.5년
  python -m pipeline.invest → site/data/zinvest.json"""
import json, math, statistics
from collections import defaultdict
from datetime import date
from shapely.geometry import shape, Point
from .common import RAW, OUT
from .redev import Locator, DATES

ORDER = ['zd', 'cm', 'jo', 'sa', 'gc', 'ij', 'cs']  # 구역지정 → 추진위 → 조합 → 사업시행 → 관리처분 → 이주 → 착공
STAGE_KEY = {0: 'zd', 1: 'cm', 2: 'jo', 3: 'jo', 4: 'sa', 5: 'gc', 6: 'ij', 7: 'cs'}  # 지도 단계(si) → 마지막으로 지난 날짜
BUILD_Y, PRE_Y = 3.5, 2.5  # 착공→입주, 후보(신통 등)→구역지정
SMALL_Y = {-1: 6.0, 0: 5.5, 1: 5.0, 2: 4.0, 3: 3.5, 4: 3.0, 7: 2.0}  # 가로주택 등 남은 기간 가정 (조합설립 전후 → 입주)
SMALL = ('가로주택', '소규모재건축', '소규모재개발', '자율주택')


def stage_gaps():
    """단계 사이 중위 기간(년): 서울 정비사업 통계의 단계별 최초 일자"""
    rows = json.loads((RAW / 'redev_seoul.json').read_text(encoding='utf-8')) if (RAW / 'redev_seoul.json').exists() else []
    y = lambda s: int(s[:4]) + (int(s[5:7]) - 1) / 12 if s and len(s) >= 7 else None
    gaps = defaultdict(list)
    for r in rows:
        ds = [(k, y(r.get(DATES[k]) or '')) for k in ORDER]
        ds = [(k, v) for k, v in ds if v]
        for (a, va), (b, vb) in zip(ds, ds[1:]):
            if 0 <= vb - va < 25: gaps[(a, b)].append(vb - va)
    med = {k: statistics.median(v) for k, v in gaps.items() if len(v) >= 5}
    step = {}  # 바로 다음 단계까지 (중간이 비면 건너뛴 쌍으로)
    for a, b in zip(ORDER, ORDER[1:]): step[a] = med.get((a, b), 1.0)
    return step, {f'{a}→{b}': round(v, 1) for (a, b), v in med.items()}


def remain_years(p, step):
    si = p.get('si', -1)
    if p.get('c') in SMALL: return SMALL_Y.get(si, 4.0)
    if si >= 8: return 0
    k = STAGE_KEY.get(si)
    yrs = PRE_Y if k is None else 0
    for a in ORDER[ORDER.index(k) if k else 0:-1]: yrs += step[a]
    return round(yrs + BUILD_Y, 1)


def trades(kind, months=24):
    t = date.today()
    ym0 = (t.year - months // 12) * 100 + t.month
    for p in (RAW / kind).glob('*/*.json'):
        if int(p.stem) < ym0: continue
        for r in json.loads(p.read_text(encoding='utf-8')):
            if not r.get('cdealType'): yield p.parent.name, r


def main():
    loc = Locator()
    gu = {p10[:5]: g for (g, _), p10 in loc.dong.items()}
    props = {}
    def prop(pnu):  # 필지 속성 (공시지가 등)
        p10 = pnu[:10]
        if p10 not in props:
            f = OUT / 'p' / f'{p10}.json'
            props[p10] = {p['p']: p for p in json.loads(f.read_text(encoding='utf-8'))} if f.exists() else {}
        return props[p10].get(pnu)
    where = {}
    def place(sgg, umd, jb):  # (구 코드, 동, 지번) → (좌표, pnu)
        k = (sgg, umd, jb)
        if k not in where:
            g = gu.get(sgg)
            _, p10, san, bun, ji = loc.split(g, f'{umd} {jb}')
            xy, _ = loc.find(g, f'{umd} {jb}')
            where[k] = (xy, f'{p10}{"2" if san else "1"}{bun:04d}{ji:04d}' if p10 and bun is not None else None)
        return where[k]
    num = lambda v: float(str(v).replace(',', '') or 0)
    src = defaultdict(list)  # 종류별 [(좌표, 행, pnu)]
    for kind in ('rh', 'rtms', 'rhrent', 'aptrent'):
        for sgg, r in trades(kind):
            xy, pnu = place(sgg, r.get('umdNm', ''), r.get('jibun', ''))
            if xy: src[kind].append((Point(xy), r, pnu))
    print('최근 24개월 실거래 위치 찾음:', {k: len(v) for k, v in src.items()}, flush=True)
    zs = json.loads((OUT / 'zones.geojson').read_text(encoding='utf-8'))['features']
    polys = {}
    for f in json.loads((OUT / 'zonepoly.geojson').read_text(encoding='utf-8'))['features']:
        if 'zi' in f['properties']: polys.setdefault(f['properties']['zi'], shape(f['geometry']))
    step, gaps = stage_gaps()
    med = lambda v: round(statistics.median(v)) if v else None
    out = {}
    for i, f in enumerate(zs):
        p = f['properties']
        if p.get('si', -1) >= 7 or p.get('c') in ('모아타운', '역세권활성화', '역세권장기전세', '역세권안심주택'): continue
        g = polys.get(i) or Point(f['geometry']['coordinates']).buffer(0.0027)  # 경계가 없으면 반경 약 300m
        apt = '재건축' in (p.get('t') or '') and p.get('c') not in SMALL and '단독' not in (p.get('t') or '')
        buy = [(r, pnu) for pt, r, pnu in src['rtms' if apt else 'rh'] if g.contains(pt)]
        if len(buy) < 2: continue
        pr = [num(r['dealAmount']) for r, _ in buy]
        ex = [num(r['excluUseAr']) for r, _ in buy if num(r['excluUseAr'])]
        if apt:  # 대지지분 = 구역 대지 합 ÷ 기존 세대 (아파트 실거래엔 대지지분이 없음)
            inside = [q for q in (prop(pnu) for _, pnu in buy) if q]
            gj = med([q['gj'] for q in inside if q.get('gj')])
            la = round(g.area * 111320 * math.cos(math.radians(g.centroid.y)) * 110540 * 0.75 / p['eh'], 1) if p.get('eh') else None
        else:
            la = med([num(r.get('landAr')) for r, _ in buy if num(r.get('landAr'))])
            gj = med([q['gj'] for q in (prop(pnu) for _, pnu in buy) if q and q.get('gj')])
        rent = [num(r['deposit']) for pt, r, _ in src['aptrent' if apt else 'rhrent'] if g.contains(pt) and not num(r.get('monthlyRent'))]
        out[str(i)] = dict(k='apt' if apt else 'villa', n=len(buy), pr=med(pr), ex=med(ex), la=la, gj=gj, js=med(rent) if len(rent) >= 2 else None,
                           nj=len(rent), yr=remain_years(p, step))
    meta = dict(asof=str(date.today()), gaps=gaps, build_y=BUILD_Y, pre_y=PRE_Y,
                note='매수가·전세는 구역 안(경계 없으면 반경 300m) 최근 24개월 실거래 중위. 아파트 재건축 대지지분은 구역 대지×0.75÷기존 세대 추정')
    (OUT / 'zinvest.json').write_text(json.dumps(dict(meta=meta, z=out), ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f"투자 기초 숫자 {len(out)}곳 (빌라 {sum(v['k'] == 'villa' for v in out.values())} · 아파트 {sum(v['k'] == 'apt' for v in out.values())} · 전세 있음 {sum(1 for v in out.values() if v['js'])})", flush=True)
    print('  단계 사이 중위 기간(년):', gaps, flush=True)


if __name__ == '__main__':
    main()
