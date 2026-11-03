# -*- coding: utf-8 -*-
"""test_g2_public.py — G2: 국민임대(N30 남양주마석·N31 김포, LH 표준 공고).

기준값은 원문에서 손으로 옮겼다(엔진 출력을 복사하지 않음) — 남양주마석 p.4~6, 김포 p.5·p.4 표:
- 신청자격: 공고일(2026.09.07) 현재 무주택세대구성원, 「민법」상 미성년자(19세 미만) 원칙적 불가(자녀 있는 미성년 세대주 등 예외).
- 소득 2025년 도시근로자 70%: 3인 5,717,900 / 4인 6,161,541 / 7인 7,339,879 / 8인 7,745,373원.
  가산: 1인 +20%p(90% 3,432,027), 2인 +10%p(80% 4,693,016), 출산자녀 1명 +10%p·2명 이상 +20%p
  (예: 3인 출산자녀 1명 80% 6,534,743, 2인 출산자녀 1명 90% 5,279,643, 4인 출산자녀 2명 90% 7,921,982).
- 자산 34,500만(출산자녀 1명 37,900만·2명 41,300만), 개별 자동차 4,542만(4,996만·5,451만).
- 출산자녀 = '23.3.28. 이후 출산한 미성년 자녀(태아 포함) — 있으면 기존 미성년 자녀까지 최대 2명.
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


def v(nid="N30", **kw):
    base = dict(profile_id="T", age=40, marital_status="혼인중", home_ownership="무주택", household_size=3,
                monthly_income=1_000_000, total_assets=10_000_000, car_value=0, children_birth_dates=[])
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), "일반").verdict


@pytest.mark.parametrize("nid", ["N30", "N31"])
@pytest.mark.parametrize("size,kids,limit", [
    (1, [], 3_432_027), (2, [], 4_693_016), (3, [], 5_717_900), (4, [], 6_161_541), (7, [], 7_339_879), (8, [], 7_745_373),
    (2, [NEW1], 5_279_643), (3, [NEW1], 6_534_743), (4, [NEW1, NEW2], 7_921_982), (4, [NEW1, OLD], 7_921_982),
    (3, [OLD], 5_717_900),                       # 기준일 이전 출생 자녀만 있으면 가산 없음
])
def test_income_limit_with_household_and_birth_bonus(nid, size, kids, limit):
    assert v(nid, household_size=size, children_birth_dates=kids, monthly_income=limit) == "ELIGIBLE"
    assert v(nid, household_size=size, children_birth_dates=kids, monthly_income=limit + 1) == "INELIGIBLE"


@pytest.mark.parametrize("kids,assets,car", [([], 345_000_000, 45_420_000), ([NEW1], 379_000_000, 49_960_000),
                                             ([NEW1, NEW2], 413_000_000, 54_510_000)])
def test_asset_and_car_limits_by_birth_children(kids, assets, car):
    kw = dict(household_size=4, children_birth_dates=kids)
    assert v(**kw, total_assets=assets, car_value=car) == "ELIGIBLE"
    assert v(**kw, total_assets=assets + 1) == "INELIGIBLE"
    assert v(**kw, car_value=car + 1) == "INELIGIBLE"


def test_home_and_adult():
    assert v(home_ownership="주택보유") == "INELIGIBLE"
    assert v(age=19) == "ELIGIBLE"
    assert v(age=18) == "MANUAL_REVIEW"             # 미성년 예외(자녀 있는 미성년 세대주 등)는 화면이 묻지 않는다


def test_inconsistent_household_is_review_and_9_persons_not_in_table():
    assert v(household_size=1, children_birth_dates=[NEW1]) == "MANUAL_REVIEW"
    assert v(household_size=9) != "ELIGIBLE"          # 원문 표는 8인까지


def test_template_and_extractor_choose_national_rental_for_lh_only():
    assert X.choose_template("LH", "국민임대주택") == "lh.national_rental"
    assert X.choose_template("SH", "국민임대주택") == "sh.national_rental"     # G5: SH 국민임대는 따로 만든 틀


# --- 영구임대(N33 양주회천 A25·N34 부천시, LH 영구임대 표준 공고) -------------------------------------------
# 양주 p.4·p.6·p.7·p.9 손계산: 일반입주자(차) 50% — 1인 70% 2,669,354 / 2인 60% 3,519,762 / 3인 50% 4,084,215원,
# 국가유공자 등(나) 70% — 3인 5,717,900원, 2순위 장애인(타) 100% — 3인 8,168,429원. 자산 2억4,500만(출생자녀 1명 2억7,000만).
def pv(nid="N33", layer="일반", **kw):
    base = dict(profile_id="T", age=40, marital_status="혼인중", home_ownership="무주택", household_size=3,
                monthly_income=1_000_000, total_assets=10_000_000, car_value=0, children_birth_dates=[],
                residence_area="양주시" if nid == "N33" else "부천시", welfare_status="해당없음",
                is_supported_single_parent=False, housing_weak_type="해당없음", disabled_spouse_qualifies=False,
                livelihood_medical_recipient=False, merit_person=False, north_korean_defector=False,
                child_facility_leaver=False, supports_elderly_parent=False)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), layer).verdict


@pytest.mark.parametrize("nid", ["N33", "N34"])
@pytest.mark.parametrize("size,limit", [(1, 2_669_354), (2, 3_519_762), (3, 4_084_215)])
def test_permanent_general_applicant_50pct(nid, size, limit):
    assert pv(nid, household_size=size, monthly_income=limit) == "ELIGIBLE"
    assert pv(nid, household_size=size, monthly_income=limit + 1) == "INELIGIBLE"


def test_permanent_status_tracks_have_their_own_income_rule():
    assert pv(merit_person=True, monthly_income=5_717_900) == "ELIGIBLE"           # 나목 70%
    assert pv(merit_person=True, monthly_income=5_717_901) == "INELIGIBLE"
    assert pv(north_korean_defector=True, monthly_income=5_717_900) == "ELIGIBLE"  # 마목
    assert pv(housing_weak_type="장애인", monthly_income=8_168_429) == "ELIGIBLE"  # 타목 100%
    assert pv(housing_weak_type="장애인", monthly_income=8_168_430) == "INELIGIBLE"
    assert pv(disabled_spouse_qualifies=True, monthly_income=8_168_429) == "ELIGIBLE"
    # 소득·자산 검증 없는 신분: 가목(생계·의료급여)·라목(지원대상 한부모)·자목(65세 이상 수급권자·차상위)
    rich = dict(monthly_income=50_000_000, total_assets=900_000_000)
    assert pv(livelihood_medical_recipient=True, **rich) == "ELIGIBLE"
    assert pv(is_supported_single_parent=True, **rich) == "ELIGIBLE"
    assert pv(age=65, welfare_status="차상위계층", **rich) == "ELIGIBLE"
    assert pv(age=64, welfare_status="차상위계층", **rich) == "INELIGIBLE"
    assert pv(supports_elderly_parent=True, **rich) == "MANUAL_REVIEW"            # 사목: 소득인정액은 계산하지 않음


def test_permanent_assets_residence_and_weak_layer():
    assert pv(total_assets=245_000_000) == "ELIGIBLE"
    assert pv(total_assets=245_000_001) == "INELIGIBLE"
    assert pv(children_birth_dates=[NEW1], total_assets=270_000_000, monthly_income=4_901_057) == "ELIGIBLE"  # 출생자녀 1명: 60%
    assert pv(residence_area="서울특별시") == "INELIGIBLE"
    assert pv("N34", residence_area="양주시") == "INELIGIBLE"
    assert pv(layer="일반(주거약자용)") == "INELIGIBLE"                                # 40세·주거약자 아님
    assert pv(layer="일반(주거약자용)", age=65) == "ELIGIBLE"
    assert pv(layer="일반(주거약자용)", housing_weak_type="장애인") == "ELIGIBLE"


def test_permanent_template_choice():
    assert X.choose_template(None, "영구임대주택") == "lh.permanent_rental"
    assert X.choose_template("SH", "영구임대주택") == "sh.permanent_rental"    # G5
    assert X.choose_template("LH", "고령자복지주택") == "lh.elderly_welfare"   # G5(영구임대형만 — kind가 확인)
