# -*- coding: utf-8 -*-
"""test_mvp0_3_child_count.py — 출생자녀 가산 대상 자녀 수를 엔진이 직접 계산하는지 검증.

원문(N1 p.4 / N2 p.5 / N3 p.7 각주): "출산자녀는 '23.3.28. 이후 출산(입양·태아 포함)한 자녀. 기준일 이후
출산 자녀가 있는 경우에는 기준일 이전 출생한 기존 미성년자녀도 포함하여 최대 2자녀로 인정(단, 세대별
주민등록표 등재자에 한함)".

손계산 기준(함수 출력을 복사하지 않았다):
- 미성년 = 공고일에 만 19세 미만. N1(2026-07-29)은 2007-07-30 이후 출생이 미성년, 2007-07-29생은 그날
  만 19세가 되어 성인. N3(2026-08-19)은 2007-08-20 이후 출생이 미성년.
- 가산 한도: 신혼부부 4인 자녀2명 413,000,000 / 자녀1명 379,000,000 / 0명 345,000,000 (N1 p.5-6)
  대학생 자녀1명 3인이상 119,000,000 / 0명 108,000,000 (N2 p.5)
  청년 3인이상 자녀2명 301,000,000 (N3 p.7)
"""

from datetime import date, timedelta

import pytest
from rule_engine import HouseholdProfile, bonus_child_count, evaluate, validate_profile
from notices_data import N1, N2, N3

N1_ON = date(2026, 7, 29)
N3_ON = date(2026, 8, 19)
AFTER = date(2024, 1, 1)        # 기준일 이후 출생
BEFORE_MINOR = date(2015, 5, 5)  # 기준일 이전 출생 미성년


# --- bonus_child_count 단위 ------------------------------------------------------------
@pytest.mark.parametrize("dates,expected", [
    ([], 0),
    ([AFTER], 1),
    ([AFTER, BEFORE_MINOR], 2),                        # 이후 1 + 기존 미성년 1
    ([BEFORE_MINOR, date(2018, 1, 1)], 0),              # 이후 출생이 없으면 기존 미성년이 있어도 0
    ([AFTER, date(2025, 1, 1), BEFORE_MINOR], 2),       # 최대 2명
    ([AFTER, date(2007, 7, 29)], 1),                    # 공고일에 만 19세 → 성인, 제외
    ([AFTER, date(2007, 7, 30)], 2),                    # 공고일에 만 18세 → 미성년, 포함
    ([date(2023, 3, 28)], 1),                           # 기준일 당일 출생은 '이후'에 포함(가정)
    ([date(2023, 3, 27)], 0),                           # 기준일 하루 전 → 이후 아님
    ([date(2026, 12, 1)], 1),                           # 태아(출산예정일)
])
def test_bonus_child_count_n1(dates, expected):
    assert bonus_child_count(dates, N1_ON) == expected


def test_minor_line_uses_each_notice_announcement_date():
    # 2007-08-19생: N1(7/29) 기준 이미 미성년 아님(만 19세 초과), N3(8/19) 기준 그날 만 19세 → 성인
    assert bonus_child_count([AFTER, date(2007, 8, 19)], N3_ON) == 1
    assert bonus_child_count([AFTER, date(2007, 8, 20)], N3_ON) == 2
    # 2007-08-05생: N1(7/29)에는 만 18세(미성년), N3(8/19)에는 만 19세(성인) → 공고마다 결과가 다르다
    assert bonus_child_count([AFTER, date(2007, 8, 5)], N1_ON) == 2
    assert bonus_child_count([AFTER, date(2007, 8, 5)], N3_ON) == 1


# --- 신혼부부 N1: 4인 가구, 일반, 소득은 충분히 낮게 ------------------------------------
def married(dates, assets):
    return HouseholdProfile(
        "B", 35, "혼인중", "무주택", household_size=4, monthly_income=1, total_assets=assets,
        car_value=0, has_subscription_account=True, marriage_date=date(2024, 1, 1),
        children_birth_dates=dates)


def test_married_after_plus_existing_minor_counts_two_so_asset_limit_413m():
    assert "N1-M-assets" in evaluate(married([AFTER, BEFORE_MINOR], 413_000_000), N1, "신혼부부").matched
    assert "N1-M-assets" in evaluate(married([AFTER, BEFORE_MINOR], 413_000_001), N1, "신혼부부").failed


