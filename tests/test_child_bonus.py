# -*- coding: utf-8 -*-
"""test_child_bonus.py — 자녀수 가산표(공고문 p.6)가 실제로 반영되는지 검증.
자녀 0/1/2명, 맞벌이 여부, 한부모/신혼부부 구분에 따라 소득비율·자산·자동차가
동시에 바뀌어야 한다."""

import pytest
from rule_engine import HouseholdProfile, evaluate, income_threshold
from notices_data import N1


def spouse(**overrides):
    defaults = dict(profile_id="B", age=30, marital_status="혼인중", home_ownership="무주택",
                     household_size=3, monthly_income=1, total_assets=1, car_value=0,
                     has_subscription_account=True, dual_income=False, young_child_count=0)
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


def singleparent(**overrides):
    defaults = dict(profile_id="B", age=35, marital_status="한부모", home_ownership="무주택",
                     household_size=2, monthly_income=1, total_assets=1, car_value=0,
                     has_subscription_account=True, young_child_count=0)
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


# --- 신혼부부, 3인가구, 자녀1명 → 소득비율 100%->110%로 완화, 자산 345M->379M로 확대 ---
def test_married_3in_child1_income_uses_relaxed_110_not_base_100():
    limit_100 = income_threshold(3, 100)   # 자녀 없을 때 기준(더 엄격)
    limit_110 = income_threshold(3, 110)   # 자녀 1명일 때 기준(더 완화)
    p = spouse(household_size=3, young_child_count=1, monthly_income=limit_100 + 1)
    # 자녀가 없었다면 100%(limit_100) 기준에 걸려 FAIL이어야 할 소득인데,
    # 자녀 1명 가산으로 110%(limit_110) 기준이 적용되어 PASS 되어야 함
    assert limit_100 + 1 <= limit_110, "테스트 전제가 무너짐(가산표 값 재확인 필요)"
    assert evaluate(p, N1, "신혼부부").verdict == "ELIGIBLE"


def test_married_3in_child1_asset_bonus_379M_not_345M():
    p = spouse(household_size=3, young_child_count=1, monthly_income=1, total_assets=379_000_000)
    assert evaluate(p, N1, "신혼부부").verdict == "ELIGIBLE"


def test_married_3in_child1_asset_still_fails_over_379M():
    p = spouse(household_size=3, young_child_count=1, monthly_income=1, total_assets=379_000_001)
    assert evaluate(p, N1, "신혼부부").verdict == "INELIGIBLE"


def test_married_4in_child2_asset_bonus_413M():
    p = spouse(household_size=4, young_child_count=2, monthly_income=1, total_assets=413_000_000)
    assert evaluate(p, N1, "신혼부부").verdict == "ELIGIBLE"


def test_married_4in_child2_dual_income_ratio_140():
    limit_140 = income_threshold(4, 140)
    p = spouse(household_size=4, young_child_count=2, dual_income=True,
               monthly_income=limit_140, total_assets=413_000_000)
    assert evaluate(p, N1, "신혼부부").verdict == "ELIGIBLE"


# --- 한부모가족, 2인가구, 자녀1명 → 110%->120%, 자산 345M->379M ---
def test_singleparent_2in_child1_relaxed_ratio_and_asset():
    limit_120 = income_threshold(2, 120)
    p = singleparent(household_size=2, young_child_count=1,
                      monthly_income=limit_120, total_assets=379_000_000)
    assert evaluate(p, N1, "한부모").verdict == "ELIGIBLE"


def test_singleparent_2in_child1_asset_fails_over_379M():
    p = singleparent(household_size=2, young_child_count=1, monthly_income=1,
                      total_assets=379_000_001)
    assert evaluate(p, N1, "한부모").verdict == "INELIGIBLE"


# --- marital_status 계층 불일치 검증 (이번에 새로 추가한 체크) ---
def test_married_layer_rejects_wrong_marital_status():
    p = spouse(marital_status="미혼")  # 신혼부부 계층인데 혼인 상태가 아님
    r = evaluate(p, N1, "신혼부부")
    assert r.verdict == "INELIGIBLE"
    assert any("marital" in f for f in r.failed)


def test_singleparent_layer_rejects_wrong_marital_status():
    p = singleparent(marital_status="혼인중")  # 한부모 계층인데 한부모가 아님
    r = evaluate(p, N1, "한부모")
    assert r.verdict == "INELIGIBLE"
    assert any("marital" in f for f in r.failed)
