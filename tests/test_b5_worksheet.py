# -*- coding: utf-8 -*-
"""test_b5_worksheet.py — 피드백 B5: 독립 검증 사례(docs/independent-validation-cases.json)와 대조 도구(tools/worksheet_check.py).

사례 파일에는 입력만 있고 답(엔진 결과)이 없어야 한다 — 작성자가 원문만 보고 판단하게. 여기서는 사례가 모두 판정 가능한
형식인지와 대조 규칙만 본다(엔진이 무엇을 내는지는 검사하지 않는다 — 그것을 사람이 독립적으로 맞대어 보는 도구다).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import worksheet_check as W  # noqa: E402

CASES = json.loads(W.CASES.read_text(encoding="utf-8"))["cases"]


def test_cases_have_inputs_only_and_all_evaluate():
    assert len(CASES) >= 16 and len({c["id"] for c in CASES}) == len(CASES)
    for c in CASES:
        assert c["user_verdict"] == "" and c["user_page"] == ""        # 답을 미리 싣지 않는다
        assert W.engine_verdict(c) in {"ELIGIBLE", "INELIGIBLE", "NEEDS_INFO", "MANUAL_REVIEW", "NOT_OFFERED"}


def test_check_counts_only_filled_and_treats_hold_alike():
    c = dict(CASES[0])
    eng = W.engine_verdict(c)
    other = "INELIGIBLE" if eng != "INELIGIBLE" else "ELIGIBLE"
    res = W.check([dict(c, user_verdict=eng), dict(c, id=99, user_verdict=other), dict(c, id=98)])
    assert res["filled"] == 2 and res["agree"] == 1 and [m["id"] for m in res["mismatch"]] == [99]
    assert W.same("확인필요", "MANUAL_REVIEW") and W.same("NEEDS_INFO", "MANUAL_REVIEW")
    assert not W.same("ELIGIBLE", "MANUAL_REVIEW")
