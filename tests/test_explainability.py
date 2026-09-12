# -*- coding: utf-8 -*-
"""test_explainability.py — Explainability 레이어(explain())가 4가지 verdict를
올바른 근거 문구(rule_id/note/source_ref)로 변환하는지 확인한다.

이 테스트는 evaluate()가 이미 낸 verdict가 맞는지는 검증하지 않는다(그건
test_regression.py의 몫이다) — verdict를 사람이 읽을 문장으로 옮기는 과정 자체가
망가지지 않았는지만 확인한다."""

from rule_engine import evaluate
from notices_data import ALL_NOTICES
from profiles_data import PROFILES
from explainability import explain

PROFILES_BY_ID = {p.profile_id: (p, layer) for p, layer in PROFILES}


def _explain(profile_id, notice_id):
    profile, layer = PROFILES_BY_ID[profile_id]
    notice = ALL_NOTICES[notice_id]
    result = evaluate(profile, notice, layer)
    return explain(result, notice)


def test_not_offered_uses_evaluation_result_note():
    exp = _explain("P01", "N1")  # 대학생 계층 → N1(신혼부부·한부모만 공급)
    assert exp.verdict == "NOT_OFFERED"
    assert "대학생" in exp.headline
    assert exp.matched == exp.failed == exp.unknown == []


def test_eligible_lists_all_matched_reasons_with_source_ref():
    exp = _explain("P01", "N2")
    assert exp.verdict == "ELIGIBLE"
    assert "신청 가능" in exp.headline
    assert str(exp.score) in exp.headline
    assert len(exp.matched) > 0
    assert exp.failed == [] and exp.unknown == []
    for item in exp.matched:
        assert item.description  # note가 채워져 있어야 함
        assert item.source_ref


def test_ineligible_lists_failed_reasons_with_source_ref():
    exp = _explain("P02", "N2")
    assert exp.verdict == "INELIGIBLE"
    assert "신청할 수 없습니다" in exp.headline
    assert len(exp.failed) > 0
    for item in exp.failed:
        assert item.description
        assert item.source_ref


def test_needs_info_lists_unknown_reasons_with_source_ref():
    exp = _explain("P10", "N2")
    assert exp.verdict == "NEEDS_INFO"
    assert "추가 확인" in exp.headline
    assert len(exp.unknown) > 0
    assert exp.failed == []
    for item in exp.unknown:
        assert item.description
        assert item.source_ref


def test_every_rule_condition_has_a_note():
    """explainability가 참조할 note가 전 조건에 채워져 있는지(회귀 방지)."""
    for notice in ALL_NOTICES.values():
        for layer_name, ruleset in notice.layers.items():
            for cond in ruleset.conditions:
                assert cond.note, (
                    f"{notice.notice_id}/{layer_name}/{cond.rule_id}에 note가 비어있음"
                )
