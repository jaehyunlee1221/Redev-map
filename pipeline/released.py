"""서울시 도시계획(UPIS) 데이터 → 모델용 해제 구역 목록 + 원본 보관
  - upisRebuild (OA-20281 도시계획 정비사업 현황): 1970년대~현재 정비구역 결정고시 이력 (신설·변경·폐지·실효)
    → '폐지·실효' = 정비구역 해제. 같은 이름의 이전 '신설'로 지정연도 추정
  - upisNewtown (OA-20286 재정비촉진사업): 뉴타운 촉진구역·존치구역 해제도 같은 방식
  - 나머지 UPIS·서울플랜+ 데이터는 원본만 받아 data/raw/upis/ 에 보관 (모델 변수 후보)
  위치: 위치(PSTN_NM) 지번 → 필지 대표점 (redev.Locator)
  python -m pipeline.released  → data/raw/released.json"""
import os, re, json, statistics
from collections import Counter
import requests
from .common import RAW
from .redev import Locator

K = os.environ.get('SEOUL_API_KEY', '')
U = 'http://openapi.seoul.go.kr:8088/{k}/json/{s}/{a}/{b}/'
SERVICES = {  # 서비스명: 설명 (열린데이터광장 OA 번호)
    'upisRebuild': '정비사업 결정고시 이력 (OA-20281)',
    'upisNewtown': '재정비촉진사업 결정고시 이력 (OA-20286)',
    'upisUrbanDev': '도시개발사업 결정고시 이력',
    'upisHistory': '지구단위계획 결정 이력 (OA-20282)',
    'upisDistUnitPlan': '지구단위계획 정보 (OA-20280)',
    'upisEtcProj': '도시계획 기타사업 (OA-20285)',
    'vnBsnsNmtn': '서울플랜+ 정비사업 현황 (OA-23112)',
    'vnBsnsSmalNmtn': '서울플랜+ 소규모정비사업 현황 (OA-23113)',
    'vnBsnsRrgnPrmt': '서울플랜+ 재정비촉진사업 현황 (OA-23114)',
    'vnBsnsSttAr': '서울플랜+ 역세권사업 현황 (OA-23115)',
    'livingZone500Info': '생활권 중심지 (OA-15531)',
}


def fetch(s, cap=60000):
    """서비스 전체 → data/raw/upis/{s}.json. 실패하면 지난번 것"""
    p = RAW / 'upis' / f'{s}.json'
    if not K: return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
    rows, a, n = [], 1, None
    try:
        while n is None or a <= min(n, cap):
            d = requests.get(U.format(k=K, s=s, a=a, b=a + 999), timeout=90).json()
            x = d.get(s)
            if not x:
                if (d.get('RESULT') or {}).get('CODE') == 'INFO-200': break
                raise RuntimeError(str(d)[:200])
            n = int(x.get('list_total_count') or 0)
            rows += x.get('row') or []
            a += 1000
    except Exception as e:
        print(f'{s} 실패 → 지난번 것 사용: {e}', flush=True)
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else []
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    print(f'{s} ({SERVICES.get(s, "")}): {len(rows)}건', flush=True)
    return rows


ymd = lambda r: r['RPT_MNG_CD'][8:16]  # 관리코드 안의 고시일 (11000AGZ20171016xxxx)


def norm(s):
    """구역 이름 → 비교용 ('신길6재정비촉진구역 주택재개발' → '신길6')"""
    s = re.sub(r'\(.*?\)|\s', '', s or '')
    for w in ('재정비촉진구역', '재정비촉진', '존치관리구역', '주택재개발', '주택재건축', '도시환경정비', '주거환경개선', '주거환경관리', '도시정비형',
              '주거정비형', '재개발', '재건축', '정비사업', '정비구역', '정비예정구역', '사업구역', '구역', '지구', '사업', '해제', '정비'):
        s = s.replace(w, '')
    return s.replace('제', '')


def released(rows, loc, gap=None):
    """폐지·실효 고시 (2010년~) → [{n, a, gu, t, rd, zd, ref, area, x, y, loc, kind}]"""
    gus = set(loc.gus)
    born = {}
    for r in rows:
        if r['RPT_TYPE'] == '신설' and ymd(r) >= '1995': born.setdefault(norm(r['RGN_NM']), []).append(ymd(r))
    out, seen = [], set()
    for r in sorted(rows, key=ymd):
        d, nm = ymd(r), (r.get('RGN_NM') or '').strip()
        if r['RPT_TYPE'] not in ('폐지', '실효') or not ('2010' <= d < '2100') or re.search('개발행위|지형도면', nm): continue
        k = norm(nm)
        if re.search('촉진지구$', r.get('SCLSF') or ''): continue  # 지구 전체(창신·숭인 등) → 안의 구역들이 따로 있음
        if (k or nm, d[:4]) in seen: continue  # 같은 구역 중복 고시 (정비사업·촉진사업 양쪽 등)
        seen.add((k or nm, d[:4]))
        zd = max((x for x in born.get(k, []) if x < d), default=None) if k else None
        a = (r.get('PSTN_NM') or '').strip()
        gu = r['LOGVM'] if r['LOGVM'] in gus else next((g for g in gus if g in a), None)
        xy, how = loc.find(gu, a) if a else (None, None)
        area = next((float(v) for v in (r.get('AREA_EXS'), r.get('AREA_CHG')) if re.fullmatch(r'[\d.]+', v or '') and float(v) > 500), None)
        sc = r.get('SCLSF') or ''
        kind = ('예정' if '예정' in nm else '관리' if re.search('주거환경', sc + nm) else '촉진' if '촉진' in nm else
                '재건축' if '재건축' in sc else '재개발')
        out.append(dict(n=nm, a=a, gu=gu, t=sc, rd=f'{d[:4]}-{d[4:6]}-{d[6:]}', zd=zd and f'{zd[:4]}-{zd[4:6]}-{zd[6:]}',
                        area=area, x=xy and xy[0], y=xy and xy[1], loc=how, kind=kind))
    gaps = [int(o['rd'][:4]) - int(o['zd'][:4]) for o in out if o['zd']]
    gap = gap or (round(statistics.median(gaps)) if gaps else 6)
    for o in out: o['ref'] = int(o['zd'][:4]) if o['zd'] else int(o['rd'][:4]) - gap  # 지정연도 (모르면 해제연도 - 중위 기간)
    print(f'해제 {len(out)}개 · 위치 찾음 {sum(1 for o in out if o["x"])} · 지정일 찾음 {len(gaps)} (지정→해제 중위 {gap}년)', flush=True)
    print('  유형:', dict(Counter(o['kind'] for o in out)), '· 해제연도:', dict(sorted(Counter(o['rd'][:4] for o in out).items())), flush=True)
    return out


def main():
    data = {s: fetch(s) for s in SERVICES}
    rel = released(data['upisRebuild'] + data['upisNewtown'], Locator())
    (RAW / 'released.json').write_text(json.dumps(rel, ensure_ascii=False), encoding='utf-8')
    for o in [o for o in rel if not o['x']][:15]: print('  위치 못 찾음:', o['n'], '|', o['a'], '|', o['gu'], flush=True)


if __name__ == '__main__':
    main()
