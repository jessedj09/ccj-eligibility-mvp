# -*- coding: utf-8 -*-
"""test_mvp0_2_manual_review.py — MANUAL_REVIEW(정책 해석 미확정) 상태와 N3 컷오프 수정 검증.

기대값 근거는 전부 원문 수치를 손으로 계산한 것이다(함수 출력을 그대로 복사하지 않았다):
- 청년 자산: N3 p.7-8 — 무자녀 251,000,000 / 3인이상+자녀1 276,000,000 / 자녀2+ 301,000,000
- 대학생 자산: N2 p.5 — 무자녀 108,000,000 / 3인이상+자녀1 119,000,000 / 자녀2+ 130,000,000
- 소득 한도: 3인가구 110% = 8,985,272원, 1인가구 120% = 4,576,036원 (N3 p.8 표)
"""

from datetime import date

import pytest
from rule_engine import (
    HouseholdProfile, evaluate, resolve_interpretations, ReviewNeeded,
    marriage_cutoff, young_child_cutoff,
)
from notices_data import (
    N1, N2, N3, N1_MARRIAGE_CUTOFF, N1_CHILD_CUTOFF, N1_ANNOUNCEMENT, N3_ANNOUNCEMENT,
)


def youth(**o):
    d = dict(profile_id="B", age=30, marital_status="미혼", home_ownership="무주택",
             house_head_status="세대주", household_size=2, young_child_count=1,
             monthly_income=1, total_assets=1, car_value=0, has_subscription_account=True)
    d.update(o)
    return HouseholdProfile(**d)


def student(**o):
    d = dict(profile_id="B", age=22, marital_status="미혼", home_ownership="무주택",
             household_size=2, young_child_count=1, monthly_income=1, total_assets=1,
             car_value=0, student_status="재학중")
    d.update(o)
    return HouseholdProfile(**d)


# --- 컷오프: N1 원문 리터럴을 일반 공식이 그대로 재현하는지(N3 적용 근거) -------------
def test_cutoff_formula_reproduces_n1_literal_dates():
    # N1 p.5: "혼인기간 7년 이내: 2019.7.29. 이후 혼인신고 / 6세 이하 자녀: 2019.7.30. 이후 출생"
    assert marriage_cutoff(N1_ANNOUNCEMENT) == N1_MARRIAGE_CUTOFF == date(2019, 7, 29)
    assert young_child_cutoff(N1_ANNOUNCEMENT) == N1_CHILD_CUTOFF == date(2019, 7, 30)


def test_n3_cutoffs_derived_from_announcement_2026_08_19():
    assert marriage_cutoff(N3_ANNOUNCEMENT) == date(2019, 8, 19)
    assert young_child_cutoff(N3_ANNOUNCEMENT) == date(2019, 8, 20)


def _single_parent(child_birth):
    return HouseholdProfile(
        "B", 35, "한부모", "무주택", household_size=2, monthly_income=1, total_assets=1,
        car_value=0, has_subscription_account=True, youngest_child_birth_date=child_birth)


def test_n3_child_born_2019_08_19_is_already_age_7_on_announcement_so_fails():
    # 2019-08-19생은 2026-08-19에 만 7세가 된다 → '6세 이하' 아님 (MVP0.1에서는 잘못 통과시켰음)
    r = evaluate(_single_parent(date(2019, 8, 19)), N3, "한부모")
    assert "N3-S-child6" in r.failed


def test_n3_child_born_2019_08_20_is_age_6_so_passes():
    r = evaluate(_single_parent(date(2019, 8, 20)), N3, "한부모")
    assert "N3-S-child6" in r.matched


# --- resolve_interpretations 단위 -------------------------------------------------
def test_resolve_all_agree_true_and_false_are_definite():
    assert resolve_interpretations({"a": True, "b": True}, "x") is True
    assert resolve_interpretations({"a": False, "b": False}, "x") is False


def test_resolve_disagreement_is_review_needed():
    r = resolve_interpretations({"a": True, "b": False}, "x")
    assert isinstance(r, ReviewNeeded) and r.code == "AMBIGUOUS_SOURCE"


def test_resolve_missing_info_dominates():
    assert resolve_interpretations({"a": None, "b": True}, "x") is None


# --- 청년 2인 가구 + 출생자녀 1명: 원문 표에 행 없음 -------------------------------
# 표 그대로 251,000,000 / 일반규칙(자녀1 10% 가산) 276,000,000
@pytest.mark.parametrize("assets,expected", [
    (251_000_000, "matched"),   # 두 해석 모두 충족
    (251_000_001, "review"),    # 표=불충족, 일반규칙=충족
    (276_000_000, "review"),    # 일반규칙 한도와 같음 → 여전히 해석에 따라 갈림
    (276_000_001, "failed"),    # 두 해석 모두 불충족
])
def test_youth_2in_child1_asset_boundaries(assets, expected):
    r = evaluate(youth(total_assets=assets), N3, "청년")
    assert "N3-R8" in getattr(r, expected)


# --- 대학생 2인 가구 + 출생자녀 1명 -------------------------------------------------
# 표 그대로 108,000,000 / 일반규칙 119,000,000
@pytest.mark.parametrize("assets,expected", [
    (108_000_000, "matched"),
    (108_000_001, "review"),
    (119_000_000, "review"),
    (119_000_001, "failed"),
])
def test_student_2in_child1_asset_boundaries(assets, expected):
    r = evaluate(student(total_assets=assets), N2, "대학생")
    assert "N2-R7" in getattr(r, expected)


