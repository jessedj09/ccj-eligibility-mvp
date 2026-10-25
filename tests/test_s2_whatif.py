# -*- coding: utf-8 -*-
"""test_s2_whatif.py — What-if(src/whatif.py): 조건 하나만 부족한 공고의 금액 한도와 시나리오 비교.

한도는 엔진으로 직접 찾은 값이어야 한다 — 한도 금액이면 그 조건이 충족, 1원 많으면 불충족(경계 정확성).
"""
import dataclasses
from datetime import date

import pytest
import whatif as w
from matcher import MasterProfile, match_all, scoped_profile
from notices_data import ALL_NOTICES
from rule_engine import evaluate

YOUTH = MasterProfile(
    home_self="무주택", home_household="주택보유", income_self=3_200_000, income_household=9_000_000,
    assets_self=20_000_000, assets_household=600_000_000, car_self=0, car_household=20_000_000, birth_date=date(1998, 3, 1),
    common=dict(marital_status="미혼", household_size=3, house_head_status="세대원", dual_income=False, children_birth_dates=[],
                residence_area="서울특별시", is_employed=True, is_social_rookie=True, parents_count=2,
                parents_monthly_income=5_800_000, registered_with_parents=True))
NEWLYWED = MasterProfile(
    home_self="무주택", home_household="무주택", income_self=4_000_000, income_household=9_500_000,
    assets_self=150_000_000, assets_household=413_000_001, car_self=0, car_household=30_000_000, birth_date=date(1993, 5, 1),
    common=dict(marital_status="혼인중", marriage_date=date(2022, 1, 1), household_size=4, house_head_status="세대주",
                dual_income=False, children_birth_dates=[date(2024, 1, 1), date(2025, 6, 1)], residence_area="서울특별시",
                income_base_area="서울특별시", spouse_residence_area="서울특별시", spouse_income_base_area="서울특별시"))


@pytest.mark.parametrize("m", [YOUTH, NEWLYWED], ids=["youth", "newlywed"])
def test_every_threshold_is_exact_to_the_won(m):
    near = w.near_misses(m, match_all(m, ALL_NOTICES))
    checked = 0
    for n in near:
        x = n.match
        assert x.verdict == "INELIGIBLE" and x.result.failed == [n.condition_id]
        for t in n.thresholds:
            p = scoped_profile(m, x.notice, x.layer)
            at = evaluate(dataclasses.replace(p, **{t.field: t.limit}), x.notice, x.layer)
            over = evaluate(dataclasses.replace(p, **{t.field: t.limit + 1}), x.notice, x.layer)
            assert n.condition_id in at.matched and n.condition_id not in over.matched, (x.notice.notice_id, x.layer, t)
            edge = t.review_limit if t.review_limit is not None else t.limit   # 이 값까지는 불충족이 아니다
            assert n.condition_id not in evaluate(dataclasses.replace(p, **{t.field: edge}), x.notice, x.layer).failed
            assert n.condition_id in evaluate(dataclasses.replace(p, **{t.field: edge + 1}), x.notice, x.layer).failed
            assert 0 <= t.limit < t.current and (t.review_limit is None or t.limit < t.review_limit < t.current)
            checked += 1
    assert checked >= 3


def test_known_limit_n1_newlywed_assets():
    """N1 신혼부부 4인·출생자녀 가산 2명의 총자산 한도는 원문 413,000,000원(tools/ui_smoke 4단계와 같은 경계)."""
    near = {(n.match.notice.notice_id, n.match.layer): n for n in w.near_misses(NEWLYWED, match_all(NEWLYWED, ALL_NOTICES))}
    n = near[("N1", "신혼부부")]
    assert n.after == "지원 가능"
    t = next(t for t in n.thresholds if t.field == "total_assets")
    assert (t.current, t.limit, t.gap, t.scope) == (413_000_001, 413_000_000, 1, "세대 합계")


