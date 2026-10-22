# -*- coding: utf-8 -*-
"""test_matcher.py — D 단계: 한 번 받은 입력으로 전 공고·계층을 판정(src/matcher.py, rules/reference/input_scope.json).

1) 입력 범위 규칙이 모든 공고·계층에 있고, 원문 취지대로 고른다(대학생·청년 = 본인 무주택, 산단·지역전략 = 혼인 시 세대 등).
2) 범위가 같아지는 입력(본인 = 세대)이면 전체 판정 결과가 공고별 직접 판정과 같다(골든 입력으로 비교).
3) 범위가 갈리는 입력이면 계층마다 맞는 값을 쓴다(손으로 만든 사례).
"""

import dataclasses
from datetime import date
from functools import lru_cache

import golden_cases as gc
import pytest
from matcher import MasterProfile, evaluate_layer, match_all, missing_inputs, scope_for, scoped_profile
from notices_data import ALL_NOTICES
from rule_engine import evaluate


def test_every_notice_layer_has_a_scope_rule():
    for n in ALL_NOTICES.values():
        for layer in n.layers:
            assert scope_for(n, layer)


@pytest.mark.parametrize("nid,layer,home,income", [
    ("N2", "대학생", "self", "self_plus_parents"), ("N3", "청년", "self", "youth_head"),
    ("N6", "산업단지근로자", "self_if_unmarried", "household"), ("N5", "지역전략산업종사자", "self_if_unmarried", "household"),
    ("N11", "청년", "self", "self"), ("N11", "취업준비생", "self", "self"), ("N1", "신혼부부", "household", "household"),
    ("N4", "신혼부부(주거약자용)", "household", "household"), ("N16", "일반", "household", "household"),
    ("N26", "일반(전용 60㎡ 이하)", "household", "household"),
])
def test_scope_rules_follow_the_notices(nid, layer, home, income):
    rule = scope_for(ALL_NOTICES[nid], layer)
    assert (rule["home"], rule["income"]) == (home, income)


def _master_from(p) -> MasterProfile:
    """범위가 같아지는 MasterProfile(본인 = 세대 = 원래 값)."""
    common = {f.name: getattr(p, f.name) for f in dataclasses.fields(p)
              if f.name not in ("home_ownership", "monthly_income", "total_assets", "car_value")}
    car = None if p.car_value == "확인불가" else p.car_value
    return MasterProfile(home_self=p.home_ownership, home_household=p.home_ownership,
                         income_self=p.monthly_income, income_household=p.monthly_income,
                         assets_self=p.total_assets, assets_household=p.total_assets,
                         car_self=car, car_household=car, common=common)


@lru_cache(maxsize=None)
def _first_cases(limit=400):
    """골든 입력을 한 번만 생성해 그룹별 앞 limit건을 모은다(조합마다 처음부터 다시 생성하지 않도록)."""
    out = {}
    for nid, layer, p in gc.cases():
        bucket = out.setdefault((nid, layer), [])
        if len(bucket) < limit:
            bucket.append(p)
    return out


@pytest.mark.parametrize("nid,layer", [g for g in gc.GROUPS
                                       if scope_for(ALL_NOTICES[g[0]], g[1])["income"] != "self_plus_parents"
                                       and not g[1].startswith("주거약자")])
def test_same_scope_input_gives_the_direct_verdict(nid, layer):
    """본인 = 세대로 입력하면 계층별 범위 변환이 값을 바꾸지 않으므로 공고별 직접 판정과 같아야 한다(골든 입력 앞 400건)."""
    notice = ALL_NOTICES[nid]
    n = 0
    for p in _first_cases()[(nid, layer)]:
        if p.household_size == 1 or p.house_head_status not in ("세대주", "세대원"):
            p = dataclasses.replace(p, house_head_status="세대주") if scope_for(notice, layer)["income"] == "youth_head" else p
        direct = evaluate(p, notice, layer)
        via = evaluate_layer(_master_from(p), notice, layer)
        assert (via.verdict, via.failed, via.unknown) == (direct.verdict, direct.failed, direct.unknown), p
        n += 1
    assert n == 400


YOUTH_AT_HOME = MasterProfile(
    home_self="무주택", home_household="주택보유", income_self=3_000_000, income_household=9_000_000,
    assets_self=20_000_000, assets_household=600_000_000, car_self=0, car_household=20_000_000,
    common=dict(age=25, marital_status="미혼", household_size=3, house_head_status="세대원", children_birth_dates=[],
                residence_area="서울특별시", income_base_area="서울특별시", student_status="해당없음",
                dual_income=False, is_employed=True))


