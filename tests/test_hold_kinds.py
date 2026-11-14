# -*- coding: utf-8 -*-
"""R-② 보류 나누기(2026-11-14 사용자 결정, 점검 세션 docs/13 2-4) — 모든 보류가 갈래와 '다음에 할 일'을 가진다. 엔진 5상태는 그대로."""
from collections import Counter

import golden_cases as gc
from display_status import (AMBIGUOUS, HOLD_GROUP, HOLD_KINDS, INPUT, INPUT_CHECK, SELF_REPORT, SOURCE, display_result)
from rule_data import load_notice
from rule_engine import ReviewNeeded, evaluate

R = ReviewNeeded


def test_each_cause_gets_its_own_kind_and_todo():
    assert display_result("NEEDS_INFO").kind == INPUT
    assert display_result("ELIGIBLE", checks=2).kind == SOURCE and "원문 확인 2건" in display_result("ELIGIBLE", checks=2).title
    amb = display_result("MANUAL_REVIEW", {"a": R("AMBIGUOUS_SOURCE", "청년 자녀가산 [표 그대로=충족, 일반규칙=불충족]")})
    assert amb.kind == AMBIGUOUS and "'표 그대로' 해석이면 충족" in amb.todo and "1600-1004" in amb.todo
    assert display_result("MANUAL_REVIEW", {"a": R("SELF_REPORT_UNVERIFIED", "사회초년생")}).kind == SELF_REPORT
    both = {"a": R("SELF_REPORT_UNVERIFIED", "x"), "b": R("INPUT_INCONSISTENT", "y")}
    assert display_result("MANUAL_REVIEW", both).kind == INPUT_CHECK          # 사용자가 먼저 고칠 수 있는 것부터
    assert display_result("ELIGIBLE").kind is None and display_result("INELIGIBLE").kind is None


def test_no_hold_without_a_kind_across_golden_inputs():
    """등록 공고 골든 입력에서 나오는 모든 보류(정보 부족·수동 확인)가 갈래와 할 일을 가진다 — 갈래 없는 보류 0."""
    seen = Counter()
    groups = gc.GROUPS[::7]                       # 사업·계층이 고루 섞이게 골라 시간을 줄인다
    notices = {}
    for nid, layer, p in gc.cases(only=groups):
        n = notices.setdefault(nid, load_notice(nid))
        r = evaluate(p, n, layer)
        d = display_result(r.verdict, r.review_reasons)
        if d.group == HOLD_GROUP:
            assert d.kind in HOLD_KINDS and d.todo, (nid, layer, r.verdict, r.review_reasons)
            seen[d.kind] += 1
    assert {INPUT, AMBIGUOUS} <= set(seen), seen
