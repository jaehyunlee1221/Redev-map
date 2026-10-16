import json
from pipeline import build, metrics
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


def test_build(tmp_path, monkeypatch):
    raw, out = tmp_path / 'raw', tmp_path / 'out'
    d = raw / '99999'; d.mkdir(parents=True)
    w = lambda n, v: (d / n).write_text(json.dumps(v, ensure_ascii=False), encoding='utf-8')
    w('dongs.json', [dict(type='Feature', geometry=sq(127, 37.5, 0.01), properties=dict(emd_cd='99999101', full_nm='테스트동'))])
    w('9999910100_parcels.json', [dict(type='Feature', geometry=sq(127.001 + i * 0.001, 37.501), properties=dict(pnu=f'99999101001{i:04d}0000', jibun=f'{i}대'))
                                  for i in (1, 2, 3)])
    w('9999910100_zones.json', [dict(type='Feature', geometry=sq(127, 37.5, 0.01), properties=dict(uname='제2종일반주거지역'))])
    w('9999910100_owners.json', [dict(pnu='9999910100100010000', cnrsPsnSn='1', posesnSeCodeNm='개인', lndpclAr='70', lndcgrCodeNm='대')])
    w('9999910100_bldgs.json', [B('0001', '19800101'), B('0002', '20250101', hoCnt='6', regstrGbCdNm='집합')])
    monkeypatch.setattr(build, 'RAW', raw); monkeypatch.setattr(build, 'OUT', out)
    build.main('99999')
    fs = {f['properties']['p'][-8:-4]: f['properties'] for f in json.loads((out / '9999910100.geojson').read_text())['features']}
    assert fs['0001']['z'] == '제2종일반주거지역' and fs['0001']['no'] == 1 and fs['0001']['ol'] == 1 and 'oe' not in fs['0001']
    assert fs['0002']['ol'] == 6 and fs['0002']['oe'] == 1 and fs['0002']['jm'] == '대'   # 소유정보 없음 → 집합 호수
    assert fs['0003']['nb'] == 0 and 60 < fs['0003']['ar'] < 1000
    dg = json.loads((out / 'dongs.geojson').read_text())['features'][0]['properties']
    assert (dg['n'], dg['nb'], dg['no'], dg['r']) == ('테스트동', 2, 1, 0.5)
