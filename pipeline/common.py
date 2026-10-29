import os, re, json, gzip
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / 'config.yaml').read_text(encoding='utf-8'))
RAW = Path(os.environ.get('REDEV_RAW') or ROOT / 'data' / 'raw')  # GitHub에서 받는 것 (건축물대장) — 커밋 안 함
SEED = ROOT / 'data' / 'seed'                                     # PC에서 받아 커밋하는 것 (브이월드)
OUT = ROOT / 'site' / 'data'

if (ROOT / '.env').exists():  # PC용 키 파일: VWORLD_KEY=...
    for ln in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
        if '=' in ln and not ln.lstrip().startswith('#'):
            k, v = ln.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def regions(arg):
    """'test' / 'seoul+seongnam' / '11650,41135' / 'seeded'(seed가 있는 구 전부) → 시군구코드 목록"""
    out = []
    for t in filter(None, re.split(r'[,+\s]+', arg)):
        if t == 'seeded': out += sorted(p.parent.name for p in SEED.glob('*/dongs.json.gz'))
        else: out += [str(c) for c in CFG['regions'][t]] if t in CFG['regions'] else [t]
    return list(dict.fromkeys(out))


def rd(sgg, name):
    """data/raw/{sgg}/{name} → 없으면 data/seed/{sgg}/{name}.gz. 둘 다 없으면 None"""
    p, g = RAW / sgg / name, SEED / sgg / (name + '.gz')
    if p.exists(): return json.loads(p.read_text(encoding='utf-8'))
    return json.loads(gzip.decompress(g.read_bytes())) if g.exists() else None


def wr(path, data):
    """.gz면 압축. 내용이 같으면 다시 쓰지 않음(git 변경 최소화) — 수정시각만 갱신"""
    b = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
    if path.suffix == '.gz': b = gzip.compress(b, mtime=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == b: path.touch()
    else: path.write_bytes(b)
