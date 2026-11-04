import json
from pipeline import build, common, fetch, metrics
from pipeline.metrics import agg_bldgs, agg_owners, is_old, pnu_of, YEAR

sq = lambda x, y, s=0.0003: {'type': 'Polygon', 'coordinates': [[[x, y], [x + s, y], [x + s, y + s], [x, y + s], [x, y]]]}
B = lambda bun, y, st='철근콘크리트구조', **k: {**dict(sigunguCd='99999', bjdongCd='10100', platGbCd='0', bun=bun, ji='0000',
                                                 useAprDay=y, strctCdNm=st, mainAtchGbCd='0', totArea='100'), **k}


def test_old_rules():
    assert is_old(B('1', f'{YEAR-30}0101')) and not is_old(B('1', f'{YEAR-29}0101'))
    assert is_old(B('1', f'{YEAR-20}0101', '벽돌구조'))           # 비RC 20년
    assert is_old(B('1', '')) is None and is_old(B('1', '0000')) is None
    assert pnu_of(B('12', '')) == '9999910100100120000'


def test_owner_estimate():
    rows = [dict(pnu='x', cnrsPsnSn='1', cnrsPsnCo='2', posesnSeCodeNm='개인', lndpclAr='80', lndcgrCodeNm='대'),
            dict(pnu='x', cnrsPsnSn='2', cnrsPsnCo='2', posesnSeCodeNm='개인'),
            dict(pnu='x', cnrsPsnSn='1', buldDongNm='A', buldHoNm='101', posesnSeCodeNm='개인'),
            dict(pnu='x', cnrsPsnSn='1', posesnSeCodeNm='국유지')]
    o = agg_owners(rows)
    assert (o['ol'], o['oh'], o['pub']) == (2, 3, 0)               # 공유 대표1 + 101호 / 공유 2 + 101호
    assert agg_owners([dict(posesnSeCodeNm='시·도유지')])['pub'] == 1
    assert agg_owners([]) is None


def test_bldg_agg():
    a = agg_bldgs([B('1', '19800101'), B('1', '', hoCnt='8', regstrGbCdNm='집합'), B('1', f'{YEAR-1}0101', hhldCnt='4'),
                   B('1', '19700101', mainAtchGbCd='1')])
    assert (a['nb'], a['no'], a['nu'], a['nn'], a['ho'], a['hh'], a['y0']) == (3, 1, 1, 1, 8, 4, 1980)


