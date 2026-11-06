"""모델 변수용 시장·입지 데이터 (GitHub에서 수집, data/raw 캐시)
  - 아파트 매매 실거래 (국토부 RTMS, DATA_GO_KR_KEY에 '아파트 매매 실거래가 상세 자료' 활용신청 필요): 구·월별
  - 지하철역 위치 (서울 열린데이터광장 subwayStationMaster, SEOUL_API_KEY)
  python -m pipeline.market [최대호출수]"""
import os, sys, re, json, time, statistics
import xml.etree.ElementTree as ET
from datetime import date
import requests
from .common import RAW, regions

RT = 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev'
ST = 'http://openapi.seoul.go.kr:8088/{key}/json/subwayStationMaster/{a}/{b}/'
DK, SK = os.environ.get('DATA_GO_KR_KEY', ''), os.environ.get('SEOUL_API_KEY', '')
FIELDS = ('aptNm', 'buildYear', 'dealAmount', 'dealYear', 'dealMonth', 'excluUseAr', 'umdNm', 'jibun', 'cdealType', 'floor')
# 투자 계산용 추가 실거래 (같은 DATA_GO_KR_KEY, 각각 data.go.kr 활용신청 필요) — 이름: (경로, 필드, 시작 연월)
EXTRA = {'rh': ('RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade',  # 연립·다세대 매매 (대지권 면적 landAr 포함)
                ('mhouseNm', 'houseType', 'buildYear', 'dealAmount', 'dealYear', 'dealMonth', 'excluUseAr', 'landAr', 'umdNm', 'jibun', 'cdealType', 'floor'), (2021, 1)),
         'rhrent': ('RTMSDataSvcRHRent/getRTMSDataSvcRHRent',  # 연립·다세대 전월세 (갭 = 매매 - 전세)
                    ('mhouseNm', 'buildYear', 'deposit', 'monthlyRent', 'dealYear', 'dealMonth', 'excluUseAr', 'umdNm', 'jibun', 'floor', 'contractType'), (2023, 1)),
         'aptrent': ('RTMSDataSvcAptRent/getRTMSDataSvcAptRent',  # 아파트 전월세 (재건축 아파트 갭)
                     ('aptNm', 'buildYear', 'deposit', 'monthlyRent', 'dealYear', 'dealMonth', 'excluUseAr', 'umdNm', 'jibun', 'floor', 'contractType'), (2023, 1)),
         'silv': ('RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade',  # 분양권·입주권 전매 → 관리처분 이후 실제 프리미엄
                  ('aptNm', 'ownershipGbn', 'dealAmount', 'dealYear', 'dealMonth', 'excluUseAr', 'umdNm', 'jibun', 'floor', 'cdealType'), (2021, 1))}


def months(start=(2006, 1)):
    y, m, t = *start, date.today()
    while (y, m) < (t.year, t.month):
        yield f'{y}{m:02d}'
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def rtms(sgg, ym, url=RT, fields=FIELDS):
    out, page = [], 1
    while True:
        for i in range(3):  # 서버가 가끔 응답이 늦음 → 재시도
            try: r = requests.get(url, params=dict(serviceKey=DK, LAWD_CD=sgg, DEAL_YMD=ym, numOfRows=1000, pageNo=page), timeout=40); break
            except requests.RequestException:
                if i == 2: raise
                time.sleep(5 * (i + 1))
        try: x = ET.fromstring(r.content)
        except ET.ParseError: raise RuntimeError(f'XML 아님 (HTTP {r.status_code}): {r.text[:200]}')
        code = x.findtext('.//resultCode') or x.findtext('.//returnReasonCode')
        if code not in ('00', '000'):
            raise RuntimeError(f"실거래 {sgg} {ym}: {code} {x.findtext('.//resultMsg') or x.findtext('.//returnAuthMsg')}")
        items = x.findall('.//item')
        out += [{k: (it.findtext(k) or '').strip() for k in fields} for it in items]
        if not items or len(out) >= int(x.findtext('.//totalCount') or 0): return out
        page += 1


