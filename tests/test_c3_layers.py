# -*- coding: utf-8 -*-
"""test_c3_layers.py — C3 새 계층(고령자·산업단지근로자·주거급여수급자·지역전략산업종사자) 경계 검증.

기준값은 원문 표에서 손으로 옮겼다(엔진 출력을 복사하지 않음):
- 고령자 결합표(금천 p.13, 가좌 p.7, 오류 p.11): 1인0 120%·345M / 2인0 110%·345M / 2인1 120%·379M /
  3인+ 0·1·2+ = 100·110·120%, 345·379·413M. 자동차 45.42/49.96/54.51M.
- 산업단지근로자(금천 p.6): 맞벌이X 1인0 120 / 2인0 110 / 2인1 120(379M) / 3인+ 100·110·120.
  맞벌이O 2인0 130 / 3인0 120·3인1 130(379M) / 4인+ 120·130·140(413M). 1인 맞벌이 칸은 원문에 없음("-").
- 지역전략산업종사자(부천 p.7): 1인 120 / 2인 110(맞벌이 130) / 3인+ 100(맞벌이 120), 자산 3억4,500만·자동차 4,542만,
  출생자녀 가산 언급 없음.
- 소득 금액(2025 도시근로자): 1인120 4,576,036 / 2인110 6,452,897 / 2인120 7,039,524 / 2인130 7,626,151 /
  3인100 8,168,429 / 3인120 9,802,115 / 3인130 10,618,958 / 4인140 12,323,083.
"""

from datetime import date

import pytest
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

KID1 = [date(2024, 1, 1)]
KID2 = [date(2024, 1, 1), date(2025, 6, 1)]


def run(nid, layer, **kw):
    base = dict(profile_id="T", age=70, marital_status="미혼", home_ownership="무주택", household_size=1,
                monthly_income=1, total_assets=1, car_value=0, children_birth_dates=[])
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), layer)


def v(*a, **kw):
    return run(*a, **kw).verdict


def codes(result):
    return {x.code for x in result.review_reasons.values()}


# --- 고령자 -------------------------------------------------------------------------------------
@pytest.mark.parametrize("nid", ["N6", "N9", "N10"])
@pytest.mark.parametrize("size,kids,income,assets,car", [
    (1, [], 4_576_036, 345_000_000, 45_420_000),
    (2, [], 6_452_897, 345_000_000, 45_420_000),
    (2, KID1, 7_039_524, 379_000_000, 49_960_000),
    (3, [], 8_168_429, 345_000_000, 45_420_000),
    (3, KID2, 9_802_115, 413_000_000, 54_510_000),
])
def test_elderly_limits_exact_and_plus_one(nid, size, kids, income, assets, car):
    kw = dict(household_size=size, children_birth_dates=kids, monthly_income=income, total_assets=assets, car_value=car)
    assert v(nid, "고령자", **kw) == "ELIGIBLE"
    for key, val in (("monthly_income", income), ("total_assets", assets), ("car_value", car)):
        assert v(nid, "고령자", **{**kw, key: val + 1}) == "INELIGIBLE", key


@pytest.mark.parametrize("nid", ["N6", "N9", "N10"])
def test_elderly_age_and_home_and_no_subscription_requirement(nid):
    assert v(nid, "고령자", age=65) == "ELIGIBLE"
    assert v(nid, "고령자", age=64) == "INELIGIBLE"
    assert v(nid, "고령자", home_ownership="주택보유") == "INELIGIBLE"
    assert v(nid, "고령자", has_subscription_account=False, marital_status="혼인중") == "ELIGIBLE"


@pytest.mark.parametrize("nid", ["N6", "N9", "N10"])
def test_elderly_inconsistent_household_goes_to_manual_review(nid):
    r = run(nid, "고령자", household_size=1, children_birth_dates=KID1)
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {"INPUT_INCONSISTENT"}
    r = run(nid, "고령자", household_size=2, children_birth_dates=KID2)
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {"INPUT_INCONSISTENT"}


# --- 산업단지근로자 (N6) ------------------------------------------------------------------------------
WORKER = dict(age=30, industrial_workplace="산업단지 입주기업", workplace_area="서울특별시", industrial_affiliation="소속")


