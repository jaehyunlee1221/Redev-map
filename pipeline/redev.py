"""정비사업(재개발·재건축) 구역 → site/data/zones.geojson (구역별 대표 지번 위치에 점 + 단계·일자·세대수)
  서울: 열린데이터광장 '서울특별시 도시정비사업 통계'(OA-22856, API TbSeoulRedevStatus, 분기 갱신). 키 SEOUL_API_KEY (없으면 sample=5건)
  위치: 대표 지번(JIBUN_ADDR) → 우리가 받은 필지(PNU)의 대표점. 아직 수집 안 된 구는 건너뜀 → 구를 받을 때마다 늘어남
  python -m pipeline.redev"""
import os, re, json, sys
import requests
from shapely.geometry import shape
from .common import OUT, RAW, rd

URL = 'http://openapi.seoul.go.kr:8088/{key}/json/TbSeoulRedevStatus/{a}/{b}/'
STAGES = ('구역지정', '추진위', '조합설립', '건축심의', '사업시행', '관리처분', '이주', '착공', '준공')
DATES = dict(zd='ZONE_DESIGNATION_INIT_YMD', cm='PROMOTION_COMMITTEE_YMD', jo='ASSOCIATION_ESTABLISHMENT_YMD',
             sa='BIZ_IMPLEMENTATION_INIT_YMD', gc='MGMT_DISPOSITION_INIT_YMD', ij='MIGRATION_START_YMD', cs='CONSTRUCTION_START_YMD')


def fetch_seoul():
    key, out, a = os.environ.get('SEOUL_API_KEY') or 'sample', [], 1
    while True:
        r = requests.get(URL.format(key=key, a=a, b=a + (4 if key == 'sample' else 999)), timeout=60)  # 예시 키는 5건까지만
        try: d = r.json()
        except ValueError: raise RuntimeError(f'JSON 아님 (HTTP {r.status_code}): {r.text[:200]}')
        x = d.get('TbSeoulRedevStatus')
        if not x:
            if (d.get('RESULT') or {}).get('CODE') == 'INFO-200': return out
            raise RuntimeError(f"서울 API: {d.get('RESULT') or str(d)[:200]}")
        out += x.get('row') or []
        if key == 'sample' or len(out) >= int(x['list_total_count']) or not x.get('row'): return out
        a += 1000


def parse_addr(s, gus):
    """'서울특별시 서초구 잠원동 60-3번지 일대' / '양천구목동903' / '쌍문2동 81' → (구, 동, 본번, 부번). 산·실패는 본번 None"""
    s = re.sub(r'\s+', '', s or '')
    s = re.sub(r'^(서울특별시|서울시|서울)', '', s)
    gu = next((g for g in gus if s.startswith(g)), None)
    if gu: s = s[len(gu):]
    s = re.sub(r'([가-힣])\d+동', r'\1동', s)  # 행정동 번호 → 법정동 ('쌍문2동' → '쌍문동')
    m = re.match(r'([가-힣]+?(?:[로동]\d+가|\d+가|동|가|로))(산)?(\d+)?(?:-(\d+))?', s)
    if not m: return gu, None, None, None
    return gu, m.group(1), None if m.group(2) or not m.group(3) else int(m.group(3)), int(m.group(4) or 0)


def date(v):
    v = re.sub(r'\D', '', v or '')
    return f'{v[:4]}-{v[4:6]}-{v[6:8]}' if len(v) == 8 and v[:2] in ('19', '20') else None


def num(v):
    v = re.sub(r'[^\d]', '', str(v or ''))
    return int(v) if v else None