def test_ambiguous_condition_has_a_manual_review_band():
    """N5 지역전략산업종사자 총자산: 원문이 출생자녀 가산 적용 여부를 정하지 않아 345,000,000원 초과 ~ 413,000,000원은 수동 확인."""
    near = {(n.match.notice.notice_id, n.match.layer): n for n in w.near_misses(NEWLYWED, match_all(NEWLYWED, ALL_NOTICES))}
    t = next(t for t in near[("N5", "지역전략산업종사자")].thresholds if t.field == "total_assets")
    assert (t.limit, t.review_limit) == (345_000_000, 413_000_000)


def test_near_misses_sorted_with_thresholds_first():
    near = w.near_misses(YOUTH, match_all(YOUTH, ALL_NOTICES))
    flags = [bool(n.thresholds) for n in near]
    assert flags == sorted(flags, reverse=True)


def test_marry_builds_a_new_household():
    after = w.marry(YOUTH, date(2026, 10, 25), 3_000_000, 30_000_000, 10_000_000, False, True)
    c = after.common
    assert (c["marital_status"], c["marriage_date"], c["household_size"], c["house_head_status"]) == \
        ("혼인중", date(2026, 10, 25), 2, "세대주")
    assert (after.income_household, after.assets_household, after.car_household, after.home_household) == \
        (6_200_000, 50_000_000, 10_000_000, "무주택")
    assert c["spouse_residence_area"] == "서울특별시" and c["dual_income"] is True
    pre = w.marry(YOUTH, None, None, None, None, True, False, prenuptial=True)
    assert pre.common["marital_status"] == "예비신혼" and pre.common["marriage_date"] is None
    assert pre.income_household is None and pre.home_household == "주택보유"


def test_separate_and_move():
    s = w.separate_household(YOUTH)
    assert (s.home_household, s.income_household, s.assets_household, s.car_household) == ("무주택", 3_200_000, 20_000_000, 0)
    assert s.common["household_size"] == 1 and s.common["house_head_status"] == "세대주"
    assert w.move(YOUTH, "수원시").common["residence_area"] == "수원시"
    assert YOUTH.common["residence_area"] == "서울특별시"          # 원래 프로필은 바뀌지 않는다


@pytest.mark.parametrize("name,change", [
    ("세대 분리", w.separate_household),
    ("혼인", lambda m: w.marry(m, date(2026, 10, 25), 3_000_000, 30_000_000, 0, False, True)),
    ("이전", lambda m: w.move(m, "수원시")),
])
def test_scenario_result_matches_direct_judgment(name, change):
    r = w.run_scenario(name, YOUTH, change, ALL_NOTICES)
    before, after = match_all(YOUTH, ALL_NOTICES), match_all(change(YOUTH), ALL_NOTICES)
    ok = lambda ms: {(x.notice.notice_id, x.layer) for x in ms if x.verdict == "ELIGIBLE"}  # noqa: E731
    assert {(x.notice.notice_id, x.layer) for x in r.gained} == ok(after) - ok(before)
    assert {(x.notice.notice_id, x.layer) for x in r.lost} == ok(before) - ok(after)
    assert r.after["ELIGIBLE"] == len(ok(after)) and sum(r.after.values()) == len(after)


def test_marriage_gains_newlywed_layers_and_loses_unmarried_youth_layers():
    r = w.run_scenario("혼인", YOUTH, lambda m: w.marry(m, date(2026, 10, 25), 3_000_000, 30_000_000, 0, False, True),
                       ALL_NOTICES)
    assert any(x.layer.startswith(("신혼부부", "신혼·신생아")) for x in r.gained)
    assert r.lost and all(x.layer == "청년" for x in r.lost)


def test_keep_filter_limits_comparison():
    r = w.run_scenario("세대 분리", YOUTH, w.separate_household, ALL_NOTICES, keep=lambda x: x.notice.notice_id == "N17")
    assert sum(r.before.values()) == len(ALL_NOTICES["N17"].layers)
    assert [x.notice.notice_id for x in r.gained] == ["N17"]
