# -*- coding: utf-8 -*-
"""test_g2_integrated.py — G2: 통합공공임대 일반형(N35 평창장평, LH 표준 공고) 일반공급 판정.

기준값은 원문에서 손으로 옮겼다(엔진 출력을 복사하지 않음) — 평창장평 p.14 기준중위소득표(보건복지부고시 제2025-135호,
2026년)·p.16~18 일반공급 신청자격·p.17 최종 소득·자산 기준표:
- 일반·고령자·한부모: 150%(1인 +20%p, 2인 +10%p, 출산자녀 1명 +10%p·2명 이상 +20%p) —
  1인 170% 4,359,205 / 2인 160% 6,718,867 / 3인 150% 8,038,554 / 4인 150% 9,742,107 / 8인 150% 15,711,522,
  2인 출산자녀 1명 170% 7,138,796 / 3인 출산자녀 1명 160% 8,574,458 / 4인 출산자녀 2명 170% 11,041,055.
- 신혼부부 맞벌이 +30%p: 2인 190% 7,978,655 / 3인 180% 9,646,265 / 3인 출산자녀 1명 190% 10,182,168 /
  4인 출산자녀 2명 200% 12,989,476.
- 청년: 본인 소득(세대원이 있는 세대주는 세대 전체) — 세대원은 1인 170% 4,359,205. 18세 이상 39세 이하, 혼인 중 아님.
- 고령자: 65세 이상(1961.10.30. 이전 출생). 자산 34,500만(37,900만·41,300만), 자동차 4,542만(4,996만·5,451만).
- 신혼부부: 혼인 7년 이내 / 예비신혼 / 6세 이하 자녀(2019.10.31. 이후 출생). 한부모: 6세 이하 자녀(2019.10.31. 이후 출생).
"""
import sys
from datetime import date
from pathlib import Path

import pytest
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

NEW1, NEW2, OLD = date(2024, 1, 1), date(2025, 6, 1), date(2015, 1, 1)


def v(layer="일반", **kw):
    base = dict(profile_id="T", age=45, marital_status="혼인중", home_ownership="무주택", household_size=3,
                monthly_income=1_000_000, total_assets=10_000_000, car_value=0, children_birth_dates=[],
                marriage_date=date(2010, 1, 1), house_head_status="세대주")
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice("N35"), layer).verdict


@pytest.mark.parametrize("layer", ["일반", "고령자"])
@pytest.mark.parametrize("size,kids,limit", [
    (1, [], 4_359_205), (2, [], 6_718_867), (3, [], 8_038_554), (4, [], 9_742_107), (8, [], 15_711_522),
    (2, [NEW1], 7_138_796), (3, [NEW1], 8_574_458), (4, [NEW1, NEW2], 11_041_055), (4, [NEW1, OLD], 11_041_055),
    (3, [OLD], 8_038_554),                       # 기준일 이전 출생 자녀만 있으면 가산 없음
])
def test_income_limit_general_and_elderly(layer, size, kids, limit):
    kw = dict(household_size=size, children_birth_dates=kids, age=70 if layer == "고령자" else 45)
    assert v(layer, **kw, monthly_income=limit) == "ELIGIBLE"
    assert v(layer, **kw, monthly_income=limit + 1) == "INELIGIBLE"


@pytest.mark.parametrize("dual,size,kids,limit", [
    (True, 2, [], 7_978_655), (True, 3, [], 9_646_265), (True, 3, [NEW1], 10_182_168), (True, 4, [NEW1, NEW2], 12_989_476),
    (False, 2, [], 6_718_867), (False, 3, [NEW1], 8_574_458), (False, 4, [NEW1, NEW2], 11_041_055),
])
def test_newlywed_income_with_dual_bonus(dual, size, kids, limit):
    kw = dict(dual_income=dual, household_size=size, children_birth_dates=kids, marriage_date=date(2024, 5, 1))
    assert v("신혼부부", **kw, monthly_income=limit) == "ELIGIBLE"
    assert v("신혼부부", **kw, monthly_income=limit + 1) == "INELIGIBLE"