def fetch_rtms(cap):
    """이미 받은 달은 건너뜀 (이번 달·지난달은 신고 기한 때문에 다시 받음). cap: 이번 실행 최대 호출 수"""
    if not DK: return print('DATA_GO_KR_KEY 없음 → 실거래 건너뜀', flush=True)
    recent, n, err = set(list(months())[-2:]), 0, 0
    for sgg in regions('seeded'):
        for ym in months():
            p = RAW / 'rtms' / sgg / f'{ym}.json'
            if p.exists() and ym not in recent: continue
            if n >= cap: return print(f'실거래: 이번 실행 한도 {cap}회 도달 → 다음 실행에 이어받음', flush=True)
            n += 1
            try: rows = rtms(sgg, ym); err = 0
            except Exception as e:
                err += 1; print(f'실거래 실패 {sgg} {ym}: {e}', flush=True)  # 실패한 달은 다음 실행 때 다시
                if err >= 8 or any(k in str(e) for k in ('LIMIT', 'SERVICE_KEY', 'ACCESS_DENIED', '등록되지')): return print(f'실거래 중단: {e}', flush=True)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        print(f'실거래 {sgg} 완료 (누적 호출 {n})', flush=True)


def fetch_stations():
    p = RAW / 'stations.json'
    if p.exists() and time.time() - p.stat().st_mtime < 90 * 86400: return
    if not SK: return print('SEOUL_API_KEY 없음 → 역 위치 건너뜀', flush=True)
    d = requests.get(ST.format(key=SK, a=1, b=1000), timeout=60).json()
    rows = (d.get('subwayStationMaster') or {}).get('row') or []
    if not rows: return print(f'역 위치 실패: {str(d)[:200]}', flush=True)
    k = rows[0].keys()
    lat = next(x for x in k if 'LAT' in x.upper()); lon = next(x for x in k if x.upper() in ('LOT', 'LNG', 'LON', 'CRDNT_X') or 'LOT' in x.upper())
    nm = next((x for x in k if 'NM' in x.upper()), None)
    st = [dict(n=r.get(nm), l=r.get('ROUTE'), x=float(r[lon]), y=float(r[lat])) for r in rows if r.get(lat) and r.get(lon)]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False), encoding='utf-8')
    print(f'지하철역 {len(st)}개', flush=True)


def summary():
    """구·동·연도별 ㎡당 매매가 중위값 (전체 / 준공 10년 이내 신축) → RAW/market.json"""
    agg = {}
    for p in sorted((RAW / 'rtms').glob('*/*.json')):
        for r in json.loads(p.read_text(encoding='utf-8')):
            if r.get('cdealType'): continue  # 계약 해제 건 제외
            try: amt, ar, yr, by = float(r['dealAmount'].replace(',', '')), float(r['excluUseAr']), int(r['dealYear']), int(r['buildYear'] or 0)
            except ValueError: continue
            v = amt / ar  # 만원/㎡
            for key in (f"{p.parent.name}|{yr}", f"{p.parent.name}|{r['umdNm']}|{yr}"):
                a = agg.setdefault(key, ([], []))
                a[0].append(v)
                if by and yr - by <= 10: a[1].append(v)
    out = {k: dict(m=round(statistics.median(a)), n=len(a), mn=round(statistics.median(b)) if len(b) >= 3 else None, nn=len(b)) for k, (a, b) in agg.items()}
    (RAW / 'market.json').write_text(json.dumps(out, ensure_ascii=False), encoding='utf-8')
    print(f'실거래 요약 {len(out)}개 (구·동·연도)', flush=True)


def fetch_extra(cap):
    """EXTRA 실거래: 활용승인 안 된 API는 첫 호출에서 건너뜀. RAW/{이름}/{구}/{연월}.json"""
    if not DK: return
    recent, n = set(list(months())[-2:]), 0
    for nm, (path, fields, start) in EXTRA.items():
        url, err, ok = f'https://apis.data.go.kr/1613000/{path}', 0, True
        for sgg in regions('seeded'):
            for ym in months(start):
                p = RAW / nm / sgg / f'{ym}.json'
                if p.exists() and ym not in recent: continue
                if n >= cap: return print(f'추가 실거래: 이번 실행 한도 {cap}회 → 다음 실행에 이어받음', flush=True)
                n += 1
                try: rows = rtms(sgg, ym, url, fields); err = 0
                except Exception as e:
                    err += 1
                    if any(k in str(e) for k in ('SERVICE_KEY', '등록되지', 'ACCESS_DENIED')): print(f'{nm}: 활용승인 안 됨 → 건너뜀 ({e})', flush=True); ok = False; break
                    if err >= 8 or 'LIMIT' in str(e): return print(f'추가 실거래 중단: {e}', flush=True)
                    continue
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            if not ok: break
        print(f'추가 실거래 {nm}: 누적 호출 {n}', flush=True)


if __name__ == '__main__':
    try: fetch_stations()
    except Exception as e: print('역 위치 실패:', e, flush=True)
    fetch_rtms(int(sys.argv[1]) if len(sys.argv) > 1 else 3000)
    if (RAW / 'rtms').exists(): summary()
    fetch_extra(int(sys.argv[2]) if len(sys.argv) > 2 else 3000)
