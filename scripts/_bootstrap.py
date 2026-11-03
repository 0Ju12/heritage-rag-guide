"""스크립트를 `python scripts/xxx.py`로 실행해도 프로젝트 모듈을 찾도록 경로를 잡는다."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
try:  # 윈도우 콘솔에서 한글·기호가 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