def test_student_3in_child1_is_in_the_table_so_no_review():
    # 3인+자녀1은 표에 행이 있다(119,000,000) — 해석이 갈리지 않으므로 확정이어야 한다
    r = evaluate(student(household_size=3, total_assets=119_000_000), N2, "대학생")
    assert "N2-R7" in r.matched and r.review == []
    r = evaluate(student(household_size=3, total_assets=119_000_001), N2, "대학생")
    assert "N2-R7" in r.failed


# --- 청년 세대원 + 출생자녀: 표가 세대주 행을 그대로 반복 ---------------------------
# 3인 자녀1: 표 그대로 110% = 8,985,272 / 1인 120% 고정 = 4,576,036
@pytest.mark.parametrize("income,expected", [
    (4_576_036, "matched"),
    (4_576_037, "review"),
    (8_985_272, "review"),
    (8_985_273, "failed"),
])
def test_youth_member_with_child_income_boundaries(income, expected):
    p = youth(house_head_status="세대원", household_size=3, young_child_count=1,
              monthly_income=income)
    r = evaluate(p, N3, "청년")
    assert "N3-R7/R7b" in getattr(r, expected)


def test_youth_member_without_child_stays_fixed_at_1in_no_review():
    # 무자녀 세대원은 결정 로그 5번대로 확정(해석 갈림 없음)
    p = youth(house_head_status="세대원", household_size=3, young_child_count=0,
              monthly_income=4_576_037)
    r = evaluate(p, N3, "청년")
    assert "N3-R7/R7b" in r.failed and r.review == []


# --- 가구원수 1인인데 가산 대상 자녀 → 입력 모순/표에 없는 조합 ------------------------
def test_size1_with_child_is_review_for_student_and_youth():
    assert "N2-R6" in evaluate(student(household_size=1), N2, "대학생").review
    assert "N3-R7/R7b" in evaluate(youth(household_size=1), N3, "청년").review


# --- 사회초년생 자기신고 경로 ---------------------------------------------------------
def test_rookie_path_is_review_with_self_report_code():
    r = evaluate(youth(age=45, is_social_rookie=True, household_size=1, young_child_count=0),
                 N3, "청년")
    assert r.review_reasons["N3-R5b"].code == "SELF_REPORT_UNVERIFIED"


def test_age_in_range_never_triggers_rookie_review():
    r = evaluate(youth(age=39, is_social_rookie=True, household_size=1, young_child_count=0),
                 N3, "청년")
    assert "N3-R5b" in r.matched


def test_rookie_false_and_out_of_age_range_is_definite_fail():
    r = evaluate(youth(age=40, is_social_rookie=False), N3, "청년")
    assert "N3-R5b" in r.failed


# --- verdict 우선순위: 확정 불충족 > 해석 미확정 > 정보 부족 > 충족 -------------------
def test_full_profile_with_ambiguous_asset_is_manual_review_not_eligible():
    # 청년 세대주 2인가구·자녀1·자산 2.7억, 나머지 조건은 전부 충족 → ELIGIBLE이면 안 된다
    r = evaluate(youth(total_assets=270_000_000), N3, "청년")
    assert r.verdict == "MANUAL_REVIEW"
    assert r.failed == [] and r.unknown == []


def test_failed_overrides_review():
    r = evaluate(youth(total_assets=270_000_000, home_ownership="주택보유"), N3, "청년")
    assert r.verdict == "INELIGIBLE"
    assert "N3-R8" in r.review  # 해석 미확정 사실 자체는 그대로 기록된다


def test_review_takes_precedence_over_needs_info_but_keeps_unknown_listed():
    r = evaluate(youth(total_assets=270_000_000, monthly_income=None), N3, "청년")
    assert r.verdict == "MANUAL_REVIEW"
    assert "N3-R7/R7b" in r.unknown


def test_no_review_when_interpretations_agree_keeps_eligible():
    r = evaluate(youth(household_size=3, total_assets=276_000_000), N3, "청년")
    assert r.verdict == "ELIGIBLE" and r.review == []


# --- 자녀 없음(확정)과 모름(미입력)의 구분 -------------------------------------------
def _married_7plus(**o):
    d = dict(profile_id="B", age=40, marital_status="혼인중", home_ownership="무주택",
             household_size=2, monthly_income=1, total_assets=1, car_value=0,
             has_subscription_account=True, marriage_date=date(2019, 7, 28))  # N1 기준 7년 초과
    d.update(o)
    return HouseholdProfile(**d)


def test_no_child_confirmed_makes_long_marriage_a_definite_fail():
    r = evaluate(_married_7plus(has_children=False), N1, "신혼부부")
    assert r.verdict == "INELIGIBLE" and "N1-M-duration" in r.failed


def test_child_unknown_keeps_needs_info():
    r = evaluate(_married_7plus(has_children=None), N1, "신혼부부")
    assert "N1-M-duration" in r.unknown


def test_no_child_does_not_hurt_recent_marriage():
    r = evaluate(_married_7plus(has_children=False, marriage_date=date(2019, 7, 29)),
                 N1, "신혼부부")
    assert "N1-M-duration" in r.matched


def test_single_parent_without_children_fails_definitely():
    p = HouseholdProfile("B", 35, "한부모", "무주택", household_size=2, monthly_income=1,
                         total_assets=1, car_value=0, has_subscription_account=True,
                         has_children=False)
    assert "N1-S-child6" in evaluate(p, N1, "한부모").failed


def test_validate_flags_contradictory_no_child_input():
    from rule_engine import validate_profile
    p = _married_7plus(has_children=False, youngest_child_birth_date=date(2022, 1, 1))
    assert any("자녀가 없다고" in e for e in validate_profile(p))