class Locator:
    """동 이름·지번 → 필지 대표점. dongs.geojson(빌드 결과)의 동 이름과 필지 파일을 씀"""
    def __init__(self):
        p = OUT / 'dongs.geojson'
        fs = json.loads(p.read_text(encoding='utf-8'))['features'] if p.exists() else []
        self.dong = {}  # (구, 동) → p10
        for f in fs:
            w = f['properties']['n'].split()
            if len(w) >= 3: self.dong[(w[-2], w[-1])] = f['properties']['c']
        self.gus = sorted({g for g, _ in self.dong}, key=len, reverse=True)
        self.cache = {}

    def parcels(self, p10):
        if p10 not in self.cache:
            self.cache[p10] = {f['properties']['pnu']: f for f in rd(p10[:5], f'{p10}_parcels.json') or []}
        return self.cache[p10]

    def find(self, district, addr):
        gu, dong, bun, ji = parse_addr(addr, self.gus)
        gu = gu or district
        p10 = self.dong.get((gu, dong))
        if not p10 or bun is None: return None, None
        ps = self.parcels(p10)
        pnu = f'{p10}1{bun:04d}{ji:04d}'
        if pnu in ps: hit, how = ps[pnu], '정확'
        else:  # 같은 본번 → 가장 가까운 본번
            same = [k for k in ps if k[10] == '1' and int(k[11:15]) == bun]
            near = same or sorted((k for k in ps if k[10] == '1'), key=lambda k: abs(int(k[11:15]) - bun))[:1]
            if not near: return None, None
            hit, how = ps[min(near)], '근처'
        pt = shape(hit['geometry']).representative_point()
        return [round(pt.x, 6), round(pt.y, 6)], how


def zone(r, loc):
    xy, how = loc.find((r.get('DISTRICT') or '').strip(), r.get('JIBUN_ADDR'))
    if not xy: return None
    st = (r.get('BIZ_STAGE') or '').strip()
    p = dict(n=(r.get('ZONE_NM') or '').strip(), gu=(r.get('DISTRICT') or '').strip(), t=(r.get('BIZ_TYPE') or '').strip(),
             s=st, si=STAGES.index(st) if st in STAGES else -1,
             pp=(r.get('BIZ_METHOD_PUBLIC_PRIVATE') or '').strip(), gp=(r.get('BIZ_METHOD_GENERAL_PROMOTED') or '').strip(),
             eh=num(r.get('EXISTING_HOUSEHOLDS')), bh=num(r.get('TOT_BUILT_HOUSEHOLDS')),
             sh=num(r.get('SALE_BUILT_HOUSEHOLDS')), rh=num(r.get('RENT_BUILT_HOUSEHOLDS')),
             a=(r.get('JIBUN_ADDR') or '').strip(), loc=how, **{k: date(r.get(v)) for k, v in DATES.items()})
    return dict(type='Feature', geometry=dict(type='Point', coordinates=xy), properties={k: v for k, v in p.items() if v not in (None, '')})


def main():
    cache = RAW / 'redev_seoul.json'
    try:
        rows = fetch_seoul()
        cache.parent.mkdir(parents=True, exist_ok=True)
        if len(rows) > 5 or not cache.exists(): cache.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        print(f'서울 정비사업 API 실패 → 지난번 받은 것 사용: {e}', flush=True)
        rows = json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else []
    if rows and len(rows) <= 5: print('SEOUL_API_KEY 없음 → 예시 5건만 (GitHub Secrets에 SEOUL_API_KEY 등록 필요)', flush=True)
    if rows:
        print('예시 행:', json.dumps(rows[0], ensure_ascii=False)[:800], flush=True)
        from collections import Counter
        print('단계별:', dict(Counter((r.get('BIZ_STAGE') or '').strip() for r in rows).most_common()), flush=True)
        print('유형별:', dict(Counter((r.get('BIZ_TYPE') or '').strip() for r in rows).most_common()), flush=True)
        if os.environ.get('DUMP'):  # 분석용: 원본 행을 압축해 로그로 (공개 데이터)
            import gzip, base64
            print('RAWDUMP', base64.b64encode(gzip.compress(json.dumps(rows, ensure_ascii=False).encode())).decode(), flush=True)
    loc = Locator()
    feats = [z for z in (zone(r, loc) for r in rows) if z]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'zones.geojson').write_text(json.dumps(dict(type='FeatureCollection', features=feats), ensure_ascii=False,
                                                  separators=(',', ':')), encoding='utf-8')
    print(f'정비사업 {len(rows)}개 중 {len(feats)}개 지도에 표시 (나머지는 아직 수집 안 된 구이거나 지번 불명)', flush=True)


if __name__ == '__main__':
    main()
