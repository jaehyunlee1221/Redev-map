import os
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / 'config.yaml').read_text(encoding='utf-8'))
RAW = Path(os.environ.get('REDEV_RAW') or ROOT / 'data' / 'raw')  # 서버에선 저장소 밖에 두어 실행 간 유지
OUT, SEED = ROOT / 'site' / 'data', ROOT / 'data' / 'seed'


def regions(arg):
    """'test' / 'seoul,seongnam' / '11650,41135' → 시군구코드 목록"""
    out = []
    for t in arg.split(','):
        t = t.strip()
        out += [str(c) for c in CFG['regions'][t]] if t in CFG['regions'] else [t]
    return list(dict.fromkeys(out))
