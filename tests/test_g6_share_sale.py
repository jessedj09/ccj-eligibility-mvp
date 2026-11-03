# -*- coding: utf-8 -*-
"""test_g6_share_sale.py — G6: LH 나눔형(이익공유형) 공공분양 판정 틀(lh.share_sale, N56 뉴홈 4차 사전청약 2024.01.03.).

기준은 원문에서 손으로 옮겼다(2024.3. 규칙 개정 전 공고 — 신생아 특별공급 없음, 맞벌이 140%, 출생자녀 가산·자동차 한도 없음):
- 공통: 수도권(서울·경기·인천) 거주, 재당첨 제한 기간 아님, 특별공급 1회.
- p.9 청년: 19~39세·혼인 중 아님·본인 과거 주택 소유 없음, 저축 6개월·6회, 본인 소득 1인 140% 4,695,438원, 본인 총자산 289백만·부모 1,083백만.
- p.11 신혼부부: 혼인 7년·6세 이하 자녀 / 예비 / 한부모, 저축 6개월·6회, 130% 8,462,288원(맞벌이 140% 9,113,233원, 3인 이하).
- p.12 생애최초: 세대 과거 소유 없음, 1순위(1년·12회)·600만원, 혼인 중 또는 미혼 자녀, 본인 5년 소득세, 130%.
- p.13 일반공급: 저축 가입, 100%(4인 7,622,056원). 세대 총자산 379백만(p.7 <표3>).
"""
import sys
from datetime import date
from pathlib import Path

import draft
import pytest
import source_verify as sv
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

BASE = dict(profile_id="T", age=30, marital_status="미혼", household_size=1, monthly_income=4_000_000, total_assets=100_000_000,
            car_value=0, parents_total_assets=500_000_000, home_ownership="무주택", residence_area="고양시",
            children_birth_dates=[], rewin_restricted=False, past_special_supply=False, self_ever_owned_home=False,
            household_ever_owned_home=False, has_subscription_account=True, subscription_months=24,
            subscription_payment_count=24, subscription_deposit=10_000_000, income_tax_5y=True, dual_income=False,
            marriage_date=date(2022, 5, 1), house_head_status="세대주")
MARRIED = dict(marital_status="혼인중", household_size=2)


def v(layer, **kw):
    return evaluate(HouseholdProfile(**dict(BASE, **kw)), load_notice("N56"), layer).verdict


def test_youth_own_income_assets_parents_and_age():
    assert v("청년", monthly_income=4_695_438) == "ELIGIBLE" and v("청년", monthly_income=4_695_439) == "INELIGIBLE"
    assert v("청년", total_assets=289_000_000) == "ELIGIBLE" and v("청년", total_assets=289_000_001) == "INELIGIBLE"
    assert v("청년", parents_total_assets=1_083_000_001) == "INELIGIBLE"
    assert v("청년", age=40) == "INELIGIBLE" and v("청년", marital_status="혼인중") == "INELIGIBLE"
    assert v("청년", self_ever_owned_home=True) == "INELIGIBLE" and v("청년", residence_area="부산광역시") == "INELIGIBLE"


def test_newlywed_130_and_dual_140_before_2024_reform():
    assert v("신혼부부", **MARRIED, monthly_income=8_462_288) == "ELIGIBLE"
    assert v("신혼부부", **MARRIED, monthly_income=8_462_289) == "INELIGIBLE"
    assert v("신혼부부", **MARRIED, monthly_income=9_113_233, dual_income=True) == "ELIGIBLE"
    assert v("신혼부부", **MARRIED, monthly_income=9_113_234, dual_income=True) == "INELIGIBLE"   # 개정 뒤라면 200%
    assert v("신혼부부", **MARRIED, marriage_date=date(2015, 1, 1)) == "INELIGIBLE"                 # 혼인 7년 넘음, 자녀 없음


def test_first_home_and_general_supply():
    assert v("생애최초", **dict(MARRIED, household_size=3), monthly_income=8_462_288) == "ELIGIBLE"
    assert v("생애최초", **MARRIED, subscription_months=11) == "INELIGIBLE"
    assert v("생애최초", **MARRIED, subscription_deposit=5_999_999) == "INELIGIBLE"
    assert v("생애최초", **MARRIED, household_ever_owned_home=True) == "INELIGIBLE"
    assert v("일반공급", household_size=4, monthly_income=7_622_056) == "ELIGIBLE"
    assert v("일반공급", household_size=4, monthly_income=7_622_057) == "INELIGIBLE"
    assert v("일반공급", total_assets=379_000_001) == "INELIGIBLE"
    assert v("일반공급", has_subscription_account=False) == "INELIGIBLE"


def test_unseen_draft_matches_and_post_reform_notice_is_not_judged():
    assert X.choose_template("LH", "공공분양(나눔형)") == "lh.share_sale" and "lh.share_sale" in draft.PASSING
    assert X.choose_template("SH", "공공분양(나눔형)") is None
    d = draft.make_draft(sv.pdf_path("N56").read_bytes(), only=None, pages=sv.pdf_pages("N56"), exclude="N56")
    assert d.status == draft.OK and d.template == "lh.share_sale" and not d.held_fields
    reg = load_notice("N56")
    assert set(d.notice.layers) == set(reg.layers)
    for layer, kw in (("청년", {}), ("청년", dict(monthly_income=4_695_439)), ("신혼부부", dict(**MARRIED, dual_income=True,
                      monthly_income=9_000_000)), ("생애최초", MARRIED), ("일반공급", dict(household_size=4, monthly_income=7_622_057))):
        p = HouseholdProfile(**dict(BASE, **kw))
        assert evaluate(p, d.notice, layer).verdict == evaluate(p, reg, layer).verdict, (layer, kw)
    # 2024.3. 개정 뒤 공고처럼 맞벌이가 200%면 판정 틀의 리터럴과 달라 자동 판정하지 않는다(필수 값 보류)
    pages = [t.replace("맞벌이도시근로자가구당월평균소득액의140%9,113,233원", "맞벌이도시근로자가구당월평균소득액의200%13,018,904원")
             for t in sv.pdf_pages("N56")]
    f = X._share_sale(pages)
    assert f["dual_quote"].status == X.HELD and X.is_critical("lh.share_sale", "dual_quote")


@pytest.mark.parametrize("layer", ["청년", "신혼부부", "생애최초", "일반공급"])
def test_every_layer_requires_capital_residence_and_no_rewin(layer):
    kw = MARRIED if layer in ("신혼부부", "생애최초") else {}
    assert v(layer, **kw, residence_area="부산광역시") == "INELIGIBLE"
    assert v(layer, **kw, rewin_restricted=True) == "INELIGIBLE"
