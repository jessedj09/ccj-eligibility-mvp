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
    assert X.choose_template("SH", "국민임대주택") is None     # SH 국민임대는 아직 검증 전
