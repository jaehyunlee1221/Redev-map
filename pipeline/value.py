"""사업이 끝났을 때의 가치 (현재 시세 기준): 구역 주변 신축 아파트 실거래로 '새 아파트 84㎡ 지금 시세' 추정
  - 신축 = 준공 10년 이내, 최근 24개월 매매, 전용 59~114㎡ (계약 해제 제외)
  - 단지 위치: 실거래의 법정동·지번 → 필지 대표점 (redev.Locator)
  - 구역별: 2km 안 가까운 신축 단지 최대 5곳을 거리 역가중 평균 → ㎡당 시세 × 84㎡
  python -m pipeline.value  → site/data/zvalue.json {meta, z: {구역 index: {ppm, v84, n, comps: [[단지, 거리m, 준공, 84㎡ 환산 만원, 거래 수]]}}}"""
import json, math, statistics
from collections import defaultdict
from datetime import date
from .common import RAW, OUT
from .redev import Locator

M2 = lambda y: (111320 * math.cos(math.radians(y)), 110540)


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
            if r.get('cdealType') or not (59 <= ar <= 114) or t.year - by > 10: continue
            agg[(p.parent.name, r['umdNm'], r['jibun'], r['aptNm'], by)].append(amt / ar)
    out = []
    for (sgg, umd, jb, nm, by), v in agg.items():
        if len(v) < 2: continue
        xy, _ = loc.find(gu.get(sgg), f'{umd} {jb}')
        if xy: out.append(dict(n=nm, by=by, x=xy[0], y=xy[1], ppm=statistics.median(v), k=len(v)))
    return out


def main():
    loc = Locator()
    cs = complexes(loc)
    zs = json.loads((OUT / 'zones.geojson').read_text(encoding='utf-8'))['features']
    out = {}
    for i, f in enumerate(zs):
        x, y = f['geometry']['coordinates']
        kx, ky = M2(y)
        near = sorted(((math.hypot((c['x'] - x) * kx, (c['y'] - y) * ky), c) for c in cs), key=lambda t: t[0])
        near = [(d, c) for d, c in near if d <= 2000][:5]
        if not near: continue
        w = [1 / max(d, 200) for d, _ in near]  # 200m 안은 같은 가중
        ppm = sum(wi * c['ppm'] for wi, (_, c) in zip(w, near)) / sum(w)
        out[str(i)] = dict(ppm=round(ppm), v84=round(ppm * 84 / 100) * 100, n=len(near),
                           comps=[[c['n'], round(d), c['by'], round(c['ppm'] * 84 / 100) * 100, c['k']] for d, c in near[:3]])
    meta = dict(basis='반경 2km 안 준공 10년 이내 아파트, 최근 24개월 매매, 전용 59~114㎡ → 84㎡ 환산, 가까운 5곳 거리 역가중', n_complex=len(cs), asof=str(date.today()))
    (OUT / 'zvalue.json').write_text(json.dumps(dict(meta=meta, z=out), ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'신축 비교 단지 {len(cs)}곳 → 구역 {len(out)}/{len(zs)}곳 완공 가치 추정', flush=True)
    vs = sorted(v['v84'] for v in out.values())
    if vs: print(f"  84㎡ 환산 중위 {vs[len(vs) // 2] / 1e4:.1f}억 (10% {vs[len(vs) // 10] / 1e4:.1f}억 ~ 90% {vs[len(vs) * 9 // 10] / 1e4:.1f}억)", flush=True)


if __name__ == '__main__':
    main()
