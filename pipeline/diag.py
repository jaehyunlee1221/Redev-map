"""Actions 러너에서 각 API 접속 가능 여부 점검"""
import os, requests

VK, DK, DOM = os.environ['VWORLD_KEY'], os.environ['DATA_GO_KR_KEY'], os.environ.get('VWORLD_DOMAIN', '')
T = [('러너 위치', 'https://ipinfo.io/json', {}),
     ('vworld 홈', 'https://www.vworld.kr/', {}),
     ('vworld 2D BOX', 'https://api.vworld.kr/req/data', dict(service='data', request='GetFeature', data='LP_PA_CBND_BUBUN', key=VK, domain=DOM,
                                                             format='json', size=1, geomFilter='BOX(127.0,37.48,127.002,37.482)')),
     ('vworld 2D like', 'https://api.vworld.kr/req/data', dict(service='data', request='GetFeature', data='LT_C_ADEMD_INFO', key=VK, domain=DOM,
                                                              format='json', size=1, attrFilter='emd_cd:like:11650')),
     ('vworld http', 'http://api.vworld.kr/req/data', dict(service='data', request='GetFeature', data='LT_C_ADEMD_INFO', key=VK, domain=DOM,
                                                          format='json', size=1, attrFilter='emd_cd:=:11650101')),
     ('vworld NED', 'https://api.vworld.kr/ned/data/getPossessionAttr', dict(key=VK, domain=DOM, pnu='1165010100', format='json', numOfRows=1)),
     ('건축HUB', 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo', dict(serviceKey=DK, sigunguCd='11650', bjdongCd='10100',
                                                                                       numOfRows=1, _type='json'))]
for name, url, p in T:
    try:
        r = requests.get(url, params=p, timeout=30)
        print(f'[{name}] {r.status_code} {r.text[:300]!r}')
    except Exception as e:
        print(f'[{name}] EXC {type(e).__name__}: {str(e)[:200]}')
