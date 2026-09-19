# -*- coding: utf-8 -*-
"""profiles_data.py — 워크북 profiles 시트의 P01~P12를 그대로 코드화.

MVP0.1 갱신: 대학생/청년/신혼부부/한부모 계층에 새로 추가된 필수조건
(재학요건·연령/사회초년생·혼인기간/자녀연령)을 판정하려면 각 프로필에 해당
사실이 있어야 한다. 기존 12개 프로필은 원래 페르소나 설명과 모순되지 않는
선에서 최소한의 사실을 보강했다 — 실제 계산 로직에 영향을 주는 소득/자산/
가구원수 값은 전혀 건드리지 않았다."""

from datetime import date

from rule_engine import HouseholdProfile

# (profile, 판정에 사용할 layer) 튜플 리스트
PROFILES = [
    (HouseholdProfile("P01", 22, "미혼", "무주택", household_size=3,
                       monthly_income=6_000_000, total_assets=50_000_000, car_value=0,
                       student_status="재학중"),
     "대학생"),
    (HouseholdProfile("P02", 24, "미혼", "무주택", household_size=3,
                       monthly_income=12_000_000, total_assets=150_000_000, car_value=0,
                       student_status="재학중"),
     "대학생"),
    (HouseholdProfile("P03", 25, "미혼", "무주택", household_size=1,
                       monthly_income=3_000_000, total_assets=30_000_000, car_value=0,
                       student_status="재학중"),
     "대학생"),
    (HouseholdProfile("P04", 33, "혼인중", "무주택", household_size=3,
                       monthly_income=6_000_000, total_assets=150_000_000, car_value=0,
                       has_subscription_account=False, has_child_under_2=True,
                       youngest_child_birth_date=date(2025, 1, 15)),
     "신혼부부"),
    # P05: 세대주/세대원 정보를 의도적으로 비워둔다 — MVP0.1 이전에는 이 정보가 없으면
    # '세대주'로 간주해 N3에서 확정 INELIGIBLE을 냈으나(버그), 수정 후에는 이 계층의
    # 소득조건 판정 자체가 불가능하므로 NEEDS_INFO가 나오는 것이 올바른 동작이다.
    # (docs/rule-coverage-matrix.md 재현사례 5번 / EXPECTED 변경 사유)
    (HouseholdProfile("P05", 35, "미혼", "무주택", household_size=1,
                       monthly_income=6_000_000, total_assets=100_000_000, car_value=0,
                       has_subscription_account=True),
     "청년"),
    (HouseholdProfile("P06", 33, "혼인중", "무주택", household_size=2,
                       monthly_income=6_000_000, total_assets=200_000_000, car_value=0,
                       has_subscription_account=True, dual_income=False,
                       marriage_date=date(2023, 5, 1)),
     "신혼부부"),
    (HouseholdProfile("P07", 29, "혼인중", "무주택", household_size=2,
                       monthly_income=7_500_000, total_assets=150_000_000, car_value=0,
                       has_subscription_account=True, dual_income=True,
                       marriage_date=date(2024, 1, 1)),
     "신혼부부"),
    (HouseholdProfile("P08", 40, "한부모", "무주택", household_size=2,
                       monthly_income=5_000_000, total_assets=100_000_000, car_value=0,
                       has_subscription_account=True,
                       youngest_child_birth_date=date(2022, 1, 1)),
     "한부모"),
    (HouseholdProfile("P09", 31, "혼인중", "주택보유", household_size=2,
                       monthly_income=5_500_000, total_assets=200_000_000, car_value=0,
                       has_subscription_account=True),
     "신혼부부"),
    (HouseholdProfile("P10", 23, "미혼", "무주택", household_size=1,
                       monthly_income=2_500_000, total_assets=30_000_000, car_value="확인불가"),
     "대학생"),
    (HouseholdProfile("P11", 30, "미혼", "무주택", house_head_status="세대주", household_size=3,
                       monthly_income=7_000_000, total_assets=200_000_000, car_value=0,
                       has_subscription_account=True),
     "청년"),
    (HouseholdProfile("P12", 30, "미혼", "무주택", house_head_status="세대원", household_size=3,
                       monthly_income=2_000_000, total_assets=200_000_000, car_value=0,
                       has_subscription_account=True),
     "청년"),
]

# 워크북 match_matrix 시트에서 손으로 판정한 기대값 (N1, N2, N3)
EXPECTED = {
    "P01": {"N1": "NOT_OFFERED", "N2": "ELIGIBLE", "N3": "ELIGIBLE"},
    "P02": {"N1": "NOT_OFFERED", "N2": "INELIGIBLE", "N3": "INELIGIBLE"},
    "P03": {"N1": "NOT_OFFERED", "N2": "ELIGIBLE", "N3": "ELIGIBLE"},
    "P04": {"N1": "ELIGIBLE", "N2": "NOT_OFFERED", "N3": "ELIGIBLE"},
    # N3: MVP0.1에서 house_head_status 미상 시 '세대주로 추정'하던 버그를 고쳤다.
    # 수정 전에는 세대주 기준(가구원수 1, 100%... 실제로는 1인가구라 120% 그대로였지만
    # 다인가구였다면 잘못된 기준이 적용됐을 것)으로 임의 계산해 INELIGIBLE을 냈다.
    # 수정 후에는 이 정보 없이는 소득조건 자체를 판정할 수 없어 NEEDS_INFO가 정답이다.
    "P05": {"N1": "NOT_OFFERED", "N2": "NOT_OFFERED", "N3": "NEEDS_INFO"},
    "P06": {"N1": "ELIGIBLE", "N2": "NOT_OFFERED", "N3": "ELIGIBLE"},
    "P07": {"N1": "ELIGIBLE", "N2": "NOT_OFFERED", "N3": "ELIGIBLE"},
    "P08": {"N1": "ELIGIBLE", "N2": "NOT_OFFERED", "N3": "ELIGIBLE"},
    "P09": {"N1": "INELIGIBLE", "N2": "NOT_OFFERED", "N3": "INELIGIBLE"},
    "P10": {"N1": "NOT_OFFERED", "N2": "NEEDS_INFO", "N3": "NEEDS_INFO"},
    "P11": {"N1": "NOT_OFFERED", "N2": "NOT_OFFERED", "N3": "ELIGIBLE"},
    "P12": {"N1": "NOT_OFFERED", "N2": "NOT_OFFERED", "N3": "ELIGIBLE"},
}
