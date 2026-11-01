# -*- coding: utf-8 -*-
"""test_g3_sh_land_sale.py — G3-3: SH 토지임대부 분양 판정 틀(sh.land_sale, N51 마곡17·N52 고덕강일3).

기준은 원문에서 손으로 옮겼다(마곡17단지):
- p.28 청년: "19세이상~39세이하로혼인중이아니며,과거주택을소유한사실이없는무주택자", 저축 6개월·6회, 본인·부모 각 총자산,
  본인 소득 1인 140% 5,338,708원(출산 150% 5,720,045 · 160% 6,101,381) / <표3> 본인 276백만(311·345), 부모 1,035백만.
- 세대 총자산 362백만(397·431), 신혼부부·생애최초 130%, 신생아 140%, 일반공급 100%(맞벌이 200%) — 3인 이하 9,793,892(130%).
- p.5·p.33 투기과열지구 생애최초 1순위: 가입 2년·24회, 세대주, 세대 전원 5년 내 당첨 없음.
"""
import sys
from datetime import date
from pathlib import Path

import pytest
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

NEW1 = date(2024, 1, 1)


def v(layer, nid="N51", **kw):
    youth = layer == "청년"
    base = dict(profile_id="T", age=30 if youth else 35, marital_status="미혼" if youth else "혼인중", home_ownership="무주택",
                household_size=1 if youth else 3, monthly_income=3_000_000, total_assets=100_000_000, car_value=0,
                parents_total_assets=500_000_000, children_birth_dates=[NEW1] if layer == "신생아" else [],
                marriage_date=date(2024, 5, 1), residence_area="서울특별시", house_head_status="세대주",
                has_subscription_account=True, subscription_months=24, subscription_payment_count=24, subscription_deposit=10_000_000,
                rewin_restricted=False, past_special_supply=False, household_ever_owned_home=False, income_tax_5y=True,
                self_ever_owned_home=False, household_won_5y=False)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), layer).verdict


@pytest.mark.parametrize("nid", ["N51", "N52"])
def test_youth_own_income_assets_and_parents(nid):
    assert v("청년", nid, monthly_income=5_338_708, total_assets=276_000_000) == "ELIGIBLE"
    assert v("청년", nid, monthly_income=5_338_709) == "INELIGIBLE"
    assert v("청년", nid, total_assets=276_000_001) == "INELIGIBLE"
    assert v("청년", nid, monthly_income=5_720_045, children_birth_dates=[NEW1], household_size=2) == "ELIGIBLE"   # 출산 1명 150%
    assert v("청년", nid, parents_total_assets=1_035_000_001) == "INELIGIBLE"
    assert v("청년", nid, age=40) == v("청년", nid, marital_status="혼인중") == "INELIGIBLE"
    assert v("청년", nid, self_ever_owned_home=True) == "INELIGIBLE"


@pytest.mark.parametrize("nid", ["N51", "N52"])
def test_household_types_income_and_total_assets(nid):
    assert v("신혼부부", nid, monthly_income=9_793_892, total_assets=362_000_000) == "ELIGIBLE"
    assert v("신혼부부", nid, monthly_income=9_793_893) == v("신혼부부", nid, total_assets=362_000_001) == "INELIGIBLE"
    assert v("신혼부부", nid, dual_income=True, monthly_income=15_067_526) == "ELIGIBLE"
    assert v("일반공급", nid, monthly_income=7_533_763) == "ELIGIBLE"            # 일반공급도 소득 100%(주택형 무관)
    assert v("일반공급", nid, monthly_income=7_533_764) == "INELIGIBLE"
    assert v("신생아", nid, children_birth_dates=[date(2015, 1, 1)]) == "INELIGIBLE"


def test_first_home_needs_overheated_first_rank():
    assert v("생애최초") == "ELIGIBLE"
    assert v("생애최초", subscription_months=23) == "INELIGIBLE"              # 투기과열지구 1순위 2년·24회
    assert v("생애최초", house_head_status="세대원") == "INELIGIBLE"
    assert v("생애최초", household_won_5y=True) == "INELIGIBLE"
    assert v("생애최초", household_won_5y=None) == "NEEDS_INFO"


def test_template_and_extractor():
    assert X.choose_template("SH", "토지임대부 분양주택") == "sh.land_sale"
    assert X.choose_template("LH", "토지임대부 분양주택") is None
    import source_verify as sv
    f = X.extract(sv.pdf_pages("N51"))["fields"]
    assert (f["residence"].value, f["overheated"].value) == ("수도권", True)
    assert [u["name"] for u in load_notice("N52").meta["unsupported_layers"]] == ["사전청약당첨자"]
