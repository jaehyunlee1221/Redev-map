import gzip, json, zipfile
import shapefile
from pyproj import CRS
from pipeline import seed

PRJ = CRS.from_epsg(5186).to_wkt('WKT1_ESRI')


def shp_zip(path, fields, rows):  # rows: [(좌하단 x, y, 값...)] → 5186 좌표 20m 정사각형
    w = shapefile.Writer(str(path.with_suffix('')), shapeType=shapefile.POLYGON, encoding='cp949')
    for f in fields: w.field(f, 'C', 50)
    for x, y, *v in rows:
        w.poly([[[x, y], [x, y + 20], [x + 20, y + 20], [x + 20, y], [x, y]]]); w.record(*v)
    w.close()
    path.with_suffix('.prj').write_text(PRJ)
    with zipfile.ZipFile(path, 'w') as z:
        for e in ('.shp', '.shx', '.dbf', '.prj'): z.write(path.with_suffix(e), 'LSMD' + e)
    return str(path)


def test_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(seed, 'SEED', tmp_path / 'seed')
    a = shp_zip(tmp_path / 'a.zip', ['PNU', 'JIBUN'], [(200000, 545000, '1165010100100010000', '1대'),
                                                       (200020, 545000, '1165010100100020000', '2대'),
                                                       (200000, 545100, '1165010200100010000', '1전'),
                                                       (300000, 545000, '1168010100100010000', '9대')])  # 다른 구 → 제외
    z = shp_zip(tmp_path / 'z.zip', ['DGM_NM'], [(199990, 544990, '제2종일반주거지역')])
    c = tmp_path / 'o.csv'
    c.write_text('고유번호,법정동명,지목,토지면적(㎡),소유구분,공유인수,공유인일련번호\n'
                 '1165010100100010000,서울특별시 서초구 방배동,대,400,개인,2,1\n'
                 '1168010100100010000,서울특별시 강남구 역삼동,대,100,개인,1,1\n', encoding='cp949')
    seed.main('11650', a, z, str(c))
    d = tmp_path / 'seed' / '11650'
    load = lambda n: json.loads(gzip.decompress((d / n).read_bytes()))
    dongs = load('dongs.json.gz')
    assert sorted(f['properties']['emd_cd'] for f in dongs) == ['11650101', '11650102']
    assert dongs[0]['properties']['emd_kor_nm'] == '방배동'
    p = load('1165010100_parcels.json.gz')
    x, y = p[0]['geometry']['coordinates'][0][0]
    assert len(p) == 2 and 126.9 < x < 127.2 and 37.3 < y < 37.6          # WGS84 변환 확인
    assert load('1165010100_zones.json.gz')[0]['properties']['uname'] == '제2종일반주거지역'
    o = load('1165010100_owners.json.gz')['1165010100100010000']
    assert (o['ol'], o['oh'], o['ar'], o['jm']) == (1, 2, 400.0, '대')   # 원본 행 대신 필지별 집계만 저장
