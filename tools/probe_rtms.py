"""data.go.kr 국토부 실거래 API 중 어떤 게 이 키로 활용승인돼 있는지 확인 (GitHub Actions에서)"""
import os, requests, xml.etree.ElementTree as ET
K = os.environ.get('DATA_GO_KR_KEY', '')
APIS = {'아파트 매매': 'RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev', '아파트 전월세': 'RTMSDataSvcAptRent/getRTMSDataSvcAptRent',
        '연립다세대 매매': 'RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade', '연립다세대 전월세': 'RTMSDataSvcRHRent/getRTMSDataSvcRHRent',
        '단독/다가구 매매': 'RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade', '단독/다가구 전월세': 'RTMSDataSvcSHRent/getRTMSDataSvcSHRent',
        '분양권·입주권 전매': 'RTMSDataSvcSilvTrade/getRTMSDataSvcSilvTrade', '토지 매매': 'RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade'}
for nm, path in APIS.items():
    try:
        r = requests.get(f'https://apis.data.go.kr/1613000/{path}', params=dict(serviceKey=K, LAWD_CD='11290', DEAL_YMD='202509', numOfRows=3, pageNo=1), timeout=40)
        try:
            x = ET.fromstring(r.content); code = x.findtext('.//resultCode') or x.findtext('.//returnReasonCode'); msg = x.findtext('.//resultMsg') or x.findtext('.//returnAuthMsg')
            it = x.find('.//item'); f = [c.tag for c in it] if it is not None else []
            print(f'{nm}: {code} {msg} 총 {x.findtext(".//totalCount")} 필드 {f[:25]}', flush=True)
        except ET.ParseError: print(f'{nm}: HTTP {r.status_code} {r.text[:150]}', flush=True)
    except Exception as e: print(f'{nm}: {e}', flush=True)
