# -*- coding: utf-8 -*-
"""test_g3_nhtown.py — G3: 신혼희망타운(공공분양) 판정 틀(lh.newlywed_town_sale, N45~N48).

기준은 원문에서 손으로 옮겼다:
- 시흥하중 A-4(N46) p.11 "현재수도권[서울특별시,인천광역시,경기도]에거주하면서아래조건(1~4)을모두갖춘신혼부부 1 혼인기간이
  …7년이내(2019.09.18.~2026.09.18.) 또는 6세이하의자녀 … 2 입주자저축에가입하여6개월이경과되고 … 6회이상 3 … 130%(단,본인및배우자가
  모두소득이있는경우에는200%)이하 4 총자산 … <표3>" / p.9 <표5>·<표6> 3인 이하 130% 9,793,892 · 140% 10,547,268 · 150% 11,300,645 ·
  200% 15,067,526 · 210% 15,820,902 · 220% 16,574,279, 4인 130% 11,442,863, 8인 200% 22,129,638 / 총자산 362백만(397·431백만).
- 평택고덕 A-57-2(N45) p.1 "입주자저축가입여부,과거당첨여부,소득및자산요건을불문", "현재전국에거주…만19세이상의무주택세대구성원".
"""
import sys
from datetime import date
from pathlib import Path

import pytest
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

NEW1, NEW2 = date(2024, 1, 1), date(2025, 6, 1)


def v(nid, layer="신혼부부", **kw):
    base = dict(profile_id="T", age=33, marital_status={"신혼부부": "혼인중", "예비신혼부부": "예비신혼", "한부모": "한부모"}[layer],
                home_ownership="무주택", household_size=2, monthly_income=3_000_000, total_assets=100_000_000, car_value=0,
                children_birth_dates=[NEW1] if layer == "한부모" else [], marriage_date=date(2024, 5, 1),
                residence_area="고양시", has_subscription_account=True, subscription_months=12, subscription_payment_count=12,
                rewin_restricted=False, past_special_supply=False)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), layer).verdict


@pytest.mark.parametrize("size,kids,dual,limit", [
    (2, [], False, 9_793_892), (3, [], False, 9_793_892), (1, [], False, 9_793_892),     # 3인 이하는 한 칸
    (4, [], False, 11_442_863), (3, [NEW1], False, 10_547_268), (4, [NEW1, NEW2], False, 13_203_303),
    (2, [], True, 15_067_526), (3, [NEW1], True, 15_820_902), (4, [NEW1, NEW2], True, 19_364_844), (8, [], True, 22_129_638),
])
def test_income_130_or_dual_200_with_birth_bonus(size, kids, dual, limit):
    kw = dict(household_size=size, children_birth_dates=kids, dual_income=dual)
    layer = "예비신혼부부" if size == 1 else "신혼부부"
    assert v("N46", layer, **kw, monthly_income=limit) == "ELIGIBLE"
    assert v("N46", layer, **kw, monthly_income=limit + 1) == "INELIGIBLE"


def test_single_parent_has_no_dual_bonus():
    kw = dict(children_birth_dates=[NEW1], household_size=2)
    assert v("N46", "한부모", **kw, monthly_income=10_547_268) == "ELIGIBLE"                 # 출산 1명 140%
    assert v("N46", "한부모", **kw, monthly_income=10_547_269, dual_income=True) == "INELIGIBLE"


def test_assets_subscription_rewin_special_region():
    assert v("N46", total_assets=362_000_000) == "ELIGIBLE" and v("N46", total_assets=362_000_001) == "INELIGIBLE"
    assert v("N46", total_assets=431_000_000, children_birth_dates=[NEW1, NEW2], household_size=4) == "ELIGIBLE"
    assert v("N46", subscription_months=5) == v("N46", subscription_payment_count=5) == "INELIGIBLE"
    assert v("N46", has_subscription_account=False) == "INELIGIBLE"
    assert v("N46", rewin_restricted=True) == v("N46", past_special_supply=True) == "INELIGIBLE"
    assert v("N46", rewin_restricted=None) == v("N46", past_special_supply=None) == "NEEDS_INFO"
    assert v("N46", residence_area="부산광역시") == "INELIGIBLE"


def test_marriage_seven_years_or_child_under_seven():
    assert v("N46", marriage_date=date(2019, 9, 18)) == "ELIGIBLE"                         # 원문 '2019.09.18.~'
    assert v("N46", marriage_date=date(2019, 9, 17)) == "INELIGIBLE"
    old = dict(marriage_date=date(2015, 1, 1), household_size=3)
    assert v("N46", **old, children_birth_dates=[date(2019, 9, 19)]) == "ELIGIBLE"
    assert v("N46", **old, children_birth_dates=[date(2019, 9, 18)]) == "INELIGIBLE"
    assert v("N46", "한부모", children_birth_dates=[date(2015, 1, 1)]) == "INELIGIBLE"


@pytest.mark.parametrize("nid", ["N45", "N47"])
def test_open_remaining_units_ignore_savings_income_assets(nid):
    rich = dict(monthly_income=90_000_000, total_assets=2_000_000_000, has_subscription_account=False,
                rewin_restricted=None, past_special_supply=None, residence_area="부산광역시")
    for layer in ("신혼부부", "예비신혼부부", "한부모"):
        assert v(nid, layer, **rich) == "ELIGIBLE"
    assert v(nid, age=18) == "INELIGIBLE"
    assert v(nid, home_ownership="주택보유") == "INELIGIBLE"
    assert v(nid, marriage_date=date(2010, 1, 1), household_size=2) == "INELIGIBLE"


def test_template_choice_and_extractor():
    assert X.choose_template("LH", "신혼희망타운(분양)") == "lh.newlywed_town_sale"
    import source_verify as sv
    f45 = X.extract(sv.pdf_pages("N45"))["fields"]
    assert f45["open_quote"].status == X.FILLED and f45["residence"].value is None
    f46 = X.extract(sv.pdf_pages("N46"))["fields"]
    assert f46["open_quote"].status == X.ABSENT and f46["residence"].value == "수도권"
    assert all(q.status == X.FILLED for q in f46["layer_quotes"].values())
    assert [u["name"] for u in load_notice("N48").meta["unsupported_layers"]] == ["사전청약당첨자"]
