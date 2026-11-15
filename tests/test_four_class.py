# -*- coding: utf-8 -*-
"""test_four_class.py — 오류 4분류(tools/four_class.py, 2026-11-09 피드백 1순위·docs/13 1-1절).

분류 규칙(화면 표시 기준)과 워크시트 대조가 '채운 사례만, 사람 답을 기준으로' 세는지 본다. 엔진이 무엇을 내는지는 검사하지 않는다
(그것을 사람이 독립적으로 맞대는 도구다 — test_b5_worksheet와 같은 원칙).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import four_class as F  # noqa: E402

CASES = json.loads(F.CASES.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("system,reference,expected", [
    ("ELIGIBLE", "ELIGIBLE", F.SAME),
    ("NEEDS_INFO", "MANUAL_REVIEW", F.SAME),            # 보류끼리는 같음
    ("MANUAL_REVIEW", "확인필요", F.SAME),               # 워크시트의 '확인필요'는 보류
    ("ELIGIBLE", "INELIGIBLE", F.C1),
    ("ELIGIBLE", "NOT_OFFERED", F.C1),
    ("INELIGIBLE", "ELIGIBLE", F.C2),
    ("NOT_OFFERED", "ELIGIBLE", F.C2),
    ("ELIGIBLE", "MANUAL_REVIEW", F.C3),
    ("INELIGIBLE", "NEEDS_INFO", F.C3),
    ("MANUAL_REVIEW", "ELIGIBLE", F.C4),
    ("NEEDS_INFO", "INELIGIBLE", F.C4),
    ("INELIGIBLE", "NOT_OFFERED", F.OTHER),
    (None, "ELIGIBLE", F.NOT_JUDGED),
])
def test_classify(system, reference, expected):
    assert F.classify(system, reference) == expected


def test_classify_rejects_unknown_verdict():
    with pytest.raises(ValueError):
        F.classify("MAYBE", "ELIGIBLE")


def test_snapshot_frozen_after_registration_is_not_unseen():
    """등록한 날보다 뒤에 얼린 스냅샷은 처음 보는 공고 검증으로 세지 않는다(같은 날은 순서를 몰라 센다)."""
    reg = F.registered_on("N12")
    if reg is None:
        pytest.skip("git 기록 없음")
    assert F.frozen_after_registration({"created": "2999-01-01"}, "N12")
    assert not F.frozen_after_registration({"created": "2000-01-01"}, "N12")
    assert not F.frozen_after_registration({"created": reg}, "N12")
    assert not F.frozen_after_registration({}, "N12")


def test_worksheet_counts_only_filled_against_human():
    c = next(x for x in CASES if x["id"] == 25)
    eng = F.engine_verdict(c)
    hold = "확인필요"
    opposite = "INELIGIBLE" if F.group(eng) != "불가" else "ELIGIBLE"
    res = F.worksheet([dict(c, user_verdict=eng), dict(c, id=901, user_verdict=hold), dict(c, id=902, user_verdict=opposite),
                       dict(c, id=903)], with_auto=False)
    assert res["filled"] == 3 and res["total"] == 4
    assert res["engine"][F.SAME] >= 1
    k = {r["id"]: r["engine_class"] for r in res["rows"]}
    assert k[25] == F.SAME
    assert k[901] == (F.SAME if F.group(eng) == "보류" else F.C3)
    assert k[902] != F.SAME


def test_round1_cases_present_and_answers_merge(tmp_path):
    """1차 카드 사례가 사례 파일에 있고, 사람 답은 별도 답 파일에서 합쳐 읽는다(사례 파일은 입력만 — test_b5)."""
    assert {1, 5, 7, 11, 21, 31, 32, 33} <= {c["id"] for c in CASES}     # docs/independent-validation-round1.md
    ans = tmp_path / "answers.json"
    ans.write_text(json.dumps({"answers": {"25": {"verdict": "확인필요", "page": "7"}}}, ensure_ascii=False), encoding="utf-8")
    merged = F.with_answers(CASES, ans)
    got = {c["id"]: (c["user_verdict"], c["user_page"]) for c in merged}
    assert got[25] == ("확인필요", "7") and got[26] == ("", "")
    assert all(c["user_verdict"] == "" for c in CASES)                  # 원본은 바꾸지 않는다
    assert F.with_answers(CASES, tmp_path / "없음.json") == CASES
