"""원천데이터 수집 → data/raw/{시군구}/{법정동10자리}_{parcels|zones|owners|bldgs}.json
25일 이내 받은 파일은 건너뛰므로 중간에 끊겨도 다시 돌리면 이어서 받음."""
import os, sys, json, time
import requests
from shapely.geometry import shape
from .common import regions, RAW

VW = 'https://api.vworld.kr/req/data'
NED = 'https://api.vworld.kr/ned/data/getPossessionAttr'
BH = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo'
VK, DK = os.environ['VWORLD_KEY'], os.environ['DATA_GO_KR_KEY']
DOM = os.environ.get('VWORLD_DOMAIN', '')
MAX_AGE = 25 * 86400
ERR = []


def get(url, **p):
    for i in range(5):
        try:
            r = requests.get(url, params=p, timeout=90)
            r.raise_for_status()
            break
        except requests.RequestException:
            if i == 4: raise
            time.sleep(3 * 2 ** i)
    try:
        return r.json()
    except ValueError:
        raise RuntimeError(f'{url} 응답 오류: {r.text[:300]}')


def vw(layer, **flt):  # 브이월드 2D 데이터 (연속지적도, 용도지역, 읍면동)
    out, page = [], 1
    while True:
        j = get(VW, service='data', request='GetFeature', data=layer, key=VK, domain=DOM,
                format='json', crs='EPSG:4326', size=1000, page=page, **flt)['response']
        if j['status'] == 'NOT_FOUND': return out
        if j['status'] != 'OK': raise RuntimeError(f'{layer} {flt}: {j.get("error")}')
        out += j['result']['featureCollection']['features']
        if page >= int(j['page']['total']): return out
        page += 1


def ned(pnu):  # 토지소유정보 (법정동 단위 PNU 앞자리로 조회)
    out, page = [], 1
    while True:
        j = get(NED, key=VK, domain=DOM, pnu=pnu, format='json', numOfRows=1000, pageNo=page)['possessions']
        if 'field' not in j and 'totalCount' not in j: raise RuntimeError(f'토지소유정보 {pnu}: {j}')
        rows = j.get('field') or []
        out += rows
        if not rows or page * 1000 >= int(j['totalCount']): return out
        page += 1


def bh(sgg, bjd):  # 건축물대장 표제부
    out, page = [], 1
    while True:
        b = get(BH, serviceKey=DK, sigunguCd=sgg, bjdongCd=bjd, numOfRows=100, pageNo=page, _type='json')['response']
        if b['header']['resultCode'] not in ('00', '0'): raise RuntimeError(f'건축물대장 {sgg}{bjd}: {b["header"]}')
        items = (b['body'].get('items') or {}).get('item') or []
        out += items if isinstance(items, list) else [items]
        if page * 100 >= int(b['body']['totalCount']): return out
        page += 1


def cached(path, fn):
    if path.exists() and time.time() - path.stat().st_mtime < MAX_AGE:
        return json.loads(path.read_text(encoding='utf-8'))
    data = fn()
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return data


def main(arg):
    for sgg in regions(arg):
        d = RAW / sgg
        d.mkdir(parents=True, exist_ok=True)
        dongs = cached(d / 'dongs.json', lambda: [f for f in vw('LT_C_ADEMD_INFO', attrFilter=f'emd_cd:like:{sgg}')
                                                  if f['properties']['emd_cd'].startswith(sgg)])
        print(sgg, f'{len(dongs)}개 동', flush=True)
        for f in dongs:
            emd = f['properties']['emd_cd']
            p10, box = emd + '00', 'BOX({},{},{},{})'.format(*shape(f['geometry']).bounds)
            jobs = {'parcels': lambda: [x for x in vw('LP_PA_CBND_BUBUN', attrFilter=f'pnu:like:{p10}')
                                        if x['properties']['pnu'].startswith(p10)],
                    'zones': lambda: vw('LT_C_UQ111', geomFilter=box),
                    'owners': lambda: ned(p10),
                    'bldgs': lambda: bh(sgg, emd[5:] + '00')}
            for k, fn in jobs.items():  # 하나 실패해도 나머지 계속
                try:
                    print(sgg, emd, f['properties'].get('emd_kor_nm'), k, len(cached(d / f'{p10}_{k}.json', fn)), flush=True)
                except Exception as e:
                    ERR.append(f'{p10} {k}: {e}')
                    print('ERROR', ERR[-1], flush=True)
    if ERR: sys.exit(f'{len(ERR)}건 실패\n' + '\n'.join(ERR[:20]))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'test')
