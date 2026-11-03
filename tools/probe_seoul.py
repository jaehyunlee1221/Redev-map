"""서울 열린데이터광장 데이터셋(OA-xxxx)의 Open API 서비스명을 찾아 컬럼·단계 분포를 출력 (조사용)
  python tools/probe_seoul.py OA-23112 OA-23114 ..."""
import os, re, sys, json, collections, requests
K = os.environ.get('SEOUL_API_KEY') or 'sample'
for oa in sys.argv[1:]:
    print(f'===== {oa}', flush=True)
    names = set()
    for tab in ('A', 'S', 'F'):
        try:
            t = requests.get(f'https://data.seoul.go.kr/dataList/{oa}/{tab}/1/datasetView.do', timeout=30).text
            names |= set(re.findall(r'8088/[^/\s"]+/(?:xml|json)/([A-Za-z0-9_]+)/', t))
            names |= set(re.findall(r'(?:SERVICE|서비스명)[^A-Za-z]{0,40}([A-Za-z][A-Za-z0-9_]{5,})', t))
            if tab == 'A': print('title:', (re.search(r'<title>(.*?)</title>', t, re.S) or [None, ''])[1].strip()[:80])
        except Exception as e: print(tab, e)
    print('후보 서비스명:', names, flush=True)
    for n in names:
        try: d = requests.get(f'http://openapi.seoul.go.kr:8088/{K}/json/{n}/1/1000/', timeout=60).json()
        except Exception as e: print(n, '실패', e); continue
        x = d.get(n)
        if not x: print(n, str(d)[:200]); continue
        rows = x.get('row') or []
        print(f'--- {n}: 총 {x.get("list_total_count")}건, 컬럼 {list(rows[0].keys()) if rows else None}')
        for k in (rows[0].keys() if rows else []):
            vs = collections.Counter(str(r.get(k)) for r in rows)
            if 1 < len(vs) <= 30: print(f'  {k}: {dict(vs.most_common(30))}')
        for r in rows[:3]: print('  예시', json.dumps(r, ensure_ascii=False)[:600])
        hits = [r for r in rows if '해제' in json.dumps(r, ensure_ascii=False)]
        print(f'  "해제" 포함 행 {len(hits)}개', [json.dumps(h, ensure_ascii=False)[:300] for h in hits[:3]], flush=True)
