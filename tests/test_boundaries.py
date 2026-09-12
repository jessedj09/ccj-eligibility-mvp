# -*- coding: utf-8 -*-
"""test_boundaries.py — 기준값(reference_values)과 정확히 같을 때 PASS(이하 조건),
기준값+1일 때 FAIL이 정확히 되는지 검증. 사람 검증 없이 코드의 <=/< 연산자 오류를
100% 잡아내는 게 목적이다."""

import pytest
from rule_engine import HouseholdProfile, evaluate, income_threshold
from notices_data import N1, N2, N3


def base_student(**overrides):
    defaults = dict(profile_id="B", age=22, marital_status="미혼", home_ownership="무주택",
                     household_size=3, monthly_income=1, total_assets=1, car_value=0)
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


def base_spouse(**overrides):
    defaults = dict(profile_id="B", age=30, marital_status="혼인중", home_ownership="무주택",
                     household_size=3, monthly_income=1, total_assets=1, car_value=0,
                     has_subscription_account=True, dual_income=False)
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


def base_youth(**overrides):
    defaults = dict(profile_id="B", age=30, marital_status="미혼", home_ownership="무주택",
                     house_head_status="세대주", household_size=3, monthly_income=1,
                     total_assets=1, car_value=0, has_subscription_account=True)
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


# =========================================================================
# 대학생 (N2) — 소득 경계값: 1인120% / 2인110% / 3인100%
# =========================================================================
@pytest.mark.parametrize("size,ratio", [(1, 120), (2, 110), (3, 100)])
def test_student_income_boundary_pass(size, ratio):
    limit = income_threshold(size, ratio)
    p = base_student(household_size=size, monthly_income=limit)
    assert evaluate(p, N2, "대학생").verdict == "ELIGIBLE"


@pytest.mark.parametrize("size,ratio", [(1, 120), (2, 110), (3, 100)])
def test_student_income_boundary_fail(size, ratio):
    limit = income_threshold(size, ratio)
    p = base_student(household_size=size, monthly_income=limit + 1)
    r = evaluate(p, N2, "대학생")
    assert r.verdict == "INELIGIBLE"
    assert "N2-R6" in r.failed


def test_student_assets_boundary_pass():
    assert evaluate(base_student(total_assets=108_000_000), N2, "대학생").verdict == "ELIGIBLE"


def test_student_assets_boundary_fail():
    r = evaluate(base_student(total_assets=108_000_001), N2, "대학생")
    assert r.verdict == "INELIGIBLE" and "N2-R7" in r.failed


def test_student_car_zero_pass():
    assert evaluate(base_student(car_value=0), N2, "대학생").verdict == "ELIGIBLE"


def test_student_car_nonzero_fail():
    # 대학생계층은 '보유 자체 금지'라 1원짜리 차량도 즉시 FAIL이어야 함
    r = evaluate(base_student(car_value=1), N2, "대학생")
    assert r.verdict == "INELIGIBLE" and "N2-R8" in r.failed


# =========================================================================
# 신혼부부 (N1) — 소득 경계값: 3인100%, 2인110%(일반)/130%(맞벌이)
# =========================================================================
def test_spouse_income_3in_100_pass():
    p = base_spouse(household_size=3, monthly_income=income_threshold(3, 100))
    assert evaluate(p, N1, "신혼부부").verdict == "ELIGIBLE"


def test_spouse_income_3in_100_fail():
    p = base_spouse(household_size=3, monthly_income=income_threshold(3, 100) + 1)
    assert evaluate(p, N1, "신혼부부").verdict == "INELIGIBLE"


def test_spouse_income_2in_general_110_pass():
    p = base_spouse(household_size=2, monthly_income=income_threshold(2, 110), dual_income=False)
    assert evaluate(p, N1, "신혼부부").verdict == "ELIGIBLE"


def test_spouse_income_2in_general_110_fail():
    p = base_spouse(household_size=2, monthly_income=income_threshold(2, 110) + 1, dual_income=False)
    assert evaluate(p, N1, "신혼부부").verdict == "INELIGIBLE"


def test_spouse_income_2in_dual_130_pass():
    p = base_spouse(household_size=2, monthly_income=income_threshold(2, 130), dual_income=True)
    assert evaluate(p, N1, "신혼부부").verdict == "ELIGIBLE"


def test_spouse_income_2in_dual_130_fail():
    p = base_spouse(household_size=2, monthly_income=income_threshold(2, 130) + 1, dual_income=True)
    assert evaluate(p, N1, "신혼부부").verdict == "INELIGIBLE"


def test_spouse_assets_boundary_pass():
    assert evaluate(base_spouse(total_assets=345_000_000), N1, "신혼부부").verdict == "ELIGIBLE"


def test_spouse_assets_boundary_fail():
    assert evaluate(base_spouse(total_assets=345_000_001), N1, "신혼부부").verdict == "INELIGIBLE"


def test_spouse_car_boundary_pass():
    assert evaluate(base_spouse(car_value=45_420_000), N1, "신혼부부").verdict == "ELIGIBLE"


def test_spouse_car_boundary_fail():
    assert evaluate(base_spouse(car_value=45_420_001), N1, "신혼부부").verdict == "INELIGIBLE"


# =========================================================================
# 청년 — 세대주(N3): 1인120%/2인110%/3인100%
# =========================================================================
@pytest.mark.parametrize("size,ratio", [(1, 120), (2, 110), (3, 100)])
def test_youth_headofhh_income_boundary_pass(size, ratio):
    limit = income_threshold(size, ratio)
    p = base_youth(house_head_status="세대주", household_size=size, monthly_income=limit)
    assert evaluate(p, N3, "청년").verdict == "ELIGIBLE"


@pytest.mark.parametrize("size,ratio", [(1, 120), (2, 110), (3, 100)])
def test_youth_headofhh_income_boundary_fail(size, ratio):
    limit = income_threshold(size, ratio)
    p = base_youth(house_head_status="세대주", household_size=size, monthly_income=limit + 1)
    assert evaluate(p, N3, "청년").verdict == "INELIGIBLE"


# =========================================================================
# 청년 — 세대원(N3): 지난 세션에서 잡은 P12 버그(가구원수 1로 고정) 재발 방지 테스트
# household_size를 일부러 5로 크게 줘도 '세대원'이면 반드시 1인가구 기준(120%)이어야 함
# =========================================================================
def test_youth_member_income_fixed_at_1in_pass_regardless_of_household_size():
    limit = income_threshold(1, 120)
    p = base_youth(house_head_status="세대원", household_size=5, monthly_income=limit)
    assert evaluate(p, N3, "청년").verdict == "ELIGIBLE"


def test_youth_member_income_fixed_at_1in_fail_regardless_of_household_size():
    limit = income_threshold(1, 120)
    p = base_youth(house_head_status="세대원", household_size=5, monthly_income=limit + 1)
    assert evaluate(p, N3, "청년").verdict == "INELIGIBLE"


def test_youth_assets_boundary_pass():
    assert evaluate(base_youth(total_assets=251_000_000), N3, "청년").verdict == "ELIGIBLE"


def test_youth_assets_boundary_fail():
    assert evaluate(base_youth(total_assets=251_000_001), N3, "청년").verdict == "INELIGIBLE"


def test_youth_car_boundary_pass():
    assert evaluate(base_youth(car_value=45_420_000), N3, "청년").verdict == "ELIGIBLE"


def test_youth_car_boundary_fail():
    assert evaluate(base_youth(car_value=45_420_001), N3, "청년").verdict == "INELIGIBLE"
