# -*- coding: utf-8 -*-
"""골든 스냅샷 재생성 도구.

규칙(rules/*.json)을 **의도적으로** 바꿨을 때만 실행한다. 실행 전에 `pytest tests/test_rules_golden.py`가
보여 주는 변경 내역(어떤 입력의 결과가 어떻게 달라졌는지)을 검토하고, 그 변화가 의도한 것인지 확인한 뒤
갱신된 tests/golden/*를 커밋 메시지에 이유와 함께 남긴다.

    python tools/regen_golden.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import golden_lib  # noqa: E402
from rule_data import load_notice  # noqa: E402

notices = {nid: load_notice(nid) for nid in ("N1", "N2", "N3")}
outcomes = golden_lib.build_outcomes(notices)
golden_lib.write(outcomes, golden_lib.build_conditions(notices))
print({k: v["n"] for k, v in outcomes["groups"].items()})
print("골든 스냅샷을 갱신했습니다:", golden_lib.OUTCOMES)
