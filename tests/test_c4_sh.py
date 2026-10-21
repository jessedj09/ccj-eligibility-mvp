# -*- coding: utf-8 -*-
"""test_c4_sh.py — C4b: SH 신혼·신생아 매입임대Ⅰ(N18)·Ⅱ(N19), 일반주택형 미리내집(N20·N21), 장기미임대(N22).

기준값은 원문에서 손으로 옮겼다:
- SH21(N18, 공고 2026.9.30) p.12: 신생아 '24.10.1 이후, 혼인신고 '19.10.1~'26.9.30, 6세 이하 '19.10.1 이후,
  지원대상 한부모는 미성년 자녀('07.10.1 이후 출생) 필요. p.16: 70% — 2인 4,693,016 / 3인 5,717,900 / 4인 6,161,541 /
  5인 6,528,890, 90% — 2인 5,866,270 / 3인 7,351,586, 6인 이상 = 5인 + 405,494(90%는 521,350). 1인 칸 없음.
  자산 345/379/413M, 자동차 45.42/49.96/54.51M. 수급자(교육급여 포함)·지원대상 한부모·차상위는 검증 면제(예비신혼 제외).
- SH22(N19) p.10: 130% — 2인 8,212,778 / 3인 10,618,958 / 5인 12,125,081, 200% — 3인 16,336,858, 6인 이상 + 753,061.
  자산 362/396/431M, 자동차 기준 없음. 혼인가구 유형 추가.
- SH18(N20, 공고 8.14): 혼인신고 '19.08.15~, 신생아 '24.08.15 이후. SH19(N21, 공고 8.24): '19.8.25~, '24.8.25 이후.
- SH20(N22) p.6: 공고일 현재 서울 주민등록 성년 무주택세대구성원. 소득 130%는 1순위 기준일 뿐 자격요건이 아님.
"""

from datetime import date, timedelta

import pytest
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate, marriage_cutoff, years_before

NW = "신혼·신생아"
DAY = timedelta(days=1)


def run(nid, layer=NW, **kw):
    base = dict(profile_id="T", age=33, marital_status="혼인중", home_ownership="무주택", household_size=3,
                marriage_date=date(2024, 1, 1), monthly_income=1_000_000, total_assets=10_000_000, car_value=0,
                children_birth_dates=[], welfare_status="해당없음", is_supported_single_parent=False)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), layer)


def v(*a, **kw):
    return run(*a, **kw).verdict


def codes(r):
    return {x.code for x in r.review_reasons.values()}


# --- SH 기준일 관행: 공고일−N년의 다음 날 ---------------------------------------------------------
@pytest.mark.parametrize("nid,marriage,newborn", [
    ("N18", date(2019, 10, 1), date(2024, 10, 1)), ("N19", date(2019, 10, 1), date(2024, 10, 1)),
    ("N20", date(2019, 8, 15), date(2024, 8, 15)), ("N21", date(2019, 8, 25), date(2024, 8, 25)),
])
def test_sh_cutoffs_are_one_day_later_than_lh_convention(nid, marriage, newborn):
    ann = load_notice(nid).announcement_date
    assert marriage == marriage_cutoff(ann) + DAY            # LH 공식(공고일−7년 당일)보다 하루 늦다
    assert newborn == years_before(ann, 2) + DAY
    assert "신혼부부" in run(nid, marriage_date=marriage).eligible_tracks
    # LH 관행이라면 7년 이내인 날(공고일−7년 당일)이 SH에서는 7년 초과다
    assert "신혼부부" not in run(nid, marriage_date=marriage - DAY).eligible_tracks
    kid = lambda d: dict(marital_status="미혼", children_birth_dates=[d], household_size=2)
    assert "신생아가구" in run(nid, **kid(newborn)).eligible_tracks
    assert "신생아가구" not in run(nid, **kid(newborn - DAY)).eligible_tracks


def test_supported_single_parent_needs_a_minor_child_only_where_stated():
    sp = dict(marital_status="한부모", is_supported_single_parent=True, household_size=2)
    assert "지원대상한부모" in run("N18", **sp, children_birth_dates=[date(2007, 10, 1)]).eligible_tracks
    assert "지원대상한부모" not in run("N18", **sp, children_birth_dates=[date(2007, 9, 30)]).eligible_tracks  # 성년 자녀뿐
    assert "지원대상한부모" in run("N20", **sp, children_birth_dates=[date(2007, 9, 30)]).eligible_tracks  # SH18엔 조건 없음


