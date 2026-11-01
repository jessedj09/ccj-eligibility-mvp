# -*- coding: utf-8 -*-
"""test_g3_public_sale.py — G3: LH 공공분양 판정 틀(lh.public_sale, N49 양주회천 A-26·N50 안산신길2 B-1).

기준은 원문에서 손으로 옮겼다(양주회천 A-26):
- p.20~26 유형별 신청자격: 수도권 거주 + 무주택세대구성원 + 다자녀(19세 미만 자녀 2명 이상, 2007.8.28~2026.8.27 출생, 저축 6개월·6회,
  120%/맞벌이 200%) / 노부모(65세 이상 직계존속 3년 이상 부양 세대주, 1순위 1년·12회, 120%/200%) / 생애최초(세대 전원 과거 주택 소유 없음,
  1순위 + 저축액 600만원, 혼인 중 또는 미혼 자녀, 본인 5년 이상 소득세, 130%/200%) / 신혼부부(혼인 7년 '2019.8.27.~2026.8.27.' 또는
  6세 이하 자녀, 예비신혼, 6세 이하 자녀 한부모, 6개월·6회, 130%/200%) / 신생아(2세 미만 자녀 — 2세가 되는 날 포함, 140%/200%) /
  일반공급(입주자저축 가입, 전용 60㎡ 이하만 100%/200%·자산).
- p.15~17 부동산 215,500천원(237,050·258,600), 자동차 45,420천원(49,960·54,510), <표4>·<표5> 3인 이하 100% 7,533,763 ·
  120% 9,040,516 · 130% 9,793,892 · 140% 10,547,268 · 200% 15,067,526 · 210% 15,820,902, 4인 120% 10,562,642.
"""
import sys
from datetime import date
from pathlib import Path

import pytest
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

NEW1, NEW2, OLD = date(2024, 1, 1), date(2025, 6, 1), date(2015, 5, 5)
KIDS = {"다자녀가구": [NEW1, OLD], "신생아": [NEW2]}


def v(layer, nid="N49", **kw):
    base = dict(profile_id="T", age=35, marital_status="혼인중", home_ownership="무주택", household_size=3,
                monthly_income=3_000_000, total_assets=0, car_value=0, real_estate_value=0,
                children_birth_dates=KIDS.get(layer, []), marriage_date=date(2024, 5, 1), residence_area="고양시",
                house_head_status="세대주", has_subscription_account=True, subscription_months=24, subscription_payment_count=24,
                subscription_deposit=10_000_000, rewin_restricted=False, past_special_supply=False,
                household_ever_owned_home=False, income_tax_5y=True, supports_elderly_parent_3y=True)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), layer).verdict


@pytest.mark.parametrize("layer,limit", [("다자녀가구", 10_562_642), ("노부모부양", 9_040_516), ("생애최초", 9_793_892),
                                         ("신혼부부", 9_793_892), ("신생아", 10_547_268), ("일반공급(전용 60㎡ 이하)", 7_533_763)])
def test_income_base_ratio_by_type(layer, limit):
    kw = dict(household_size=4) if layer == "다자녀가구" else {}
    if layer == "다자녀가구":       # 4인, 23.3.28. 이후 출생 1명 + 기존 미성년 1명 → 가산 2명, 120% + 20%p = 140% 4인 12,323,083
        limit = 12_323_083
    if layer == "신생아":           # 2025.6.1. 출생 1명 → 140% + 10%p = 150% 3인 이하 11,300,645
        limit = 11_300_645
    assert v(layer, **kw, monthly_income=limit) == "ELIGIBLE"
    assert v(layer, **kw, monthly_income=limit + 1) == "INELIGIBLE"


def test_dual_income_200_and_large_general_has_no_income_limit():
    assert v("신혼부부", dual_income=True, monthly_income=15_067_526) == "ELIGIBLE"
    assert v("신혼부부", dual_income=True, monthly_income=15_067_527) == "INELIGIBLE"
    assert v("일반공급(전용 60㎡ 초과)", monthly_income=90_000_000, real_estate_value=900_000_000) == "ELIGIBLE"
    assert v("일반공급(전용 60㎡ 초과)", has_subscription_account=False) == "INELIGIBLE"


def test_real_estate_and_car_limits():
    assert v("신혼부부", real_estate_value=215_500_000) == "ELIGIBLE"
    assert v("신혼부부", real_estate_value=215_500_001) == "INELIGIBLE"
    assert v("신혼부부", car_value=45_420_001) == "INELIGIBLE"
    assert v("신혼부부", real_estate_value=None) == "NEEDS_INFO"


def test_type_requirements():
    assert v("다자녀가구", children_birth_dates=[NEW1]) == "INELIGIBLE"                       # 19세 미만 자녀 1명
    assert v("다자녀가구", household_size=4, children_birth_dates=[date(2007, 8, 28), NEW1]) == "ELIGIBLE"   # 원문 출생 범위 첫날
    assert v("다자녀가구", household_size=4, children_birth_dates=[date(2007, 8, 27), NEW1]) == "INELIGIBLE"
    assert v("노부모부양", supports_elderly_parent_3y=False) == v("노부모부양", house_head_status="세대원") == "INELIGIBLE"
    assert v("노부모부양", subscription_months=11) == "INELIGIBLE"
    assert v("생애최초", household_ever_owned_home=True) == v("생애최초", subscription_deposit=5_999_999) == "INELIGIBLE"
    assert v("생애최초", income_tax_5y=False) == "INELIGIBLE"
    assert v("생애최초", marital_status="미혼") == "MANUAL_REVIEW"       # 성년 미혼 자녀는 묻지 않는다
    assert v("신혼부부", marriage_date=date(2019, 8, 27)) == "ELIGIBLE"
    assert v("신혼부부", marriage_date=date(2019, 8, 26)) == "INELIGIBLE"
    assert v("신혼부부", marital_status="예비신혼", marriage_date=None) == "ELIGIBLE"
    assert v("신생아", children_birth_dates=[date(2024, 8, 27)]) == "ELIGIBLE"                # 2세가 되는 날 포함
    assert v("신생아", children_birth_dates=[date(2024, 8, 26)]) == "INELIGIBLE"


def test_common_region_rewin_and_special_history():
    assert v("신혼부부", residence_area="부산광역시") == "INELIGIBLE"
    assert v("신혼부부", rewin_restricted=True) == "INELIGIBLE"
    assert v("신혼부부", past_special_supply=True) == "MANUAL_REVIEW"        # 출산 특례는 원문 확인
    assert v("일반공급(전용 60㎡ 이하)", past_special_supply=True) == "ELIGIBLE"   # 일반공급은 특별공급 이력과 무관


def test_template_and_layers():
    assert X.choose_template("LH", "공공분양주택") == "lh.public_sale"
    assert X.choose_template("SH", "공공분양주택") is None
    assert "일반공급(전용 60㎡ 이하)" not in load_notice("N50").layers
    assert {u["name"] for u in load_notice("N50").meta["unsupported_layers"]} == {
        "사전청약당첨자", "기관추천·국가유공자 특별공급", "지역균형발전 특별공급"}
