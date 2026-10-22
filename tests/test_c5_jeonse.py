# -*- coding: utf-8 -*-
"""test_c5_jeonse.py — C5b: SH 장기전세2(미리내집) 7·8차(N23·N24), 장기전세 49·50차(N25·N26).

기준값은 원문에서 손으로 옮겼다:
- SH25(N23, 공고 2026.4.24) p.13: 혼인신고 2019.4.25. 이후, 5년 무소유 2021.4.25. 이후. p.16(60㎡ 이하) 120% — 2인 7,039,524 /
  3인 9,802,115, 맞벌이 180% — 3인 14,703,172. p.17(60㎡ 초과) 150% — 3인 12,252,644, 맞벌이 200% — 5인 18,653,970.
  자산 66,200/72,800/79,400만원, 자동차 4,542/4,996/5,451만원.
- SH26(N24, 공고 8.21) p.13: 혼인신고 2019.8.22. 이후. p.17 주거약자형 추가 자격 ①~⑦(65세 이상 포함).
- SH24(N26, 50차) p.23: 60㎡ 이하 105% — 1인 4,004,031 / 3인 8,576,850, 115% — 3인 9,393,693, 125% — 3인 10,210,536, 맞벌이 140% —
  3인 11,435,801. 60㎡ 초과 150% — 3인 12,252,644, 맞벌이 200% — 3인 16,336,858. 출생자녀 가산은 맞벌이와 중복하지 않음.
  자산 66,200만원·자동차 4,542만원 계열. p.20 상계장암지구는 의정부시 거주자 포함.
- SH23(N25, 49차, 공고 2025.12.15) p.23: 60㎡ 이하 105% — 3인 8,008,322, 60㎡ 초과 150% — 1인 5,397,246. p.24 자산 64,000만원,
  자동차 4,563만원.
"""

from datetime import date

import pytest
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

J2_LOW, J2_HIGH = "신혼부부(전용 60㎡ 이하)", "신혼부부(전용 60㎡ 초과)"
JS_LOW, JS_HIGH, JS_WEAK = "일반(전용 60㎡ 이하)", "일반(전용 60㎡ 초과)", "일반(주거약자형·전용 60㎡ 이하)"
KID1 = [date(2025, 1, 1)]
KID2 = [date(2025, 1, 1), date(2024, 6, 1)]


def run(nid, layer, **kw):
    base = dict(profile_id="T", age=33, marital_status="혼인중", home_ownership="무주택", household_size=3,
                marriage_date=date(2024, 1, 1), monthly_income=1_000_000, total_assets=10_000_000, car_value=0,
                children_birth_dates=[], residence_area="서울특별시", owned_home_in_5y=False)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), layer)


def v(*a, **kw):
    return run(*a, **kw).verdict


def codes(r):
    return {x.code for x in r.review_reasons.values()}


# --- 장기전세2(미리내집) ---------------------------------------------------------------------------
@pytest.mark.parametrize("nid", ["N23", "N24"])
@pytest.mark.parametrize("layer,size,dual,limit", [
    (J2_LOW, 2, False, 7_039_524), (J2_LOW, 3, False, 9_802_115), (J2_LOW, 3, True, 14_703_172),
    (J2_HIGH, 3, False, 12_252_644), (J2_HIGH, 5, True, 18_653_970),
])
def test_jeonse2_income_by_unit_size(nid, layer, size, dual, limit):
    kw = dict(household_size=size, dual_income=dual)
    assert v(nid, layer, **kw, monthly_income=limit) == "ELIGIBLE"
    assert v(nid, layer, **kw, monthly_income=limit + 1) == "INELIGIBLE"


def test_jeonse2_same_income_passes_large_unit_but_not_small():
    kw = dict(household_size=3, monthly_income=10_000_000)            # 120% 9,802,115 < 1천만 < 150% 12,252,644
    assert v("N23", J2_LOW, **kw) == "INELIGIBLE" and v("N23", J2_HIGH, **kw) == "ELIGIBLE"


@pytest.mark.parametrize("nid,marriage", [("N23", date(2019, 4, 25)), ("N24", date(2019, 8, 22))])
def test_jeonse2_marriage_cutoff_sh_convention(nid, marriage):
    from datetime import timedelta
    assert v(nid, J2_LOW, marriage_date=marriage) == "ELIGIBLE"
    assert v(nid, J2_LOW, marriage_date=marriage - timedelta(days=1)) == "INELIGIBLE"
    assert v(nid, J2_LOW, marital_status="예비신혼", marriage_date=None) == "ELIGIBLE"