@pytest.mark.parametrize("size,kids,dual,income,assets", [
    (1, [], False, 4_576_036, 345_000_000),
    (2, [], False, 6_452_897, 345_000_000),
    (2, KID1, False, 7_039_524, 379_000_000),
    (3, [], False, 8_168_429, 345_000_000),
    (2, [], True, 7_626_151, 345_000_000),
    (3, [], True, 9_802_115, 345_000_000),
    (3, KID1, True, 10_618_958, 379_000_000),
    (4, KID2, True, 12_323_083, 413_000_000),
])
def test_industrial_worker_limits(size, kids, dual, income, assets):
    kw = dict(WORKER, household_size=size, children_birth_dates=kids, dual_income=dual,
              monthly_income=income, total_assets=assets, marital_status="혼인중" if dual else "미혼")
    assert v("N6", "산업단지근로자", **kw) == "ELIGIBLE"
    assert v("N6", "산업단지근로자", **{**kw, "monthly_income": income + 1}) == "INELIGIBLE"
    assert v("N6", "산업단지근로자", **{**kw, "total_assets": assets + 1}) == "INELIGIBLE"


@pytest.mark.parametrize("change,verdict", [
    ({"industrial_workplace": "경제자유구역 입주 중소기업"}, "ELIGIBLE"),
    ({"industrial_workplace": "산업단지 교육·연구기관"}, "ELIGIBLE"),
    ({"industrial_workplace": "해당없음"}, "INELIGIBLE"),
    ({"industrial_workplace": None}, "NEEDS_INFO"),
    ({"workplace_area": "고양시"}, "ELIGIBLE"),
    ({"workplace_area": "수원시"}, "INELIGIBLE"),          # 연접 13개 시 밖
    ({"workplace_area": None}, "NEEDS_INFO"),
    ({"industrial_affiliation": "비소속 1년 이상 근무(예정)"}, "ELIGIBLE"),
    ({"industrial_affiliation": "비소속 1년 미만"}, "INELIGIBLE"),
    ({"home_ownership": "주택보유"}, "INELIGIBLE"),
])
def test_industrial_worker_workplace_conditions(change, verdict):
    assert v("N6", "산업단지근로자", **{**WORKER, **change}) == verdict


@pytest.mark.parametrize("kw", [
    dict(household_size=1, dual_income=True),
    dict(household_size=1, children_birth_dates=KID1),
    dict(household_size=2, dual_income=True, children_birth_dates=KID1),
    dict(household_size=3, dual_income=True, children_birth_dates=KID2),
])
def test_industrial_worker_inconsistent_inputs(kw):
    r = run("N6", "산업단지근로자", **{**WORKER, **kw})
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {"INPUT_INCONSISTENT"}


# --- 주거급여수급자 (N10) -------------------------------------------------------------------------------
@pytest.mark.parametrize("status,verdict", [("수급자", "ELIGIBLE"), ("수급권자", "ELIGIBLE"),
                                            ("해당없음", "INELIGIBLE"), (None, "NEEDS_INFO")])
def test_housing_benefit_status(status, verdict):
    assert v("N10", "주거급여수급자", housing_benefit_status=status) == verdict


def test_housing_benefit_has_no_income_or_asset_clause():
    # 원문(오류 p.12)에 소득·자산 기준 조항이 없다 — 엔진이 기준을 만들어 내지 않는다
    r = run("N10", "주거급여수급자", housing_benefit_status="수급자", monthly_income=None, total_assets=None,
            household_size=4)
    assert r.verdict == "ELIGIBLE"
    assert v("N10", "주거급여수급자", housing_benefit_status="수급자", home_ownership="주택보유") == "INELIGIBLE"


# --- 지역전략산업종사자 (N5) ---------------------------------------------------------------------------
ARTIST = dict(age=30, regional_industry_type="등록 예술인")


@pytest.mark.parametrize("size,dual,income", [(1, False, 4_576_036), (2, False, 6_452_897), (2, True, 7_626_151),
                                              (3, False, 8_168_429), (3, True, 9_802_115)])
