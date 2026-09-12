# -*- coding: utf-8 -*-
"""test_priority_scoring.py — N1 우선공급 배점이 지난 세션 결론대로 동작하는지 확인."""

from rule_engine import HouseholdProfile
from priority_scoring import n1_priority


def profile(**overrides):
    defaults = dict(profile_id="B", age=33, marital_status="혼인중", home_ownership="무주택",
                     household_size=3, monthly_income=1, total_assets=1, car_value=0,
                     has_subscription_account=False, subscription_months=0,
                     subscription_payment_count=0, residence_region=None, residence_years=0.0)
    defaults.update(overrides)
    return HouseholdProfile(**defaults)


def test_1순위_노원구_청약통장_없으면_0점():
    # 이전 세션에서 다룬 P04와 동일한 취지 케이스: 자격은 있어도 배점이 최하위
    p = profile(residence_region="노원구", residence_years=1.0)
    r = n1_priority(p)
    assert r.tier == "1순위"
    assert r.item2_subscription == 0
    assert r.total == 1  # 거주3년미만=1점 + 청약통장0점


def test_1순위_노원구_3년이상_24회이상_만점():
    p = profile(residence_region="노원구", residence_years=3.5,
                subscription_months=30, subscription_payment_count=25)
    r = n1_priority(p)
    assert r.item1_residence == 3
    assert r.item2_subscription == 3
    assert r.total == 6


def test_2순위_서울시는_거주지항목_적용불가():
    # 노원구 거주자가 아니므로 ①번 항목 자체가 None(적용불가)이어야 함
    p = profile(residence_region="서울시", residence_years=10.0,
                subscription_months=30, subscription_payment_count=25)
    r = n1_priority(p)
    assert r.tier == "2순위"
    assert r.item1_residence is None
    assert r.item2_subscription == 3
    assert r.total == 3  # ①은 빠지고 ②만 반영


def test_2순위_청약통장_없으면_총점_0점():
    p = profile(residence_region="서울시")
    r = n1_priority(p)
    assert r.total == 0


def test_caveat_문구가_항상_포함됨():
    # ①번 항목 적용범위가 100% 확정이 아니라는 경고가 결과에서 누락되면 안 됨
    r = n1_priority(profile(residence_region="노원구"))
    assert "확정은 아님" in r.caveat
