# -*- coding: utf-8 -*-
"""test_g7_select_rental.py — G7: LH 선택형 공공임대 판정 틀(lh.select_rental, N57 뉴홈 4차 사전청약 2024.01.04.).

기준은 원문에서 손으로 옮겼다(2024.3. 규칙 개정 전 — 신생아 특별공급 없음, 다자녀 3명, 출생자녀 가산 없음):
- 공통: 수도권 거주, 재당첨 제한 기간 아님, 특별공급 1회, 세대 총자산 379백만(청년은 본인 289백만·부모 1,083백만).
- 소득(잔여공급 기준, 2023년도 가구원수별 표): 일반 1인 120% 4,024,661·2인 110% 5,505,914·3인 이상 100%(4인 7,622,056),
  다자녀 120%(5인 9,648,590), 노부모부양 2인 130% 6,506,989·3인 이상 120%, 생애최초 2인 140% 7,007,526·3인 이상 130%(3인 8,733,657),
  신혼부부 2인 140%(맞벌이 150% 7,508,064)·3인 이상 130%(맞벌이 140% 9,405,477), 청년 본인 1인 140% 4,695,438.
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
            marriage_date=date(2022, 5, 1), house_head_status="세대주", supports_elderly_parent_3y=True)
KIDS3 = [date(2010, 1, 1), date(2012, 1, 1), date(2015, 1, 1)]


def v(layer, **kw):
    return evaluate(HouseholdProfile(**dict(BASE, **kw)), load_notice("N57"), layer).verdict


def married(size, **kw):
    return dict(marital_status="혼인중", household_size=size, **kw)


def test_general_supply_size_relaxed_ratios():
    assert v("일반공급", monthly_income=4_024_661) == "ELIGIBLE" and v("일반공급", monthly_income=4_024_662) == "INELIGIBLE"
    assert v("일반공급", household_size=2, monthly_income=5_505_914) == "ELIGIBLE"
    assert v("일반공급", household_size=2, monthly_income=5_505_915) == "INELIGIBLE"
    assert v("일반공급", household_size=4, monthly_income=7_622_056) == "ELIGIBLE"
    assert v("일반공급", household_size=4, monthly_income=7_622_057) == "INELIGIBLE"
    assert v("일반공급", total_assets=379_000_001) == "INELIGIBLE"


def test_special_supplies():
    assert v("다자녀가구", **married(5, children_birth_dates=KIDS3, monthly_income=9_648_590)) == "ELIGIBLE"
    assert v("다자녀가구", **married(5, children_birth_dates=KIDS3, monthly_income=9_648_591)) == "INELIGIBLE"
    assert v("다자녀가구", **married(4, children_birth_dates=KIDS3[:2])) == "INELIGIBLE"              # 개정 전: 3명 이상
    assert v("노부모부양", **married(2, monthly_income=6_506_989)) == "ELIGIBLE"
    assert v("노부모부양", **married(2, monthly_income=6_506_990)) == "INELIGIBLE"
    assert v("노부모부양", **married(3), house_head_status="세대원") == "INELIGIBLE"
    assert v("생애최초", **married(2, monthly_income=7_007_526)) == "ELIGIBLE"
    assert v("생애최초", **married(3, monthly_income=8_733_658)) == "INELIGIBLE"
    assert v("신혼부부", **married(2, monthly_income=7_508_064, dual_income=True)) == "ELIGIBLE"
    assert v("신혼부부", **married(3, monthly_income=9_405_477, dual_income=True)) == "ELIGIBLE"
    assert v("신혼부부", **married(3, monthly_income=9_405_478, dual_income=True)) == "INELIGIBLE"
    assert v("청년", monthly_income=4_695_438) == "ELIGIBLE" and v("청년", parents_total_assets=1_083_000_001) == "INELIGIBLE"


def test_unseen_draft_matches_and_other_year_is_not_judged():
    assert X.choose_template("LH", "공공분양(선택형)") == "lh.select_rental" and "lh.select_rental" in draft.PASSING
    d = draft.make_draft(sv.pdf_path("N57").read_bytes(), only=None, pages=sv.pdf_pages("N57"), exclude="N57")
    assert d.status == draft.OK and d.template == "lh.select_rental" and not d.held_fields
    reg = load_notice("N57")
    assert set(d.notice.layers) == set(reg.layers)
    for layer, kw in (("일반공급", dict(household_size=2, monthly_income=5_505_915)), ("신혼부부", married(2, dual_income=True,
                      monthly_income=7_508_064)), ("노부모부양", married(2, monthly_income=6_506_990)), ("청년", {})):
        p = HouseholdProfile(**dict(BASE, **kw))
        assert evaluate(p, d.notice, layer).verdict == evaluate(p, reg, layer).verdict, (layer, kw)
    pages = [t.replace("379,000천원이하", "362,000천원이하") for t in sv.pdf_pages("N57")]
    assert X._select_rental(pages)["asset_quote"].status == X.HELD and X.is_critical("lh.select_rental", "asset_quote")


@pytest.mark.parametrize("layer", ["청년", "다자녀가구", "노부모부양", "생애최초", "신혼부부", "일반공급"])
def test_every_layer_requires_capital_residence_and_no_rewin(layer):
    kw = {"다자녀가구": married(5, children_birth_dates=KIDS3), "노부모부양": married(3), "생애최초": married(3),
          "신혼부부": married(3)}.get(layer, {})
    assert v(layer, **kw) == "ELIGIBLE"
    assert v(layer, **kw, residence_area="부산광역시") == "INELIGIBLE"
    assert v(layer, **kw, rewin_restricted=True) == "INELIGIBLE"