def test_end_to_end(tmp_path, monkeypatch):
    """PC 수집(vworld) → GitHub 수집(bldgs) → build. API는 가짜 응답으로 대체"""
    raw, seed, out = tmp_path / 'raw', tmp_path / 'seed', tmp_path / 'out'
    for m in (common, fetch): monkeypatch.setattr(m, 'RAW', raw); monkeypatch.setattr(m, 'SEED', seed)
    monkeypatch.setattr(build, 'OUT', out); monkeypatch.setattr(build, 'SEED', seed)
    F = lambda g, **p: dict(type='Feature', geometry=g, properties=p)
    layers = {'LT_C_ADEMD_INFO': [F(sq(127, 37.5, 0.01), emd_cd='99999101', full_nm='테스트동', emd_kor_nm='테스트동', x='버림'),
                                  F(sq(128, 37.5, 0.01), emd_cd='88888101')],                       # 다른 구 → 제외
              'LP_PA_CBND_BUBUN': [F(sq(127.001 + i * 0.001, 37.501), pnu=f'99999101001{i:04d}0000', jibun=f'{i}대', bonbun='x')
                                   for i in (1, 2, 3)],
              'LT_C_UQ111': [F(sq(127, 37.5, 0.01), uname='제2종일반주거지역')]}
    monkeypatch.setattr(fetch, 'vw', lambda layer, **k: layers[layer])
    LU = [dict(pnu='9999910100100010000', prposAreaDstrcCode='UQA122', prposAreaDstrcCodeNm='제2종일반주거지역', cnflcAt='1'),
          dict(pnu='9999910100100010000', prposAreaDstrcCode='UBA100', prposAreaDstrcCodeNm='정비구역', cnflcAt='1')]
    monkeypatch.setattr(fetch, 'ned', lambda p, url=fetch.NED: LU if url == fetch.LU else [
        dict(pnu='9999910100100010000', cnrsPsnSn='1', cnrsPsnCo='2', posesnSeCodeNm='개인', lndpclAr='70', lndcgrCodeNm='대'),
        dict(pnu='9999910100100010000', cnrsPsnSn='2', posesnSeCodeNm='개인')])
    monkeypatch.setattr(fetch, 'bh', lambda s, b: [B('0001', '19800101'), B('0002', '20250101', hoCnt='6', regstrGbCdNm='집합')])

    fetch.main('99999', 'vworld')
    assert sorted(p.name for p in (seed / '99999').iterdir()) == ['9999910100_landuse.json.gz', '9999910100_owners.json.gz',
                                                                  '9999910100_parcels.json.gz', '9999910100_zones.json.gz', 'dongs.json.gz']
    lu = common.rd('99999', '9999910100_landuse.json')
    assert lu['9999910100100010000'] == [['UQA122', '1'], ['UBA100', '1']] and lu['_c']['UBA100'] == '정비구역'
    assert not raw.exists()
    own = common.rd('99999', '9999910100_owners.json')
    assert list(own) == ['_v', '9999910100100010000'] and own['9999910100100010000']['oh'] == 2   # 원본 행 아닌 필지별 집계
    assert common.rd('99999', '9999910100_parcels.json')[0]['properties'] == dict(pnu='9999910100100010000', jibun='1대')
    m = (seed / '99999' / 'dongs.json.gz').stat().st_mtime
    fetch.main('99999', 'vworld')                                                                  # 기한 내 → 건너뜀
    assert (seed / '99999' / 'dongs.json.gz').stat().st_mtime == m

    fetch.main('seeded', 'bldgs')
    assert [p.name for p in (raw / '99999').iterdir()] == ['9999910100_bldgs.json']

    build.main('seeded')
    fs = {p['p'][-8:-4]: p for p in json.loads((out / 'p' / '9999910100.json').read_text())}
    nd = [json.loads(l) for l in (out / 'parcels.ndjson').read_text().splitlines()]
    assert len([f for f in nd if 'tippecanoe' not in f]) == 3 and nd[0]['geometry']['type'] == 'Polygon'
    assert fs['0001']['z'] == '제2종일반주거지역' and fs['0001']['no'] == 1 and fs['0001']['ol'] == 1 and fs['0001']['oh'] == 2
    assert 'oe' not in fs['0001']
    assert fs['0002']['ol'] == 6 and fs['0002']['oe'] == 1 and fs['0002']['jm'] == '대'   # 소유정보 없음 → 집합 호수
    assert fs['0003']['nb'] == 0 and 60 < fs['0003']['ar'] < 1000
    assert json.loads((out / 'version.json').read_text())['v']
    dg = json.loads((out / 'dongs.geojson').read_text())['features'][0]['properties']
    assert (dg['n'], dg['nb'], dg['no'], dg['r'], dg['oe']) == ('테스트동', 2, 1, 0.5, 2)


def test_regions():
    assert common.regions('test') == ['11650']
    assert common.regions('seoul+seongnam')[-3:] == ['41131', '41133', '41135'] and len(common.regions('seoul,seongnam')) == 28


def test_owner_real_format():
    """브이월드 실제 응답 형식: 없는 값은 '0000', 집합건물은 agbldgSn·층·호로 구분"""
    R = lambda sn, ag='0000', fl='0000', ho='0000', co='0', se='개인': dict(
        pnu='x', cnrsPsnSn=sn, agbldgSn=ag, buldDongNm='0000', buldFloorNm=fl, buldHoNm=ho, buldRoomNm='0000',
        cnrsPsnCo=co, posesnSeCodeNm=se, lndpclAr='59.97', lndcgrCodeNm='대', pblntfPclnd='11780000', ownshipChgDe='2015-01-05')
    o = agg_owners([R('000001', '0160', '4', '401'), R('000002', '0160', '4', '401'),   # 401호 부부 공동
                    R('000003', '0161', '4', '401'),                                    # 다른 동 건물의 401호
                    R('000004', '0160', '5', '501'), R('000005', se='시,도유지')])
    assert (o['ol'], o['oh'], o['pub'], o['gj'], o['cg']) == (3, 4, 0, 11780000, '2015-01')