def test_regional_worker_income_limits(size, dual, income):
    kw = dict(ARTIST, household_size=size, dual_income=dual, monthly_income=income)
    assert v("N5", "지역전략산업종사자", **kw) == "ELIGIBLE"
    assert v("N5", "지역전략산업종사자", **{**kw, "monthly_income": income + 1}) == "INELIGIBLE"


def test_regional_worker_assets_and_age():
    assert v("N5", "지역전략산업종사자", **ARTIST, total_assets=345_000_000, car_value=45_420_000) == "ELIGIBLE"
    assert v("N5", "지역전략산업종사자", **ARTIST, total_assets=345_000_001) == "INELIGIBLE"
    assert v("N5", "지역전략산업종사자", **ARTIST, car_value=45_420_001) == "INELIGIBLE"
    assert v("N5", "지역전략산업종사자", **{**ARTIST, "age": 40}) == "INELIGIBLE"
    assert v("N5", "지역전략산업종사자", **{**ARTIST, "age": 19}) == "ELIGIBLE"


@pytest.mark.parametrize("kind,verdict", [("전문예술법인·단체 종사자", "ELIGIBLE"), ("등록 예술인", "ELIGIBLE"),
                                          ("콘텐츠산업 종사자", "MANUAL_REVIEW"), ("부천시 추천자", "MANUAL_REVIEW"),
                                          ("해당없음", "INELIGIBLE"), (None, "NEEDS_INFO")])
def test_regional_worker_type_and_city_verification(kind, verdict):
    r = run("N5", "지역전략산업종사자", age=30, regional_industry_type=kind)
    assert r.verdict == verdict
    if verdict == "MANUAL_REVIEW":
        assert codes(r) == {"SELF_REPORT_UNVERIFIED"}


def test_regional_worker_child_bonus_ambiguity_only_when_it_matters():
    kw = dict(ARTIST, household_size=3, children_birth_dates=KID1)
    # 3억6천만: 원문 그대로(345M) 불충족 / 가산 적용(379M) 충족 → 해석이 갈림
    r = run("N5", "지역전략산업종사자", **kw, total_assets=360_000_000)
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {"AMBIGUOUS_SOURCE"}
    assert v("N5", "지역전략산업종사자", **kw, total_assets=300_000_000) == "ELIGIBLE"      # 둘 다 충족
    assert v("N5", "지역전략산업종사자", **kw, total_assets=400_000_000) == "INELIGIBLE"    # 둘 다 불충족
    assert v("N5", "지역전략산업종사자", **ARTIST, household_size=3, total_assets=360_000_000) == "INELIGIBLE"  # 자녀 없음


def test_regional_worker_single_person_dual_income_is_inconsistent():
    r = run("N5", "지역전략산업종사자", **ARTIST, household_size=1, dual_income=True)
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {"INPUT_INCONSISTENT"}


# --- 메타 ---------------------------------------------------------------------------------------------
def test_new_layers_left_the_unsupported_list_and_housing_weak_units_are_listed():
    for nid, layers in {"N5": ["지역전략산업종사자"], "N6": ["고령자", "산업단지근로자"], "N9": ["고령자"],
                        "N10": ["고령자", "주거급여수급자"]}.items():
        notice = load_notice(nid)
        names = {u["name"] for u in notice.meta.get("unsupported_layers", [])}
        assert set(layers) <= set(notice.layers) and not set(layers) & names, nid
    for nid in ("N6", "N10"):
        assert any("주거약자" in u["name"] for u in load_notice(nid).meta["unsupported_layers"])


def test_elderly_same_verdicts_across_three_notices():
    """금천·가좌·오류의 고령자 조항과 결합표는 같다(각 p.13·p.7·p.11). 공고일에 맞춰 날짜를 옮긴 같은 체계적 입력
    (골든 S·T 구간)에 대한 판정 기록이 같아야 한다."""
    import json as _json
    import re as _re
    import golden_cases
    import golden_lib
    groups = golden_lib.load_outcomes()["groups"]

    def neutral(key):
        g = groups[key]
        n = g["n"] - golden_cases.RANDOM_PER_GROUP
        return [_re.sub(r"N\d+-", "X-", _json.dumps(r, ensure_ascii=False)) for r in g["records"][:n]]

    base = neutral("N6/고령자")
    assert neutral("N9/고령자") == base and neutral("N10/고령자") == base