def test_newlywed_marriage_seven_years_or_child_under_7():
    kw = dict(household_size=2)
    assert v("신혼부부", **kw, marriage_date=date(2019, 10, 30)) == "ELIGIBLE"      # 공고일 7년 전 당일 포함
    assert v("신혼부부", **kw, marriage_date=date(2019, 10, 29)) == "INELIGIBLE"
    kid = dict(household_size=3, marriage_date=date(2015, 1, 1))
    assert v("신혼부부", **kid, children_birth_dates=[date(2019, 10, 31)]) == "ELIGIBLE"
    assert v("신혼부부", **kid, children_birth_dates=[date(2019, 10, 30)]) == "INELIGIBLE"
    assert v("신혼부부", marital_status="예비신혼", household_size=2, marriage_date=None) == "ELIGIBLE"
    assert v("신혼부부", marital_status="미혼", household_size=2) == "INELIGIBLE"


def test_inconsistent_newlywed_household_is_review():
    assert v("신혼부부", household_size=1, marriage_date=date(2024, 5, 1)) == "MANUAL_REVIEW"
    assert v("신혼부부", household_size=2, children_birth_dates=[NEW1], marriage_date=date(2024, 5, 1)) == "MANUAL_REVIEW"


def test_youth_age_marriage_and_own_income():
    kw = dict(marital_status="미혼", household_size=4, house_head_status="세대원", monthly_income=4_359_205)
    assert v("청년", age=18, **kw) == "ELIGIBLE"
    assert v("청년", age=39, **kw) == "ELIGIBLE"
    assert v("청년", age=40, **kw) == "INELIGIBLE"
    assert v("청년", age=17, **kw) == "INELIGIBLE"
    assert v("청년", age=30, **dict(kw, monthly_income=4_359_206)) == "INELIGIBLE"   # 세대원은 본인 1인 170%
    assert v("청년", age=30, **dict(kw, marital_status="혼인중")) == "INELIGIBLE"
    # 세대원이 있는 세대주는 세대 전체 — 2인 160%
    head = dict(marital_status="미혼", age=30, household_size=2, house_head_status="세대주")
    assert v("청년", **head, monthly_income=6_718_867) == "ELIGIBLE"
    assert v("청년", **head, monthly_income=6_718_868) == "INELIGIBLE"


def test_single_parent_needs_child_under_7():
    kw = dict(marital_status="한부모", household_size=2, monthly_income=6_718_867)
    assert v("한부모", **kw, children_birth_dates=[date(2019, 10, 31)]) == "ELIGIBLE"
    assert v("한부모", **kw, children_birth_dates=[date(2019, 10, 30)]) == "INELIGIBLE"
    assert v("한부모", **dict(kw, monthly_income=6_718_868), children_birth_dates=[date(2022, 1, 1)]) == "INELIGIBLE"


def test_elderly_age_and_assets():
    assert v("고령자", age=65) == "ELIGIBLE"
    assert v("고령자", age=64) == "INELIGIBLE"
    for kids, assets, car in [([], 345_000_000, 45_420_000), ([NEW1], 379_000_000, 49_960_000),
                              ([NEW1, NEW2], 413_000_000, 54_510_000)]:
        kw = dict(age=70, household_size=4, children_birth_dates=kids)
        assert v("고령자", **kw, total_assets=assets, car_value=car) == "ELIGIBLE"
        assert v("고령자", **kw, total_assets=assets + 1) == "INELIGIBLE"
        assert v("고령자", **kw, car_value=car + 1) == "INELIGIBLE"


def test_home_and_adult():
    assert v(home_ownership="주택보유") == "INELIGIBLE"
    assert v(age=18) == "MANUAL_REVIEW"             # 미성년 예외(자녀 양육 미성년 세대주 등)는 화면이 묻지 않는다


def test_template_choice_and_job_linked_variant_is_blocked():
    assert X.choose_template("LH", "통합공공임대주택") == "lh.integrated_rental"
    assert X.choose_template("SH", "통합공공임대주택") is None
    pages = ["담양삼만통합공공임대주택[일자리연계형지원주택]입주자추가모집"]
    assert "일자리연계형" in X.variant_notice("lh.integrated_rental", pages)
    assert X.variant_notice("lh.integrated_rental", ["평창장평통합공공임대주택(일반형)입주자모집공고"]) is None
    assert X.variant_notice("lh.national_rental", pages) is None
