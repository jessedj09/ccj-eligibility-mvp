# -*- coding: utf-8 -*-
"""test_select2026.py — 2026 판 LH 선택형 = 6년 분양전환 공공임대 최초 모집(N64 군포대야미 A-1 2026.06.30.).

기준은 원문에서 손으로 옮겼다(p.9~11·p.14~22, 2025년도 가구원수별 표 — 3인 이하를 3인으로 보지 않음):
- 일반 1인 120% 4,576,036·2인 110% 6,452,897·3인 100% 8,168,429, 맞벌이 200%(2인 11,732,540·3인 16,336,858)
- 다자녀 3인+ 120%(3인 9,802,115), 노부모 2인 130% 7,626,151, 생애최초·신혼 2인 140% 8,212,778·3인 130% 10,618,958,
  신생아 2인 150% 8,799,405·3인 140% 11,435,801, 출산자녀 1명 +10%p, 맞벌이 + 출산자녀 2명 이상(220%)은 원문 표에 없어 확인 필요
- 세대 총자산 362,000천원(출산 1명 397,000), 청년 본인 1인 140% 5,338,708·본인 276,000천원·부모 1,035,000천원
"""
import sys
from datetime import date
from pathlib import Path

import draft
import notice_candidates as nc
import source_verify as sv
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

BASE = dict(profile_id="T", age=30, marital_status="미혼", household_size=1, monthly_income=3_000_000, total_assets=100_000_000,
            car_value=0, parents_total_assets=500_000_000, home_ownership="무주택", residence_area="고양시",
            children_birth_dates=[], rewin_restricted=False, past_special_supply=False, self_ever_owned_home=False,
            household_ever_owned_home=False, has_subscription_account=True, subscription_months=24,
            subscription_payment_count=24, subscription_deposit=10_000_000, income_tax_5y=True, dual_income=False,
            marriage_date=date(2022, 5, 1), house_head_status="세대주", supports_elderly_parent_3y=True)
KIDS3 = [date(2010, 1, 1), date(2012, 1, 1), date(2015, 1, 1)]
NEWBORN = date(2025, 3, 1)           # 2세 미만(공고일 2026.06.30.)이고 '23.3.28. 이후 출생 — 출산 가산 1명


def v(layer, **kw):
    return evaluate(HouseholdProfile(**dict(BASE, **kw)), load_notice("N64"), layer).verdict


def married(size, **kw):
    return dict(marital_status="혼인중", household_size=size, **kw)


def test_title_goes_to_select_rental_2026():
    assert nc.classify(["-1-군포대야미지구A-1블록6년분양전환공공임대주택분양전환공공임대주택입주자모집공고", "LH청약플러스"])[1] == \
        "공공분양(선택형)"
    assert X._select_rental(sv.pdf_pages("N64"))["edition"].value == "2026"
    assert X._select_rental(sv.pdf_pages("N57"))["edition"].value == "2024"


def test_general_supply_by_household_size():
    assert v("일반공급", monthly_income=4_576_036) == "ELIGIBLE" and v("일반공급", monthly_income=4_576_037) == "INELIGIBLE"
    assert v("일반공급", **married(2, monthly_income=6_452_897)) == "ELIGIBLE"
    assert v("일반공급", **married(2, monthly_income=6_452_898)) == "INELIGIBLE"
    assert v("일반공급", **married(2, monthly_income=11_732_540, dual_income=True)) == "ELIGIBLE"
    assert v("일반공급", **married(3, monthly_income=8_168_429)) == "ELIGIBLE"
    assert v("일반공급", **married(3, monthly_income=8_168_430)) == "INELIGIBLE"
    assert v("일반공급", **married(3, total_assets=362_000_001)) == "INELIGIBLE"


def test_special_supplies():
    assert v("다자녀가구", **married(5, children_birth_dates=KIDS3[:2], monthly_income=11_192_382)) == "ELIGIBLE"
    assert v("다자녀가구", **married(5, children_birth_dates=KIDS3[:2], monthly_income=11_192_383)) == "INELIGIBLE"
    assert v("노부모부양", **married(2, monthly_income=7_626_151)) == "ELIGIBLE"
    assert v("노부모부양", **married(2, monthly_income=7_626_152)) == "INELIGIBLE"
    assert v("생애최초", **married(2, monthly_income=8_212_778)) == "ELIGIBLE"
    assert v("신혼부부", **married(3, monthly_income=10_618_958)) == "ELIGIBLE"
    assert v("신혼부부", **married(3, monthly_income=10_618_959)) == "INELIGIBLE"
    assert v("신생아", **married(3, children_birth_dates=[NEWBORN], monthly_income=12_252_644)) == "ELIGIBLE"     # 140% + 출산 10%p
    assert v("신생아", **married(3, children_birth_dates=[NEWBORN], monthly_income=12_252_645)) == "INELIGIBLE"
    assert v("청년", monthly_income=5_338_708) == "ELIGIBLE" and v("청년", monthly_income=5_338_709) == "INELIGIBLE"
    assert v("청년", total_assets=276_000_001) == "INELIGIBLE" and v("청년", parents_total_assets=1_035_000_001) == "INELIGIBLE"


def test_combinations_not_in_source_table_need_review():
    two_newborns = [date(2025, 3, 1), date(2026, 1, 1)]
    assert v("신생아", **married(4, children_birth_dates=two_newborns, dual_income=True, monthly_income=1)) != "ELIGIBLE"
    assert v("다자녀가구", **married(2, children_birth_dates=KIDS3[:2])) != "ELIGIBLE"


def test_unseen_draft_builds_without_missing_quotes():
    d = draft.make_draft(sv.pdf_path("N64").read_bytes(), only=None, pages=sv.pdf_pages("N64"), exclude="N64")
    assert d.status == draft.OK and d.template == "lh.select_rental" and d.missing == []
    assert [u["name"] for u in load_notice("N64").meta["unsupported_layers"]] == ["기관추천·국가유공자 특별공급", "사전청약 당첨자"]