@pytest.mark.parametrize("kw,verdict", [
    (dict(owned_home_in_5y=True), "INELIGIBLE"), (dict(owned_home_in_5y=None), "NEEDS_INFO"),
    (dict(residence_area="고양시"), "INELIGIBLE"), (dict(age=18), "MANUAL_REVIEW"),
    (dict(total_assets=662_000_000, car_value=45_420_000), "ELIGIBLE"), (dict(total_assets=662_000_001), "INELIGIBLE"),
    (dict(children_birth_dates=KID1, household_size=3, total_assets=728_000_000), "ELIGIBLE"),
    (dict(children_birth_dates=KID2, household_size=4, total_assets=794_000_000, car_value=54_510_000), "ELIGIBLE"),
    (dict(children_birth_dates=KID2, household_size=4, total_assets=794_000_001), "INELIGIBLE"),
])
def test_jeonse2_common_conditions(kw, verdict):
    assert v("N23", J2_LOW, **kw) == verdict


def test_jeonse2_table_gaps():
    r = run("N23", J2_LOW, household_size=1)
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {"INPUT_INCONSISTENT"}
    r = run("N23", J2_HIGH, household_size=6)
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {"AMBIGUOUS_SOURCE"}


def test_jeonse2_weak_unit_only_in_8th():
    layer = "신혼부부(주거약자형·전용 60㎡ 이하)"
    assert layer not in load_notice("N23").layers
    assert v("N24", layer, housing_weak_type="장애인") == "ELIGIBLE"
    assert v("N24", layer, housing_weak_type="해당없음") == "INELIGIBLE"
    assert v("N24", layer, housing_weak_type="해당없음", age=65) == "ELIGIBLE"


# --- 장기전세 --------------------------------------------------------------------------------------
@pytest.mark.parametrize("nid,layer,size,kids,dual,limit", [
    ("N26", JS_LOW, 1, [], False, 4_004_031), ("N26", JS_LOW, 3, [], False, 8_576_850),
    ("N26", JS_LOW, 3, KID1, False, 9_393_693), ("N26", JS_LOW, 3, KID2, False, 10_210_536),
    ("N26", JS_LOW, 3, [], True, 11_435_801), ("N26", JS_LOW, 3, KID2, True, 11_435_801),   # 맞벌이와 자녀 가산 중복 없음
    ("N26", JS_HIGH, 3, [], False, 12_252_644), ("N26", JS_HIGH, 3, [], True, 16_336_858),
    ("N25", JS_LOW, 3, [], False, 8_008_322), ("N25", JS_HIGH, 1, [], False, 5_397_246),
])
def test_jeonse_income_limits(nid, layer, size, kids, dual, limit):
    kw = dict(household_size=size, children_birth_dates=kids, dual_income=dual)
    assert v(nid, layer, **kw, monthly_income=limit) == "ELIGIBLE"
    assert v(nid, layer, **kw, monthly_income=limit + 1) == "INELIGIBLE"


@pytest.mark.parametrize("kw,code", [
    (dict(household_size=1, children_birth_dates=KID1), "INPUT_INCONSISTENT"),
    (dict(household_size=2, children_birth_dates=KID2), "INPUT_INCONSISTENT"),
    (dict(household_size=1, dual_income=True), "INPUT_INCONSISTENT"),
    (dict(household_size=7), "AMBIGUOUS_SOURCE"),
    (dict(residence_area="의정부시"), "AMBIGUOUS_SOURCE"),           # 상계장암지구만 포함
])
def test_jeonse_gaps_and_uijeongbu(kw, code):
    r = run("N26", JS_LOW, **kw)
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {code}


def test_jeonse_assets_by_round():
    assert v("N26", JS_LOW, total_assets=662_000_000, car_value=45_420_000) == "ELIGIBLE"
    assert v("N26", JS_LOW, total_assets=662_000_001) == "INELIGIBLE"
    assert v("N25", JS_LOW, total_assets=640_000_000, car_value=45_630_000) == "ELIGIBLE"   # 49차는 이전 연도 기준
    assert v("N25", JS_LOW, total_assets=640_000_001) == "INELIGIBLE"
    assert v("N25", JS_LOW, car_value=45_630_001) == "INELIGIBLE"
    assert v("N26", JS_LOW, residence_area="수원시") == "INELIGIBLE"


@pytest.mark.parametrize("nid", ["N25", "N26"])
def test_jeonse_weak_unit_and_unsupported_priority_supply(nid):
    assert v(nid, JS_WEAK, housing_weak_type="장애인") == "ELIGIBLE"
    assert v(nid, JS_WEAK, housing_weak_type="해당없음") == "INELIGIBLE"
    assert v(nid, JS_WEAK, housing_weak_type="해당없음", age=65) == "ELIGIBLE"
    assert any("우선공급" in u["name"] for u in load_notice(nid).meta["unsupported_layers"])
