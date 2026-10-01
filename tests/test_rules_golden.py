# -*- coding: utf-8 -*-
"""test_rules_golden.py — 골든 스냅샷 회귀 테스트.

데이터 규칙(rules/*.json)이 tests/golden/*에 기록된 결과와 같은 답을 내는지 확인한다. 실패하면 어떤 입력의
결과가 어떻게 달라졌는지 보여 준다. 그 변화가 **의도한 규칙 변경**이면 `python tools/regen_golden.py`로
갱신하고 변경 이유를 커밋 메시지에 남긴다. 의도하지 않았다면 데이터 오류다.

기준선은 B단계에서 기존 파이썬 규칙(legacy)과 차분 테스트로 동등성을 증명한 뒤 만든 것이다.
"""

import json

import golden_cases
import golden_lib
import pytest
from rule_data import load_notice

GOLDEN = golden_lib.load_outcomes()
NOTICES = {nid: load_notice(nid) for nid in ("N1", "N2", "N3")}
MAX_SHOWN = 5


def test_golden_snapshot_matches_rules():
    from rule_engine import evaluate
    expected = {key: iter(group["records"]) for key, group in GOLDEN["groups"].items()}
    seen = {key: 0 for key in expected}
    diffs = []
    for nid, layer, profile in golden_cases.cases():
        key = f"{nid}/{layer}"
        seen[key] += 1
        old = next(expected[key], None)
        new = golden_lib.record(evaluate(profile, NOTICES[nid], layer))
        if json.loads(json.dumps(new)) != old:
            diffs.append((key, profile, old, new))
    assert {k: v for k, v in seen.items()} == {k: g["n"] for k, g in GOLDEN["groups"].items()}, \
        "골든 입력 개수가 기록과 다릅니다 — tests/golden_cases.py를 바꿨다면 tools/regen_golden.py로 갱신하세요"
    if diffs:
        shown = "\n".join(f"  [{k}] {p}\n     기록: {o}\n     현재: {n}" for k, p, o, n in diffs[:MAX_SHOWN])
        pytest.fail(f"{len(diffs)}건의 결과가 골든 스냅샷과 다릅니다(처음 {MAX_SHOWN}건):\n{shown}\n"
                    "의도한 규칙 변경이면 python tools/regen_golden.py 로 갱신하고 이유를 커밋에 남기세요.")


def test_golden_conditions_metadata_matches_rules():
    """조건 ID·필드·필수 여부·출처 표기·설명 문구·이행 시점이 기록과 같다(설명 화면이 그대로 쓰는 값)."""
    expected = json.loads(golden_lib.CONDITIONS.read_text(encoding="utf-8"))
    actual = golden_lib.build_conditions(NOTICES)
    assert actual == expected, "조건 메타데이터가 골든과 다릅니다 — 의도한 변경이면 tools/regen_golden.py 로 갱신"
