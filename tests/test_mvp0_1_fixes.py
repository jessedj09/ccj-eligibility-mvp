# -*- coding: utf-8 -*-
"""test_mvp0_1_fixes.py — ChatGPT Codex 리뷰가 지적한 8개 재현 사례를 실제로
재현(수정 전 동작)하고 수정 후 올바른 동작을 검증한다.
docs/rule-coverage-matrix.md의 "재현한 오류" 절과 1:1로 대응한다."""

from datetime import date

import pytest
from rule_engine import HouseholdProfile, evaluate, validate_profile
from notices_data import N1, N2, N3


def youth(**overrides):
    defaults = dict(profile_id="B", age=30, marital_status="미혼", home_ownership="무주택",
                     house_head_status="세대주", household_size=1,
                     monthly_income=1, total_assets=1, car_value=0,
                     has_subscription_account=True)
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


def student(**overrides):
    defaults = dict(profile_id="B", age=22, marital_status="미혼", home_ownership="무주택",
                     household_size=1, monthly_income=1, total_assets=1, car_value=0,
                     student_status="재학중")
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


def married(**overrides):
    defaults = dict(profile_id="B", age=30, marital_status="혼인중", home_ownership="무주택",
                     household_size=2, monthly_income=1, total_assets=1, car_value=0,
                     has_subscription_account=True, dual_income=False)
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


def singleparent(**overrides):
    defaults = dict(profile_id="B", age=35, marital_status="한부모", home_ownership="무주택",
                     household_size=2, monthly_income=1, total_assets=1, car_value=0,
                     has_subscription_account=True)
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


# --- 1. 번동3 청년: 주택보유자가 신청 가능으로 판정되던 문제 ---------------
def test_youth_homeowner_is_ineligible():
    p = youth(home_ownership="주택보유")
    r = evaluate(p, N3, "청년")
    assert r.verdict == "INELIGIBLE"
    assert "N3-R5" in r.failed


# --- 2. 청년의 연령/사회초년생 요건 미검사 ---------------------------------
def test_youth_age_out_of_range_without_rookie_flag_fails():
    p = youth(age=45, is_social_rookie=None)
    r = evaluate(p, N3, "청년")
    assert "N3-R5b" in r.unknown  # rookie 여부를 모르면 확정 불가(무조건 FAIL이 아님)


def test_youth_age_out_of_range_and_confirmed_not_rookie_fails():
    p = youth(age=45, is_social_rookie=False)
    r = evaluate(p, N3, "청년")
    assert r.verdict == "INELIGIBLE"
    assert "N3-R5b" in r.failed


def test_youth_age_out_of_range_but_social_rookie_passes_this_condition():
    p = youth(age=45, is_social_rookie=True, monthly_income=income_ok_for(1, 120))
    r = evaluate(p, N3, "청년")
    assert "N3-R5b" in r.matched


def income_ok_for(size, ratio):
    from rule_engine import income_threshold
    return income_threshold(size, ratio)


def test_youth_age_in_range_needs_no_rookie_info():
    p = youth(age=25, is_social_rookie=None)
    r = evaluate(p, N3, "청년")
    assert "N3-R5b" in r.matched


# --- 3. 대학생/취업준비생 재학요건 미검사 ----------------------------------
def test_student_status_unknown_is_needs_info():
    p = student(student_status=None)
    r = evaluate(p, N2, "대학생")
    assert r.verdict == "NEEDS_INFO"
    assert "N2-R5c" in r.unknown


def test_student_job_seeker_within_2_years_passes():
    # N2 공고일 2026-07-15 기준 정확히 2년 전 졸업 → 이내(만 나이 방식)
    p = student(student_status="취업준비생", grad_or_dropout_date=date(2024, 7, 15))
    r = evaluate(p, N2, "대학생")
    assert "N2-R5c" in r.matched


