# -*- coding: utf-8 -*-
"""test_v3_grading.py — 자동 판정 v3 ③: 계층 등급과 사용자 단위 확정(src/grading.py, docs/10 §2-3·§2-5).

확실하지 않은 것(원문에서 확인 못 한 조건, 규칙이 모르는 문장, 새 제한 문구)이 **그 사용자의 결론을 바꿀 수 있을 때만** 보류하고,
어디를 확인할지(쪽·조건)를 함께 준다. 이미 다른 확인된 조건으로 지원 불가인 사용자는 그대로 확정.
등록 공고를 '처음 보는 공고'처럼 만들어(형제·장부에서 자기 제외) 등록 판정과 비교해 위험 0(tools/eval_v3.py).
"""
import copy
import dataclasses
import sys
from pathlib import Path

import draft
import golden_cases as gc
import grading
import operator_mode
import pytest
import source_verify as sv
from display_status import HOLD_GROUP, display_checks
from rule_data import load_notice
from rule_engine import evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import eval_v3  # noqa: E402


@pytest.fixture(scope="module")
def n12():
    return draft.make_draft(sv.pdf_path("N12").read_bytes(), only=None, pages=sv.pdf_pages("N12"), exclude="N12")


def _profiles(verdict, layer="청년", n=4):
    reg = load_notice("N12")
    out = [p for _, _, p in gc.cases(only=[("N12", layer)]) if evaluate(p, reg, layer).verdict == verdict]
    return out[:n]


def test_clean_draft_is_auto_confirmed_and_judges_like_registered(n12):
    assert n12.status == draft.OK and {g.grade for g in grading.grades(n12).values()} == {grading.AUTO}
    for p in _profiles("ELIGIBLE") + _profiles("INELIGIBLE"):
        r, checks = grading.judge(n12, p, "청년")
        assert checks == [] and r.verdict == evaluate(p, load_notice("N12"), "청년").verdict


def test_unclassified_clause_holds_only_users_whose_result_it_can_change(n12):
    d = copy.copy(n12)
    d.unclassified = [(3, "신청자본인이서울특별시에2년이상거주한자에한하여신청가능")]
    assert grading.grades(d)["청년"].grade == grading.PARTIAL
    eligible = _profiles("ELIGIBLE")[0]
    r, checks = grading.judge(d, eligible, "청년")
    assert r.verdict == "MANUAL_REVIEW" and len(checks) == 1 and checks[0].page == 3 and "규칙에 없는 조건" in checks[0].text
    ineligible = _profiles("INELIGIBLE")[0]                      # 다른 확인된 조건으로 이미 지원 불가 — 그대로 확정
    r, checks = grading.judge(d, ineligible, "청년")
    assert r.verdict == "INELIGIBLE" and checks == []


def test_held_condition_check_names_the_condition_and_page(n12):
    d = copy.copy(n12)
    home = next(c for c in n12.doc["layers"]["청년"]["conditions"] if c["id"].endswith("-home"))
    d.held_conditions = dict(n12.held_conditions, **{"청년": {home["id"]}})
    r, checks = grading.judge(d, _profiles("ELIGIBLE")[0], "청년")
    assert r.verdict == "MANUAL_REVIEW" and checks[0].kind == "held" and checks[0].page == home["source"]["page"]
    assert home["note"][:10] in checks[0].text
    # 불충족 조건이 그 보류 조건뿐이면 → 원문 확인, 다른 확인된 조건도 불충족이면 → 지원 불가 확정
    reg = load_notice("N12")
    only_home = next(p for _, _, p in gc.cases(only=[("N12", "청년")])
                     if evaluate(p, reg, "청년").failed == [home["id"].replace("DRAFT", "N12")])
    r, checks = grading.judge(d, only_home, "청년")
    assert r.verdict == "MANUAL_REVIEW" and [c.kind for c in checks] == ["held"]
    both = dataclasses.replace(only_home, age=50)
    assert grading.judge(d, both, "청년")[0].verdict == "INELIGIBLE"


def test_clause_is_attached_to_layers_by_page(n12):
    d = copy.copy(n12)
    ranges = grading.layer_pages(n12.doc)
    a, b = ranges["청년"]
    d.unclassified = [(a, "범위 안 문장"), (max(b for _, b in ranges.values()) + 5, "범위 밖 문장")]
    clauses = [t for _, t in grading.layer_clauses(d, "청년")]
    assert "범위 안 문장" in clauses and "범위 밖 문장" in clauses        # 어디에도 안 붙는 문장은 모든 계층에


def test_missing_layer_is_not_judgeable_instead_of_not_offered():
    d = draft.make_draft(sv.pdf_path("N5").read_bytes(), only=None, pages=sv.pdf_pages("N5"), exclude="N5")
    assert "주거약자(26A1/B1형)" not in d.notice.layers and grading.layers_may_be_missing(d)
    assert grading.offered(d, "주거약자(26A1/B1형)") is None and grading.offered(d, "청년") is True


@pytest.mark.parametrize("nid", ["N12", "N24", "N5", "N16"])
def test_registered_notices_as_unseen_have_no_danger(nid):
    d, grades, c = eval_v3.evaluate_notice(nid, limit=120)
    assert c[eval_v3.dc.WRONG_ELIGIBLE] + c[eval_v3.dc.WRONG_OTHER] == 0
    if nid in ("N12", "N24", "N16"):
        assert all(g.grade == grading.AUTO for g in grades.values()), nid


def test_public_switch_defaults_off(monkeypatch):
    monkeypatch.setattr(operator_mode.st, "secrets", {})
    monkeypatch.delenv(operator_mode.PUBLIC_ENV, raising=False)
    assert operator_mode.auto_judge_public() is False
    monkeypatch.setenv(operator_mode.PUBLIC_ENV, "1")
    assert operator_mode.auto_judge_public() is True
    monkeypatch.setattr(operator_mode.st, "secrets", {"auto_judge_public": False})
    assert operator_mode.auto_judge_public() is False


def test_check_display_is_a_hold_with_count():
    shown = display_checks(2)
    assert shown.group == HOLD_GROUP and "원문 확인 2건" in shown.title
