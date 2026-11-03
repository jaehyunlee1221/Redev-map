"""서울 열린데이터광장 조사용 (GitHub Actions에서 실행: 이 서버는 해외 차단 없음)
  1) 카탈로그(SearchCatalogService)에서 제목 키워드로 데이터셋(OA-xxxx) 찾기
  2) 입출력 인자 메타 서비스로 Open API 서비스명 찾기 (이름 후보 여러 개 시도)
  3) 서비스명 후보를 직접 호출해 존재 여부·건수·컬럼·값 분포 출력
  4) 지정한 서비스는 전체를 받아 gzip+base64로 로그에 덤프 (DUMP <이름> ...)
  python tools/probe_seoul.py [서비스명 ...]"""
import os, re, sys, json, gzip, base64, collections, requests

K = os.environ.get('SEOUL_API_KEY') or 'sample'
U = 'http://openapi.seoul.go.kr:8088/{k}/json/{s}/{a}/{b}/{x}'
TITLES = ['정비사업', '재정비', '촉진', '도시개발', '결정고시', '도시계획', '생활권', '시행계획', '용도지역', '지구단위', '소규모', '역세권', '해제', '재개발', '재건축']


def call(s, a=1, b=5, x=''):
    try: d = requests.get(U.format(k=K, s=s, a=a, b=b, x=x), timeout=60).json()
    except Exception as e: return None, f'{type(e).__name__}: {str(e)[:120]}'
    if s in d: return d[s], None
    return None, json.dumps(d, ensure_ascii=False)[:200]


def show(s, x, rows):
    print(f'--- {s}: 총 {x.get("list_total_count")}건, 컬럼 {list(rows[0].keys()) if rows else None}')
    for k in (rows[0].keys() if rows else []):
        vs = collections.Counter(str(r.get(k)) for r in rows)
        if 1 < len(vs) <= 40: print(f'  {k}: {dict(vs.most_common(40))}')
    for r in rows[:3]: print('  예시', json.dumps(r, ensure_ascii=False)[:800])
    hits = [r for r in rows if '해제' in json.dumps(r, ensure_ascii=False)]
    print(f'  "해제" 포함 {len(hits)}행', [json.dumps(h, ensure_ascii=False)[:300] for h in hits[:3]], flush=True)


def fetch_all(s):
    x, err = call(s, 1, 1)
    if not x: return print(s, '실패', err)
    n, rows = int(x.get('list_total_count') or 0), []
    for a in range(1, n + 1, 1000):
        y, err = call(s, a, min(a + 999, n))
        if not y: print(s, a, '실패', err); break
        rows += y.get('row') or []
    show(s, x, rows)
    print(f'DUMP {s} ' + base64.b64encode(gzip.compress(json.dumps(rows, ensure_ascii=False).encode())).decode(), flush=True)


if len(sys.argv) > 1 and sys.argv[1] == 'only':  # 서비스명을 알 때: 그것만 조회·덤프
    for s in sys.argv[2:]:
        x, err = call(s, 1, 1)
        if not x: print(s, '실패', err, flush=True); continue
        n = int(x.get('list_total_count') or 0)
        if n <= 30000: fetch_all(s)
        else:
            y, err = call(s, 1, 1000); show(s, x, (y or {}).get('row') or [])
    sys.exit()

print('== 1) 카탈로그', flush=True)
cat = {}
for t in TITLES:
    x, err = call('SearchCatalogService', 1, 200, f'%20/{t}')
    if not x: print(t, err); continue
    for r in x.get('row') or []:
        cat.setdefault(r.get('INF_ID') or r.get('infId'), r)
first = next(iter(cat.values()), None)
print('카탈로그 컬럼', list(first.keys()) if first else None)
for i, r in sorted(cat.items(), key=lambda z: str(z[0])):
    nm = r.get('INF_NM') or r.get('infNm')
    if re.search('정비|재개발|재건축|촉진|개발사업|고시|도시계획|생활권|용도지역|지구단위|역세권|해제', nm or ''):
        print(i, nm, '|', r.get('SRV_TYPE') or r.get('srvType'), '|', r.get('MNG_STATION_NAME') or r.get('mngStationName'), '|', r.get('DATA_LT_NM') or r.get('dataLtNm'), flush=True)
        if r is first or 'upis' in json.dumps(r).lower(): print('  ', json.dumps(r, ensure_ascii=False)[:600])

print('== 2) 입출력 인자 메타', flush=True)
ids = [i for i, r in cat.items() if re.search('정비|촉진|개발사업|고시|도시계획|생활권|용도지역|지구단위|역세권|해제', (r.get('INF_NM') or r.get('infNm') or ''))]
for meta in ('SearchOpenAPIIOValueService', 'SearchOpenAPIIOService', 'SearchOpenAPIInfoService', 'OpenAPIIOValue', 'SearchOpenApiIOValue'):
    x, err = call(meta, 1, 50, ids[0] if ids else 'OA-2192')
    print(meta, '→', (json.dumps(x, ensure_ascii=False)[:600] if x else err), flush=True)
    if x:
        for i in ids:
            y, err = call(meta, 1, 100, i)
            if y: print(i, json.dumps(y.get('row') or [], ensure_ascii=False)[:1500], flush=True)
        break

print('== 3) 서비스명 후보', flush=True)
base = ['Rebuild', 'Redev', 'Redevelop', 'Renewal', 'Renew', 'Jjb', 'Promotion', 'Promote', 'ReProm', 'Develop', 'Dvlp', 'UrbanDev', 'UrbanDevelop', 'DevBiz',
        'Notice', 'Decision', 'Decsn', 'Gosi', 'Announce', 'Etc', 'EtcBiz', 'Other', 'OtherBiz', 'LifeCenter', 'Center', 'LifeZone', 'Living', 'ExecPlan', 'Exec',
        'Execute', 'PlanExec', 'Public', 'History', 'Hist', 'PlanHist', 'UseZone', 'Zone', 'Uq', 'District', 'DistrictUnit', 'DistrictPlan', 'Dup', 'Jgdw',
        'Small', 'SmallRebuild', 'SmallRedev', 'SmallScale', 'Station', 'StationArea', 'Yeoksegwon', 'Release', 'Cancel', 'Rebuild2', 'Biz', 'Project']
cands = list(dict.fromkeys(sys.argv[1:] + [p + b for b in base for p in ('upis', 'Upis')]))
found = []
for s in cands:
    x, err = call(s, 1, 5)
    if x: found.append(s); show(s, x, x.get('row') or [])
    else: print(s, (err or '')[:110])
print('있는 서비스:', found, flush=True)

print('== 4) 전체 덤프', flush=True)
for s in dict.fromkeys(['upisRebuild'] + [f for f in found if f != 'upisRebuild']): fetch_all(s)
