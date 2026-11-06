"""사업이 끝났을 때의 가치 (현재 시세 기준): 구역 주변 신축 아파트 실거래로 '새 아파트 84㎡ 지금 시세' 추정
  - 신축 = 준공 10년 이내, 최근 24개월 매매, 전용 59~114㎡ (계약 해제 제외)
  - 단지 위치: 실거래의 법정동·지번 → 필지 대표점 (redev.Locator)
  - 단지 규모(세대수): 건축물대장(그 지번의 동별 세대수 합). 같은 구 안에서 세대수가 클수록 ㎡당 시세가 얼마나 높은지(탄력성 β)를 추정
  - 같은 전용면적 기준: 단지마다 전용 59㎡형(55~64㎡)·84㎡형(80~89㎡)의 '가장 최근' 거래가
  - 구역별: 2km 안에서 그 평형 거래가 있는 가까운 신축 단지 최대 5곳을 거리 역가중 평균 → 구역 계획 세대수로 규모 보정
    (그 평형 거래가 없으면 ㎡당 중위 × 면적으로 대신)
  python -m pipeline.value  → site/data/zvalue.json {meta, z: {구역 index: {v59, v84, ppm, n, comps: [[단지, 거리m, 준공, 84 최근가, 84 거래월, 세대, 59 최근가, 59 거래월]]}}}"""
import json, math, statistics
from collections import defaultdict
from datetime import date
from .common import RAW, OUT, rd
from .redev import Locator
from .metrics import pnu_of, num

M2 = lambda y: (111320 * math.cos(math.radians(y)), 110540)
BANDS = {59: (55, 64), 84: (80, 89)}  # 전용면적 평형 구간 (㎡)


def complexes(loc):
    """신축 단지별 ㎡당 매매가 중위 (만원/㎡) + 위치"""
    t = date.today()
    ym0 = (t.year - 2) * 100 + t.month  # 최근 24개월
    gu = {p10[:5]: g for (g, _), p10 in loc.dong.items()}
    agg = defaultdict(list)
    for p in (RAW / 'rtms').glob('*/*.json'):
        if int(p.stem) < ym0: continue
        for r in json.loads(p.read_text(encoding='utf-8')):
            try: amt, ar, by = float(r['dealAmount'].replace(',', '')), float(r['excluUseAr']), int(r['buildYear'] or 0)
            except ValueError: continue
            if r.get('cdealType') or not (55 <= ar <= 114) or t.year - by > 10: continue
            agg[(p.parent.name, r['umdNm'], r['jibun'], r['aptNm'], by)].append((int(p.stem), int(r.get('dealDay') or 0), amt, ar))
    out, hh = [], {}
    for (sgg, umd, jb, nm, by), v in agg.items():
        if not v: continue
        last = {}
        for b, (lo, hi) in BANDS.items():  # 같은 평형의 가장 최근 거래
            band = [x for x in v if lo <= x[3] < hi]
            if band: last[b] = max(band)[:3]  # (연월, 일, 금액)
        v = [a / ar for _, _, a, ar in v]
        xy, _ = loc.find(gu.get(sgg), f'{umd} {jb}')
        if not xy: continue
        _, p10, san, bun, ji = loc.split(gu.get(sgg), f'{umd} {jb}')
        h = None
        if p10 and bun is not None:  # 단지 세대수 = 그 지번에 등록된 동들의 세대수 합 (건축물대장)
            if p10 not in hh:
                hh[p10] = defaultdict(int)
                for b in rd(sgg, f'{p10}_bldgs.json') or []: hh[p10][pnu_of(b)] += int(num(b.get('hhldCnt')))
            h = hh[p10].get(f'{p10}{"2" if san else "1"}{bun:04d}{ji:04d}') or None
        out.append(dict(n=nm, by=by, x=xy[0], y=xy[1], ppm=statistics.median(v), k=len(v), hh=h, sgg=sgg, last=last))
    return out


def size_beta(cs):
    """같은 구 안에서 log(㎡당 시세) ~ β·log(세대수) 기울기 (구별 평균을 빼서 입지 차이 제거). 0~0.2로 제한"""
    by = defaultdict(list)
    for c in cs:
        if c['hh'] and c['hh'] >= 30: by[c['sgg']].append((math.log(c['hh']), math.log(c['ppm'])))
    xs, ys = [], []
    for v in by.values():
        if len(v) < 3: continue
        mx, my = sum(a for a, _ in v) / len(v), sum(b for _, b in v) / len(v)
        xs += [a - mx for a, _ in v]; ys += [b - my for _, b in v]
    if len(xs) < 20: return 0.0, len(xs)
    b = sum(x * y for x, y in zip(xs, ys)) / sum(x * x for x in xs)
    return min(max(b, 0.0), 0.2), len(xs)