# --- 소득 상한(원문 금액 + 6인 이상 규칙, 1인 없음) -------------------------------------------------
@pytest.mark.parametrize("nid,size,dual,limit", [
    ("N18", 2, False, 4_693_016), ("N18", 3, False, 5_717_900), ("N18", 5, False, 6_528_890),
    ("N18", 3, True, 7_351_586), ("N18", 6, False, 6_528_890 + 405_494), ("N18", 7, True, 8_394_287 + 521_350 * 2),
    ("N19", 2, False, 8_212_778), ("N19", 3, False, 10_618_958), ("N19", 3, True, 16_336_858),
    ("N19", 6, False, 12_125_081 + 753_061), ("N20", 4, True, 17_604_404), ("N21", 5, True, 18_653_970),
])
def test_sh_income_limits(nid, size, dual, limit):
    kw = dict(household_size=size, dual_income=dual)
    assert v(nid, **kw, monthly_income=limit) == "ELIGIBLE"
    assert v(nid, **kw, monthly_income=limit + 1) == "INELIGIBLE"


@pytest.mark.parametrize("nid", ["N18", "N19", "N20", "N21"])
def test_single_person_household_is_not_in_the_sh_table(nid):
    r = run(nid, marital_status="미혼", household_size=1, children_birth_dates=[date(2026, 12, 1)])  # 태아만
    assert r.verdict == "MANUAL_REVIEW" and "AMBIGUOUS_SOURCE" in codes(r)


# --- 자산 ---------------------------------------------------------------------------------------
def test_sh_assets_and_car():
    kid = dict(children_birth_dates=[date(2025, 1, 1)])
    assert v("N18", **kid, total_assets=379_000_000, car_value=49_960_000) == "ELIGIBLE"
    assert v("N18", **kid, total_assets=379_000_001) == "INELIGIBLE"
    assert v("N18", **kid, car_value=49_960_001) == "INELIGIBLE"
    assert v("N18", total_assets=345_000_001) == "INELIGIBLE"
    assert v("N19", **kid, total_assets=396_000_000, car_value=90_000_000) == "ELIGIBLE"    # 자동차 개별 기준 없음
    assert v("N19", total_assets=362_000_001) == "INELIGIBLE"
    two = dict(children_birth_dates=[date(2025, 1, 1), date(2015, 1, 1)])                   # 이후 1 + 기존 미성년 1
    assert v("N20", **two, total_assets=431_000_000) == "ELIGIBLE"
    assert v("N20", **two, total_assets=431_000_001) == "INELIGIBLE"


def test_sh_exemption_includes_education_benefit_but_not_prospective_couples():
    rich = dict(monthly_income=90_000_000, total_assets=900_000_000)
    assert v("N18", welfare_status="교육급여만 수급", **rich) == "ELIGIBLE"     # SH는 교육급여 포함(p.17)
    assert v("N18", welfare_status="차상위계층", **rich) == "ELIGIBLE"
    assert v("N18", marital_status="예비신혼", welfare_status="차상위계층", monthly_income=90_000_000) == "INELIGIBLE"
    assert v("N18", marital_status="예비신혼", welfare_status="차상위계층", total_assets=900_000_000) == "INELIGIBLE"


def test_married_type_only_in_sh_II():
    old = dict(marriage_date=date(2010, 1, 1))          # 혼인 7년 초과, 자녀 없음
    assert v("N18", **old) == "INELIGIBLE"
    assert run("N19", **old).eligible_tracks == ["혼인가구"]
    assert run("N20", **old).eligible_tracks == ["혼인가구"]


# --- 장기미임대 -----------------------------------------------------------------------------------
@pytest.mark.parametrize("kw,verdict", [
    (dict(residence_area="서울특별시"), "ELIGIBLE"),
    (dict(residence_area="고양시"), "INELIGIBLE"),            # 연접 지역이라도 서울 주민등록이어야 함
    (dict(residence_area=None), "NEEDS_INFO"),
    (dict(residence_area="서울특별시", monthly_income=None, total_assets=None), "ELIGIBLE"),  # 소득은 순위 전용
    (dict(residence_area="서울특별시", monthly_income=90_000_000), "ELIGIBLE"),
    (dict(residence_area="서울특별시", age=18), "MANUAL_REVIEW"),
    (dict(residence_area="서울특별시", home_ownership="주택보유"), "INELIGIBLE"),
])
def test_long_term_vacant(kw, verdict):
    assert v("N22", "일반", **kw) == verdict
