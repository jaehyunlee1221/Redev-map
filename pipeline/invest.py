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
    # 각 단계 → 착공: 실제로 착공까지 간 구역에서 직접 잰 중위 (이웃 단계 중위를 이어 붙이면 표본이 달라 과대)
    to_cs = defaultdict(list)
    for r in rows:
        c = y(r.get(DATES['cs']) or '')
        if not c: continue
        for k in ORDER[:-1]:
            v = y(r.get(DATES[k]) or '')
            if v and 0 <= c - v < 30: to_cs[k].append(c - v)
    rem = {k: statistics.median(v) for k, v in to_cs.items() if len(v) >= 5}
    return step, rem, {f'{a}→{b}': round(v, 1) for (a, b), v in med.items()}, {k: (round(v, 1), len(to_cs[k])) for k, v in rem.items()}


def remain_years(p, step, rem=None):
    si = p.get('si', -1)
    if p.get('c') in SMALL: return SMALL_Y.get(si, 4.0)
    if si >= 8: return 0
    k = STAGE_KEY.get(si)
    yrs = PRE_Y if k is None else 0
    k0 = k or 'zd'
    if rem and k0 in rem: yrs += rem[k0]  # 그 단계 → 착공 직접 중위
    else:
        for a in ORDER[ORDER.index(k0):-1]: yrs += step[a]
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
    step, rem, gaps, rem_log = stage_gaps()
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
        if apt:  # 아파트 실거래엔 대지지분이 없음 → 거래된 단지 필지 면적 ÷ 그 필지 세대수(건축물대장), 없으면 구역 대지×0.75 ÷ 기존 세대
            inside = [q for q in (prop(pnu) for _, pnu in buy) if q]
            gj = med([q['gj'] for q in inside if q.get('gj')])
            per = [q['ar'] / u for q in inside if q.get('ar') and (u := max(q.get('hh') or 0, q.get('ho') or 0)) >= 20]
            la = med([v for v in per if 5 <= v <= 200])
            if la is None and (p.get('eh') or 0) >= 50:
                la = round(g.area * 111320 * math.cos(math.radians(g.centroid.y)) * 110540 * 0.75 / p['eh'], 1)
            if la is not None and not 5 <= la <= 200: la = None  # 말이 안 되는 값은 버림 (기존 세대 수가 잘못 적힌 구역 등)
        else:
            la = med([num(r.get('landAr')) for r, _ in buy if num(r.get('landAr'))])
            gj = med([q['gj'] for q in (prop(pnu) for _, pnu in buy) if q and q.get('gj')])
        rent = [num(r['deposit']) for pt, r, _ in src['aptrent' if apt else 'rhrent'] if g.contains(pt) and not num(r.get('monthlyRent'))]
        out[str(i)] = dict(k='apt' if apt else 'villa', n=len(buy), pr=med(pr), ex=med(ex), la=la, gj=gj, js=med(rent) if len(rent) >= 2 else None,
                           nj=len(rent), yr=remain_years(p, step, rem))
    meta = dict(asof=str(date.today()), gaps=gaps, to_cs={k: v for k, (v, _) in rem_log.items()}, build_y=BUILD_Y, pre_y=PRE_Y,
                note='매수가·전세는 구역 안(경계 없으면 반경 300m) 최근 24개월 실거래 중위. 아파트 재건축 대지지분은 구역 대지×0.75÷기존 세대 추정')
    (OUT / 'zinvest.json').write_text(json.dumps(dict(meta=meta, z=out), ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f"투자 기초 숫자 {len(out)}곳 (빌라 {sum(v['k'] == 'villa' for v in out.values())} · 아파트 {sum(v['k'] == 'apt' for v in out.values())} · 전세 있음 {sum(1 for v in out.values() if v['js'])})", flush=True)
    print('  단계 사이 중위 기간(년):', gaps, flush=True)
    print('  단계 → 착공 중위(년, 구역 수):', rem_log, flush=True)
    sanity(out, zs)


def calc(b, v, land=1.3, ratio=100, mem=75):
    """지도(site/index.html invest())와 같은 계산 — 로그 점검용"""
    if not b.get('pr') or not v: return None
    right = b['la'] * b['gj'] * land / 1e4 * ratio / 100 if b.get('la') and b.get('gj') else None
    tax = b['pr'] * (0.011 if b['pr'] <= 6e4 else 0.022 if b['pr'] <= 9e4 else 0.033)
    if right is None: return None
    total = b['pr'] + tax + v['v84'] * mem / 100 - right
    yr = max(b.get('yr') or 5, 1)
    return dict(prem=b['pr'] - right, right=right, init=b['pr'] - b['js'] + tax if b.get('js') else None, total=total,
                gain=v['v84'] - total, ann=(v['v84'] / total) ** (1 / yr) - 1 if total > 0 else None, yr=yr)


def sanity(out, zs):
    """기본 가정으로 계산해 분포·이상치 출력 (지도 숫자가 말이 되는지 확인용)"""
    vf = OUT / 'zvalue.json'
    if not vf.exists(): return
    zv = json.loads(vf.read_text(encoding='utf-8'))['z']
    R = {i: calc(b, zv.get(i)) for i, b in out.items()}
    R = {i: r for i, r in R.items() if r}
    q = lambda xs: (lambda s: f'중위 {s[len(s) // 2] / 1e4:.2f}억 (10% {s[len(s) // 10] / 1e4:.2f} ~ 90% {s[len(s) * 9 // 10] / 1e4:.2f})')(sorted(xs)) if xs else '-'
    print(f'  [점검] 계산 가능 {len(R)}/{len(out)}곳 (대지지분·공시지가 없음 {len(out) - len(R)})', flush=True)
    for k in ('pr', 'js'):
        print(f'    {k}: {q([b[k] for b in out.values() if b.get(k)])}', flush=True)
    for k in ('right', 'prem', 'init', 'total', 'gain'):
        print(f'    {k}: {q([r[k] for r in R.values() if r[k] is not None])}', flush=True)
    an = sorted(r['ann'] for r in R.values() if r['ann'] is not None)
    if an: print(f"    연수익: 중위 {an[len(an) // 2]:.1%} (10% {an[len(an) // 10]:.1%} ~ 90% {an[len(an) * 9 // 10]:.1%})", flush=True)
    print(f"    이상치: 프리미엄<0 {sum(r['prem'] < 0 for r in R.values())} · 갭<0 {sum(1 for r in R.values() if r['init'] is not None and r['init'] < 0)} · "
          f"대지지분>200㎡ {sum(1 for b in out.values() if (b.get('la') or 0) > 200)} · 대지지분<5㎡ {sum(1 for b in out.values() if b.get('la') and b['la'] < 5)}", flush=True)
    nm = lambda i: f"{zs[int(i)]['properties'].get('n')}({zs[int(i)]['properties'].get('s', '')})"
    for lab, key, rev in (('연수익 상위', 'ann', True), ('프리미엄 음수', 'prem', False)):
        L = sorted((i for i in R if R[i][key] is not None), key=lambda i: R[i][key], reverse=rev)[:8]
        print(f'    {lab}: ' + ' | '.join(f"{nm(i)} 매수{out[i]['pr'] / 1e4:.1f}억 지분{out[i]['la']}㎡ 공시{out[i]['gj']} 권리{R[i]['right'] / 1e4:.1f}억 "
                                         f"완공{zv[i]['v84'] / 1e4:.1f}억 총{R[i]['total'] / 1e4:.1f}억 연{R[i]['ann'] or 0:.1%} {R[i]['yr']}년" for i in L), flush=True)


if __name__ == '__main__':
    main()