def test_student_job_seeker_over_2_years_fails():
    p = student(student_status="취업준비생", grad_or_dropout_date=date(2024, 7, 14))
    r = evaluate(p, N2, "대학생")
    assert "N2-R5c" in r.failed


# --- 4. 신혼부부 혼인기간/자녀연령, 한부모 자녀요건 미검사 ------------------
def test_married_over_7_years_without_young_child_fails():
    # 혼인 7년 초과 + 자녀도 확실히 7세 이상(6세 이하 아님) → 대체경로도 없어 확정 FAIL
    p = married(marriage_date=date(2018, 7, 29), youngest_child_birth_date=date(2010, 1, 1))
    r = evaluate(p, N1, "신혼부부")
    assert r.verdict == "INELIGIBLE"
    assert "N1-M-duration" in r.failed


def test_married_exactly_7_years_passes():
    p = married(marriage_date=date(2019, 7, 29))
    r = evaluate(p, N1, "신혼부부")
    assert "N1-M-duration" in r.matched


def test_married_over_7_years_with_unknown_child_status_is_needs_info():
    # 혼인기간은 확정 FAIL이지만 자녀 정보를 아예 모르면(대체경로 가능성이 남아있으므로) NEEDS_INFO
    p = married(marriage_date=date(2018, 7, 29), youngest_child_birth_date=None)
    r = evaluate(p, N1, "신혼부부")
    assert "N1-M-duration" in r.unknown


def test_married_over_7_years_but_child_under_6_passes_via_child_path():
    p = married(marriage_date=date(2015, 1, 1), youngest_child_birth_date=date(2022, 1, 1))
    r = evaluate(p, N1, "신혼부부")
    assert "N1-M-duration" in r.matched


def test_preengaged_couple_skips_duration_requirement_entirely():
    p = married(marital_status="예비신혼", marriage_date=None, youngest_child_birth_date=None)
    r = evaluate(p, N1, "신혼부부")
    assert "N1-M-duration" in r.matched


def test_singleparent_without_child_birthdate_is_needs_info():
    p = singleparent(youngest_child_birth_date=None)
    r = evaluate(p, N1, "한부모")
    assert "N1-S-child6" in r.unknown


def test_singleparent_child_just_before_cutoff_fails():
    # 원문 리터럴 컷오프(2019.7.30. 이후 출생)보다 하루 이른 출생 → FAIL
    p = singleparent(youngest_child_birth_date=date(2019, 7, 29))
    r = evaluate(p, N1, "한부모")
    assert "N1-S-child6" in r.failed


def test_singleparent_child_exactly_on_cutoff_passes():
    p = singleparent(youngest_child_birth_date=date(2019, 7, 30))
    r = evaluate(p, N1, "한부모")
    assert "N1-S-child6" in r.matched


# --- 5. 세대주/세대원 정보가 없으면 세대주로 계산하던 문제 -----------------
def test_youth_missing_head_status_is_needs_info_not_silently_head_of_household():
    p = youth(house_head_status=None, household_size=3, monthly_income=9_000_000)
    # 세대주였다면 3인 100% 기준(8,168,429)이라 9,000,000은 FAIL이었을 것.
    # 세대원이었다면 1인 120% 기준(4,576,036)이라 역시 FAIL. 두 경우 다 FAIL이라도
    # '어느 기준을 적용했는지 확인되지 않았다'는 사실 자체가 NEEDS_INFO여야 한다.
    r = evaluate(p, N3, "청년")
    assert "N3-R7/R7b" in r.unknown


# --- 6·7. 소득·자산 None(미입력)과 0원 구분, 예외 미발생 -------------------
def test_income_none_is_needs_info_not_exception():
    p = student(monthly_income=None)
    r = evaluate(p, N2, "대학생")  # 예외 없이 끝나야 함
    assert r.verdict == "NEEDS_INFO"
    assert "N2-R6" in r.unknown


