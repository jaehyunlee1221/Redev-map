"""필지 단위 집계: 건축물(노후·신축·호수) / 소유(추정 소유자 수·국공유)"""
import datetime
from collections import defaultdict
from .common import CFG

R = CFG['rules']
YEAR = R['base_year'] or datetime.date.today().year


def year(d):  # '19880512' → 1988, 결측 → None
    d = str(d or '').strip()[:4]
    return int(d) if d.isdigit() and int(d) > 1800 else None


def is_old(b):  # True/False, 사용승인일 미상이면 None
    y = year(b.get('useAprDay'))
    if y is None: return None
    rc = any(k in (b.get('strctCdNm') or '') for k in R['rc_keywords'])
    return YEAR - y >= R['old_years']['rc' if rc else 'other']


def pnu_of(b):  # 건축물대장 → PNU (대지구분 1=산 → '2')
    return b['sigunguCd'] + b['bjdongCd'] + ('2' if str(b.get('platGbCd')) == '1' else '1') \
        + str(b.get('bun') or 0).zfill(4) + str(b.get('ji') or 0).zfill(4)


def num(v):
    try: return float(v or 0)
    except ValueError: return 0.0


def agg_bldgs(bs):  # 주건축물만
    m = [b for b in bs if str(b.get('mainAtchGbCd', '0')) == '0']
    old = [is_old(b) for b in m]
    ys = [y for y in map(year, (b.get('useAprDay') for b in m)) if y]
    return dict(nb=len(m), no=sum(o is True for o in old), nu=sum(o is None for o in old),
                nn=sum(YEAR - y < R['new_years'] for y in ys),
                ta=round(sum(num(b.get('totArea')) for b in m)),
                oa=round(sum(num(b.get('totArea')) for b, o in zip(m, old) if o)),
                ho=sum(int(num(b.get('hoCnt'))) for b in m if '집합' in (b.get('regstrGbCdNm') or '')),
                hh=sum(int(num(b.get('hhldCnt')) + num(b.get('fmlyCnt'))) for b in m),
                y0=min(ys, default=None), y1=max(ys, default=None))


def agg_owners(rows):
    """ol = 구분소유 단위(공유는 대표 1인), oh = 공유자 각각 → 추정 소유자 수 범위.
    같은 사람이 여러 필지·호를 가진 경우는 구분 불가(실제보다 많게 잡힘)."""
    if not rows: return None
    pub = lambda r: '유지' in (r.get('posesnSeCodeNm') or '')  # 국유지·시도유지·구유지 등
    sn, co = defaultdict(set), defaultdict(int)
    for r in rows:
        if pub(r): continue
        u = (r.get('buldDongNm') or '', r.get('buldHoNm') or '')
        sn[u].add(r.get('cnrsPsnSn'))
        co[u] = max(co[u], int(num(r.get('cnrsPsnCo'))))
    r0 = rows[0]
    return dict(ol=len(sn), oh=sum(max(len(sn[u]), co[u], 1) for u in sn), pub=int(not sn),
                ar=round(num(r0.get('lndpclAr')), 1), jm=r0.get('lndcgrCodeNm') or '',
                gj=int(num(r0.get('pblntfPclnd'))), cg=max(str(r.get('ownshipChgDe') or '') for r in rows)[:7])
