from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / 'config.yaml').read_text(encoding='utf-8'))
RAW, OUT = ROOT / 'data' / 'raw', ROOT / 'site' / 'data'


def regions(arg):
    """'test' / 'seoul,seongnam' / '11650,41135' → 시군구코드 목록"""
    out = []
    for t in arg.split(','):
        t = t.strip()
        out += [str(c) for c in CFG['regions'][t]] if t in CFG['regions'] else [t]
    return list(dict.fromkeys(out))