def test_married_after_only_counts_one_so_asset_limit_379m():
    assert "N1-M-assets" in evaluate(married([AFTER], 379_000_000), N1, "신혼부부").matched
    assert "N1-M-assets" in evaluate(married([AFTER], 413_000_000), N1, "신혼부부").failed


def test_married_only_old_minors_count_zero_so_base_limit_345m():
    assert "N1-M-assets" in evaluate(married([BEFORE_MINOR], 345_000_000), N1, "신혼부부").matched
    assert "N1-M-assets" in evaluate(married([BEFORE_MINOR], 345_000_001), N1, "신혼부부").failed


# --- 한부모 N1: 3인 가구, 자녀 2명 → 120%/413,000,000 (N1 p.5) ---------------------------
def single_parent(dates, assets=1):
    return HouseholdProfile(
        "B", 38, "한부모", "무주택", household_size=3, monthly_income=1, total_assets=assets,
        car_value=0, has_subscription_account=True, children_birth_dates=dates)


def test_single_parent_bonus_and_under6_both_derived_from_one_list():
    r = evaluate(single_parent([AFTER, BEFORE_MINOR], 413_000_000), N1, "한부모")
    assert "N1-S-assets" in r.matched
    assert "N1-S-child6" in r.matched   # 막내(2024-01-01)가 6세 이하 — 별도 입력 없이 목록에서 파생


def test_no_children_list_is_confirmed_no_child():
    p = single_parent([])
    assert p.has_children is False and p.youngest_child_birth_date is None
    assert "N1-S-child6" in evaluate(p, N1, "한부모").failed


def test_derived_fields_from_list():
    p = single_parent([date(2020, 1, 1), AFTER])
    assert p.has_children is True and p.youngest_child_birth_date == AFTER


# --- 대학생 N2: 3인 가구 ----------------------------------------------------------------
def student(dates, assets):
    return HouseholdProfile(
        "B", 22, "미혼", "무주택", household_size=3, monthly_income=1, total_assets=assets,
        car_value=0, student_status="재학중", children_birth_dates=dates)


def test_student_bonus_from_dates():
    assert "N2-R7" in evaluate(student([AFTER], 119_000_000), N2, "대학생").matched
    assert "N2-R7" in evaluate(student([BEFORE_MINOR], 119_000_000), N2, "대학생").failed  # 0명 → 108M


# --- 청년 N3: 세대주 3인 가구, 자녀 2명 → 자산 301,000,000 ------------------------------
def youth(dates, assets):
    return HouseholdProfile(
        "B", 30, "미혼", "무주택", house_head_status="세대주", household_size=3,
        monthly_income=1, total_assets=assets, car_value=0, has_subscription_account=True,
        children_birth_dates=dates)


def test_youth_two_after_children_asset_limit_301m():
    kids = [date(2024, 1, 1), date(2024, 6, 1)]
    assert "N3-R8" in evaluate(youth(kids, 301_000_000), N3, "청년").matched
    assert "N3-R8" in evaluate(youth(kids, 301_000_001), N3, "청년").failed


# --- 이전 입력 방식과의 관계 -------------------------------------------------------------
def test_dates_take_precedence_over_legacy_young_child_count():
    p = married([], 345_000_000)
    p.young_child_count = 2  # 모순 입력 — 목록(자녀 없음)이 우선한다
    assert "N1-M-assets" in evaluate(p, N1, "신혼부부").matched  # 한도 345M(0명)
    assert any("자녀가 없다고" in e for e in validate_profile(p))


def test_legacy_count_still_used_when_no_dates_given():
    p = HouseholdProfile("B", 35, "혼인중", "무주택", household_size=4, monthly_income=1,
                         total_assets=413_000_000, car_value=0, has_subscription_account=True,
                         marriage_date=date(2024, 1, 1), young_child_count=2)
    assert "N1-M-assets" in evaluate(p, N1, "신혼부부").matched


# --- 검증: 태아(출산예정일)는 미래여도 정상 -----------------------------------------------
def test_validate_allows_due_date_in_pregnancy_window_but_not_far_future():
    today = date.today()
    ok = married([today + timedelta(days=100)], 1)
    bad = married([today + timedelta(days=400)], 1)
    assert validate_profile(ok) == []
    assert any("너무 먼 미래" in e for e in validate_profile(bad))
