# -*- coding: utf-8 -*-
"""pytest가 tests/ 밖의 src/ 모듈을 import할 수 있도록 경로를 추가한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