def test_youth_living_with_home_owning_parents():
    """본인 무주택·저소득, 세대(부모) 주택 보유·고소득인 25세 세대원."""
    by = {(x.notice.notice_id, x.layer): x for x in match_all(YOUTH_AT_HOME, ALL_NOTICES)}
    assert by[("N3", "청년")].verdict == "ELIGIBLE"          # 행복주택 청년: 본인 무주택, 세대원이므로 본인 소득·자산
    assert by[("N11", "청년")].verdict == "ELIGIBLE" and by[("N11", "청년")].result.eligible_tracks == ["3순위"]
    assert by[("N16", "일반")].verdict == "INELIGIBLE"       # 든든전세: 세대 전원 무주택이어야 함
    assert by[("N16", "일반")].result.failed == ["N16-home"]


def test_youth_head_of_household_uses_household_income():
    head = dataclasses.replace(YOUTH_AT_HOME, common={**YOUTH_AT_HOME.common, "house_head_status": "세대주"})
    r = evaluate_layer(head, ALL_NOTICES["N3"], "청년")
    assert r.verdict == "INELIGIBLE" and "N3-R7/R7b" in r.failed     # 세대 소득 900만 > 3인 기준


def test_student_income_is_self_plus_parents_and_size_includes_parents():
    student = MasterProfile(
        home_self="무주택", home_household="주택보유", income_self=0, income_household=None,
        assets_self=10_000_000, car_self=0,
        common=dict(age=21, marital_status="미혼", student_status="재학중", children_birth_dates=[],
                    parents_count=2, parents_monthly_income=8_168_429))
    p = scoped_profile(student, ALL_NOTICES["N2"], "대학생")
    assert (p.household_size, p.monthly_income, p.home_ownership) == (3, 8_168_429, "무주택")
    assert evaluate_layer(student, ALL_NOTICES["N2"], "대학생").verdict == "ELIGIBLE"      # 3인 100% = 8,168,429
    over = dataclasses.replace(student, common={**student.common, "parents_monthly_income": 8_168_430})
    assert evaluate_layer(over, ALL_NOTICES["N2"], "대학생").verdict == "INELIGIBLE"


def test_industrial_worker_home_scope_depends_on_marriage():
    base = dict(age=30, household_size=3, children_birth_dates=[], industrial_workplace="산업단지 입주기업",
                workplace_area="서울특별시", industrial_affiliation="소속")
    m = MasterProfile(home_self="무주택", home_household="주택보유", income_household=1, assets_household=1,
                      car_household=0, common={**base, "marital_status": "미혼"})
    assert evaluate_layer(m, ALL_NOTICES["N6"], "산업단지근로자").verdict == "ELIGIBLE"       # 미혼 → 본인 무주택
    married = dataclasses.replace(m, common={**base, "marital_status": "혼인중"})
    assert evaluate_layer(married, ALL_NOTICES["N6"], "산업단지근로자").verdict == "INELIGIBLE"  # 혼인 → 세대 전원


def test_home_answer_implications():
    m = MasterProfile(home_household="무주택", common=dict(age=30, marital_status="미혼", household_size=1))
    assert scoped_profile(m, ALL_NOTICES["N3"], "청년").home_ownership == "무주택"      # 세대 전원 무주택 → 본인도
    m = MasterProfile(home_self="주택보유", common=dict(age=30, marital_status="혼인중", household_size=2))
    assert scoped_profile(m, ALL_NOTICES["N1"], "신혼부부").home_ownership == "주택보유"  # 본인 보유 → 세대도


def test_bucheon_vulnerable_layer_uses_each_tracks_own_scope():
    m = dataclasses.replace(YOUTH_AT_HOME, common={**YOUTH_AT_HOME.common, "residence_area": "부천시",
                                                    "housing_weak_type": "장애인"})
    r = evaluate_layer(m, ALL_NOTICES["N5"], "주거약자(26A1/B1형)")
    assert r.verdict == "ELIGIBLE" and r.eligible_tracks == ["청년"]   # 청년 트랙은 본인 기준(세대원)으로 충족


def test_missing_inputs_points_to_what_unlocks_more_notices():
    blank = MasterProfile(common=dict(age=30, marital_status="미혼"))
    counts = missing_inputs(match_all(blank, ALL_NOTICES))
    assert counts and max(counts.values()) == next(iter(counts.values()))       # 많이 막는 항목부터
    assert "주택 소유" in counts


def test_birth_date_gives_age_on_each_announcement_date():
    """2007-08-18생: N5 부천(공고 2026-08-18)에서는 만 19세, N3 번동3(2026-08-19)에서도 19세, N10(2026-05-15)에서는 18세."""
    m = MasterProfile(birth_date=date(2007, 8, 18), common=dict(marital_status="미혼"))
    assert scoped_profile(m, ALL_NOTICES["N5"], "청년").age == 19
    assert scoped_profile(m, ALL_NOTICES["N10"], "청년").age == 18