def main():
    loc = Locator()
    cs = complexes(loc)
    beta, nb = size_beta(cs)
    zs = json.loads((OUT / 'zones.geojson').read_text(encoding='utf-8'))['features']
    out = {}
    for i, f in enumerate(zs):
        x, y = f['geometry']['coordinates']
        pr = f['properties']
        zh = pr.get('bh') or pr.get('pu') or (round(pr['ba'] * 2.5 * 0.8 / 95) if pr.get('ba') else None)  # 계획 세대 (없으면 면적×용적률 250%로 추정)
        kx, ky = M2(y)
        near = sorted(((math.hypot((c['x'] - x) * kx, (c['y'] - y) * ky), c) for c in cs), key=lambda t: t[0])
        near = [(d, c) for d, c in near if d <= 2000]
        if not near: continue
        adj = lambda c: (zh / c['hh']) ** beta if zh and c['hh'] and beta else 1.0  # 단지 규모 보정 (구역 계획 세대 vs 비교 단지)
        wavg = lambda L, f: sum(f(c) / max(d, 200) for d, c in L) / sum(1 / max(d, 200) for d, _ in L)  # 200m 안은 같은 가중
        top = near[:5]
        ppm0 = wavg(top, lambda c: c['ppm'])
        ppm = wavg(top, lambda c: c['ppm'] * adj(c))
        o = dict(ppm=round(ppm), n=len(top), hh=zh, hest=0 if (pr.get('bh') or pr.get('pu')) else 1, adj=round(ppm / ppm0 - 1, 3))
        for b in BANDS:
            L = [(d, c) for d, c in near if b in c['last']][:5]
            if L:
                o[f'v{b}'] = round(wavg(L, lambda c: c['last'][b][2] * adj(c)) / 100) * 100
                o[f'n{b}'] = len(L)
            else:
                o[f'v{b}'] = round(ppm * b / 100) * 100; o[f'n{b}'] = 0  # 그 평형 거래가 없으면 ㎡당 중위로
        show = sorted({id(c): (d, c) for d, c in top[:3] + [(d, c) for d, c in near if 84 in c['last']][:2]}.values(), key=lambda t: t[0])
        lp = lambda c, b: list(c['last'][b][::2]) if b in c['last'] else [None, None]  # [연월, 금액]
        o['comps'] = [[c['n'], round(d), c['by'], lp(c, 84)[1], lp(c, 84)[0], c['hh'], lp(c, 59)[1], lp(c, 59)[0]] for d, c in show]
        out[str(i)] = o
    meta = dict(basis='반경 2km 안 준공 10년 이내 아파트의 같은 평형(전용 59㎡형 55~64㎡, 84㎡형 80~89㎡) 가장 최근 매매가(24개월 안), 가까운 5곳 거리 역가중, 단지 규모 보정',
                n_complex=len(cs), beta=round(beta, 3), n_beta=nb, asof=str(date.today()))
    (OUT / 'zvalue.json').write_text(json.dumps(dict(meta=meta, z=out), ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'신축 비교 단지 {len(cs)}곳 (세대수 확인 {sum(1 for c in cs if c["hh"])}) · 단지 규모 탄력성 β={beta:.3f} (단지 {nb}곳, 세대수 2배 → ㎡당 {2 ** beta - 1:+.1%}) → 구역 {len(out)}/{len(zs)}곳 완공 가치 추정', flush=True)
    print(f"  같은 평형 최근 거래로 계산: 84㎡ {sum(1 for v in out.values() if v['n84'])}곳 · 59㎡ {sum(1 for v in out.values() if v['n59'])}곳 (나머지는 ㎡당 중위 환산)", flush=True)
    vs = sorted(v['v84'] for v in out.values())
    if vs: print(f"  84㎡ 중위 {vs[len(vs) // 2] / 1e4:.1f}억 (10% {vs[len(vs) // 10] / 1e4:.1f}억 ~ 90% {vs[len(vs) * 9 // 10] / 1e4:.1f}억)", flush=True)


if __name__ == '__main__':
    main()
