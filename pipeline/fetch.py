"""원천데이터 수집. 동 단위로 저장하고 기한 내 받은 건 건너뛰므로, 끊겨도 다시 돌리면 이어받음.
  PC(국내 IP)   python -m pipeline.fetch seoul+seongnam vworld  → data/seed/{시군구}/*.json.gz (커밋해서 올림)
                 python -m pipeline.fetch test check            → 각 API가 되는지 점검만
  GitHub        python -m pipeline.fetch seeded bldgs          → data/raw/{시군구}/*_bldgs.json"""
import os, sys, time, subprocess
import numpy as np
import requests
import shapely
from shapely.geometry import shape, mapping
from .common import regions, ROOT, RAW, SEED, rd, wr
from .metrics import agg_owners

VW = 'https://api.vworld.kr/req/data'
NED = 'https://api.vworld.kr/ned/data/getPossessionAttr'
BH = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo'
VK, DK, DOM = (os.environ.get(k, '') for k in ('VWORLD_KEY', 'DATA_GO_KR_KEY', 'VWORLD_DOMAIN'))
DAYS = dict(dongs=90, parcels=90, zones=90, owners=30, bldgs=25)  # 이 기간 안에 받은 파일은 건너뜀
ERR = []


def get(url, **p):
    for i in range(4):
        try:
            r = requests.get(url, params=p, timeout=90)
            r.raise_for_status()
            return r.json()
        except ValueError:
            raise RuntimeError(f'JSON 아님: {r.text[:300]}')
        except requests.RequestException:
            if i == 3: raise
            time.sleep(3 * 2 ** i)


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


def ned(pnu):  # 토지소유정보 (PNU 앞자리로 조회)
    out, page = [], 1
    while True:
        j = get(NED, key=VK, domain=DOM, pnu=pnu, format='json', numOfRows=1000, pageNo=page)
        j = j.get('possessions', j)
        if 'field' not in j and 'totalCount' not in j: raise RuntimeError(f'토지소유정보 {pnu}: {str(j)[:300]}')
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


def feat(f, nd=7, **props):  # 좌표 반올림 + 필요한 속성만 남김
    g = shapely.transform(shape(f['geometry']), lambda c: np.round(c, nd))
    return dict(type='Feature', geometry=mapping(g), properties=props)


def owners(p10):  # 원본 행은 저장하지 않고 필지별 집계만 남김
    rows = {}
    for r in ned(p10): rows.setdefault(r['pnu'], []).append(r)
    return {pnu: agg_owners(rs) for pnu, rs in rows.items()}


def run(path, fn, days):
    if path.exists() and time.time() - path.stat().st_mtime < days * 86400: return '-'
    try:
        data = fn()
        wr(path, data)
        return len(data)
    except Exception as e:
        ERR.append(f'{path.name}: {e}')
        return 'ERR'


def push(sgg):
    """PUSH=1이면 구 하나 끝날 때마다 올림 → 지도가 구 단위로 바로바로 갱신"""
    if not os.environ.get('PUSH'): return
    git = lambda *a: subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True)
    git('add', 'data/seed')
    if git('diff', '--cached', '--quiet').returncode == 0: return
    git('commit', '-q', '-m', f'브이월드 데이터 갱신: {sgg}')
    git('pull', '--rebase', '-q')
    r = git('push', '-q')
    print(f'{sgg} 업로드 ' + ('완료' if r.returncode == 0 else f'실패: {r.stderr.strip()[:200]}'), flush=True)


def check(sgg):
    """API별로 한두 건만 불러보고 결과 출력"""
    def t(name, fn):
        try: print(f'[OK] {name}: {fn()}', flush=True)
        except Exception as e: print(f'[실패] {name}: {str(e)[:300]}', flush=True)
    ds = []
    t('읍면동 목록', lambda: len(ds.extend(vw('LT_C_ADEMD_INFO', attrFilter=f'emd_cd:like:{sgg}')) or ds))
    if not ds: return
    p10 = ds[0]['properties']['emd_cd'] + '00'
    box = 'BOX({},{},{},{})'.format(*shape(ds[0]['geometry']).bounds)
    one = get(VW, service='data', request='GetFeature', data='LP_PA_CBND_BUBUN', key=VK, domain=DOM, format='json',
              size=1, attrFilter=f'pnu:like:{p10}')['response']
    t(f'연속지적도 ({p10})', lambda: f"{one['status']}, 총 {one.get('record', {}).get('total')}건")
    t('용도지역', lambda: f"{len(vw('LT_C_UQ111', geomFilter=box))}개 구역")
    pnu = one['result']['featureCollection']['features'][0]['properties']['pnu'] if one['status'] == 'OK' else p10
    for q in (p10, pnu):
        t(f'토지소유정보 pnu={q}', lambda: (lambda j: f"총 {j.get('totalCount')}건, 예시 {(j.get('field') or [{}])[0]}")(
            get(NED, key=VK, domain=DOM, pnu=q, format='json', numOfRows=1, pageNo=1).get('possessions', {})))
    if DK: t('건축물대장', lambda: f"{len(bh(sgg, p10[5:]))}건")


def main(arg, mode):
    if os.name == 'nt':  # 윈도우: 수집 중 절전 방지
        import ctypes; ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    if mode == 'check': return check(regions(arg)[0])
    for sgg in regions(arg):
        if mode == 'vworld':
            run(SEED / sgg / 'dongs.json.gz', lambda: [feat(f, 6, **{k: f['properties'].get(k, '') for k in ('emd_cd', 'full_nm', 'emd_kor_nm')})
                                                       for f in vw('LT_C_ADEMD_INFO', attrFilter=f'emd_cd:like:{sgg}')
                                                       if f['properties']['emd_cd'].startswith(sgg)], DAYS['dongs'])
        ds = rd(sgg, 'dongs.json') or []
        print(sgg, f'{len(ds)}개 동', flush=True)
        for f in ds:
            emd = f['properties']['emd_cd']
            p10, box = emd + '00', 'BOX({},{},{},{})'.format(*shape(f['geometry']).bounds)
            if mode == 'vworld':
                base, ext = SEED / sgg, '.json.gz'
                jobs = dict(parcels=lambda: [feat(x, pnu=x['properties']['pnu'], jibun=x['properties'].get('jibun', ''))
                                             for x in vw('LP_PA_CBND_BUBUN', attrFilter=f'pnu:like:{p10}')
                                             if x['properties']['pnu'].startswith(p10)],
                            zones=lambda: [feat(x, 6, uname=x['properties'].get('uname', '')) for x in vw('LT_C_UQ111', geomFilter=box)],
                            owners=lambda: owners(p10))
            else:
                base, ext = RAW / sgg, '.json'
                jobs = dict(bldgs=lambda: bh(sgg, emd[5:] + '00'))
            res = {k: run(base / f'{p10}_{k}{ext}', fn, DAYS[k]) for k, fn in jobs.items()}
            print(sgg, emd, f['properties'].get('emd_kor_nm', ''), res, flush=True)
        if mode == 'vworld': push(sgg)
    if ERR: sys.exit(f'{len(ERR)}건 실패 (다시 실행하면 실패한 것만 다시 받음)\n' + '\n'.join(ERR[:20]))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'test', sys.argv[2] if len(sys.argv) > 2 else 'vworld')