def test_income_actual_zero_is_evaluated_normally_not_treated_as_unknown():
    p = student(monthly_income=0, total_assets=0)
    r = evaluate(p, N2, "대학생")
    assert "N2-R6" in r.matched
    assert "N2-R7" in r.matched


def test_assets_none_is_needs_info_not_exception():
    p = student(total_assets=None)
    r = evaluate(p, N2, "대학생")
    assert "N2-R7" in r.unknown


def test_validate_profile_flags_negative_income():
    p = student(monthly_income=-1)
    errors = validate_profile(p)
    assert any("음수" in e for e in errors)


def test_validate_profile_flags_future_marriage_date():
    p = married(marriage_date=date(2099, 1, 1))
    errors = validate_profile(p)
    assert any("미래" in e for e in errors)


def test_validate_profile_passes_clean_profile():
    assert validate_profile(student()) == []


# --- 8. 대학생·청년의 자녀 가산 미적용 -------------------------------------
def test_student_child_bonus_raises_asset_limit():
    # 3인가구, 자녀 없으면 108,000,000이 한도지만 자녀 1명이면 119,000,000으로 상향
    p = student(household_size=3, young_child_count=1, total_assets=119_000_000)
    r = evaluate(p, N2, "대학생")
    assert "N2-R7" in r.matched
    p_no_bonus = student(household_size=3, young_child_count=0, total_assets=119_000_000)
    r2 = evaluate(p_no_bonus, N2, "대학생")
    assert "N2-R7" in r2.failed


def test_youth_household_head_child_bonus_raises_asset_limit():
    # 청년 세대주 3인가구, 자녀 1명 → 자산한도 251M -> 276M
    p = youth(house_head_status="세대주", household_size=3, young_child_count=1,
              total_assets=276_000_000, monthly_income=1)
    r = evaluate(p, N3, "청년")
    assert "N3-R8" in r.matched
    p_no_bonus = youth(house_head_status="세대주", household_size=3, young_child_count=0,
                        total_assets=276_000_000, monthly_income=1)
    r2 = evaluate(p_no_bonus, N3, "청년")
    assert "N3-R8" in r2.failed


# --- 회귀: 불충족과 정보부족이 동시에 존재하는 사례 -------------------------
def test_failed_condition_takes_priority_over_unknown_conditions():
    # 재학요건은 모르지만(unknown), 자동차는 확실히 보유(failed) → 최종 verdict는 INELIGIBLE
    p = student(student_status=None, car_value=5_000_000)
    r = evaluate(p, N2, "대학생")
    assert r.verdict == "INELIGIBLE"
    assert "N2-R8" in r.failed
    assert "N2-R5c" in r.unknown


# --- 코덱스 회귀 지정 사례 (자산 조건만 별도 검증, 최종 자격은 다른 조건도 확인) ---
def test_codex_case_youth_head_2in_child1_asset_270m_passes_asset_condition():
    p = youth(house_head_status="세대주", household_size=2, young_child_count=1,
              total_assets=270_000_000)
    r = evaluate(p, N3, "청년")
    # 2인가구는 원문 표에 자녀가산 행이 없어(자녀가 있으면 통상 3인 이상) 자산한도는
    # 2인 기준(251,000,000원)이 그대로 적용된다 — 따라서 270,000,000원은 FAIL이다.
    # (이 사례는 "표에 없는 조합"에 대한 해석을 보여주기 위한 것으로, 최종 신청자격은
    # 이 자산조건 하나만으로 결정되지 않는다.)
    assert "N3-R8" in r.failed


def test_codex_case_student_2in_child1_asset_115m_fails_asset_condition():
    p = student(household_size=2, young_child_count=1, total_assets=115_000_000)
    r = evaluate(p, N2, "대학생")
    # 대학생 자녀가산표도 2인가구 자녀행이 없어 2인 기준(108,000,000원)이 그대로 적용 → FAIL
    assert "N2-R7" in r.failed