def test_paging(monkeypatch):
    """페이지당 건수가 요청보다 적게 와도 끝까지 받음 / 한도 초과면 Stop"""
    pages = {1: ['a'] * 300, 2: ['b'] * 300, 3: ['c'] * 50}
    monkeypatch.setattr(fetch, 'get', lambda url, **p: {'possessions': {'totalCount': '650', 'field': pages[p['pageNo']]}})
    assert len(fetch.ned('1165010600')) == 650
    monkeypatch.setattr(fetch, 'get', lambda url, **p: {'response': {'status': 'ERROR', 'error': {'code': 'OVER_REQUEST_LIMIT'}}})
    try: fetch.vw('LT_C_UQ111'); assert False
    except fetch.Stop: pass


def test_apartment_multi_parcel(monkeypatch):
    """아파트 호별 행의 공유인수(대지 전체 공유자 수)는 무시 / 여러 필지에 걸친 단지는 대표 필지에만 셈"""
    R = lambda pnu, ho, sn='000001', co='48': dict(pnu=pnu, cnrsPsnSn=sn, cnrsPsnCo=co, agbldgSn='0001', buldDongNm='101',
                                                   buldFloorNm='1', buldHoNm=ho, buldRoomNm='0000', posesnSeCodeNm='개인')
    big = [R('A', h) for h in ('101', '102', '103', '104', '105')] + [R('A', '101', '000002')]
    small = [R('B', h) for h in ('101', '102', '103', '104')]
    land = [dict(pnu='C', cnrsPsnSn='1', cnrsPsnCo='3', posesnSeCodeNm='개인')]
    monkeypatch.setattr(fetch, 'ned', lambda p: small + land + big)
    o = fetch.owners('x')
    assert (o['A']['ol'], o['A']['oh']) == (5, 6) and o['B'] == {**o['B'], 'ol': 0, 'oh': 0, 'dp': 'A'}
    assert o['C']['oh'] == 3 and o['_v'] == fetch.VER['owners']


def test_redev_addr():
    from pipeline.redev import parse_addr
    G = ['서초구', '양천구', '중구']
    assert parse_addr('서울특별시 서초구 잠원동 60-3번지 일대', G) == ('서초구', '잠원동', 60, 3)
    assert parse_addr('양천구목동903', G) == ('양천구', '목동', 903, 0)
    assert parse_addr('쌍문2동 81번지', G) == (None, '쌍문동', 81, 0)
    assert parse_addr('중구 충무로1가 24-1', G) == ('중구', '충무로1가', 24, 1)
    assert parse_addr('서초구 방배동 산108-1', G)[2] is None


def test_zone_polys(tmp_path, monkeypatch):
    """토지이용계획 정비구역 필지 → 경계, 정비사업 점과 매칭. 붙은 덩어리에 점이 둘이면 가까운 점으로 나눔"""
    import gzip
    from pipeline import redev
    seed = tmp_path / 'seed'; monkeypatch.setattr(common, 'SEED', seed); monkeypatch.setattr(common, 'RAW', tmp_path / 'raw')
    d = seed / '99999'; d.mkdir(parents=True)
    w = lambda n, x: (d / n).write_bytes(gzip.compress(json.dumps(x).encode()))
    w('dongs.json.gz', [dict(type='Feature', geometry=sq(127, 37.5, 0.01), properties=dict(emd_cd='99999101'))])
    pn = lambda i: f'99999101001{i:04d}0000'
    w('9999910100_parcels.json.gz', [dict(type='Feature', geometry=sq(127.001 + i * 0.0003, 37.501), properties=dict(pnu=pn(i))) for i in range(6)])
    w('9999910100_landuse.json.gz', {'_v': 1, '_c': {'A': '정비구역', 'B': '제2종일반주거지역'},
                                     **{pn(i): [['B', '1'], ['A', '1']] for i in range(4)}, pn(4): [['B', '1']]})
    P = lambda x: dict(type='Feature', geometry=dict(type='Point', coordinates=[x, 37.50115]), properties=dict(n=f'z{x}', s='추진위', si=1, loc='정확'))
    feats = [P(127.00115), P(127.00205), P(127.1)]
    polys, rep = redev.zone_polys(feats, redev.Locator())
    assert sorted(rep) == [0, 1] and len(polys) == 2                      # 4필지 덩어리 하나 → 두 구역으로 나뉨, 먼 점은 매칭 안 됨
    assert round(sum(shape_area(p) for p in polys) / (0.0003 ** 2)) == 4


def shape_area(f):
    from shapely.geometry import shape
    return shape(f['geometry']).area


def test_released():
    from pipeline.released import released, norm
    assert norm('신길6재정비촉진구역 주택재개발') == '신길6' == norm('신길제6구역')

    class L:
        gus = ['영등포구']
        def find(self, gu, a): return ([126.9, 37.5], '정확') if gu == '영등포구' else (None, None)
    row = lambda c, t, n, a='영등포구 신길동 510', s='주택재개발사업구역': dict(RPT_MNG_CD=c, RPT_TYPE=t, RGN_NM=n, PSTN_NM=a, LOGVM='서울특별시',
                                                                           SCLSF=s, AREA_EXS='36266', AREA_CHG='')
    rows = [row('11000AGZ200811270001', '신설', '신길6재정비촉진구역'), row('11000AGZ201710160001', '폐지', '신길6재정비촉진구역'),
            row('11000AGZ201710200001', '폐지', '신길6 재정비촉진구역'),  # 같은 해 중복
            row('11000AGZ201501010001', '폐지', '창신숭인', '종로구 창신동', '주거지형재정비촉진지구'),  # 지구 전체 → 제외
            row('11000AGZ198204260001', '폐지', '옛구역')]  # 2010년 이전 → 제외
    out = released(rows, L())
    assert len(out) == 1 and out[0]['zd'] == '2008-11-27' and out[0]['rd'] == '2017-10-16' and out[0]['ref'] == 2008
    assert out[0]['x'] == 126.9 and out[0]['area'] == 36266 and out[0]['kind'] == '촉진'


def test_locator_split():
    from pipeline.redev import Locator
    L = Locator.__new__(Locator)
    L.dong = {('성동구', '성수동1가'): '1120011400', ('서대문구', '북가좌동'): '1141012000', ('동작구', '상도동'): '1159010200'}
    L.gus = ['서대문구', '성동구', '동작구']
    assert L.split(None, '성동구 성수1가1동 72-10번지') == ('성동구', '1120011400', False, 72, 10)
    assert L.split(None, '서대문구 북가좌동 340-30번지 일대') == ('서대문구', '1141012000', False, 340, 30)
    assert L.split('동작구', '상도4동 산 65번지 일대') == ('동작구', '1159010200', True, 65, 0)


def test_score(tmp_path, monkeypatch):
    import json, random
    from pipeline import score
    random.seed(0)
    cols = [c for c in score.FULL if c not in ('log_area', 'log_gj', 'k_rebuild', 'k_dosi')]
    rows = []
    for i in range(260):
        k = 'released' if i < 120 else 'active_c'
        r = {c: random.random() for c in cols}
        r.update(kind=k, id=i, ref=2008, n_bldg=20, area_ha=2, gj_med=3e6, cx=127, cy=37.5, post_hh=0, t='재개발', ty='주택정비형',
                 s='관리처분' if i < 200 else '조합설립')
        if k == 'released': r['owners_per_ha'] += 1
        rows.append(r)
    monkeypatch.setattr(score, 'RAW', tmp_path); monkeypatch.setattr(score, 'OUT', tmp_path)
    (tmp_path / 'zone_features.json').write_text(json.dumps(rows))
    score.main()
    z = json.loads((tmp_path / 'zscore.json').read_text())
    assert z['meta']['n_bad'] == 120 and len(z['z']) == 60  # 조합설립 단계만 점수
    v = next(iter(z['z'].values()))
    assert 1 <= v['g'] <= 5 and isinstance(v['up'], list)
