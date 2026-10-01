# -*- coding: utf-8 -*-
"""test_rule_data_n3.py — B단계 P2: N3(번동3) 대학생·청년 계층의 데이터 규칙이 기존 파이썬 규칙과
같은 결과를 내는지 차분 테스트한다(비교 항목과 입력 생성 방식은 test_rule_data.py와 동일).
신혼부부·한부모 계층은 P3에서 이전한다."""

import hashlib
import itertools
import random
from datetime import date, timedelta
from pathlib import Path

import pytest
from rule_engine import (
    CHILD_BONUS_CUTOFF, HouseholdProfile, evaluate, income_threshold, years_before,
)
from notices_data import N3 as LEGACY_N3, N3_ANNOUNCEMENT
from rule_data import load_notice
from test_rule_data import (
    AFTER, AFTER2, BEFORE_MINOR, ASSETS, CARS as STUDENT_CARS, INCOMES, LEGACY_COUNTS,
    SIZES, STATUSES, snapshot, _biased,
)

N3 = load_notice("N3")
PROJECT = Path(__file__).resolve().parent.parent

ADULT_LINE = years_before(N3_ANNOUNCEMENT, 19)
GRAD_CUT = years_before(N3_ANNOUNCEMENT, 2)
CHILD_LISTS = [
    None, [], [AFTER], [AFTER, BEFORE_MINOR], [BEFORE_MINOR], [AFTER, AFTER2, BEFORE_MINOR],
    [AFTER, ADULT_LINE], [AFTER, ADULT_LINE + timedelta(days=1)],
    [CHILD_BONUS_CUTOFF], [CHILD_BONUS_CUTOFF - timedelta(days=1)],
]
GRAD_DATES = [None, GRAD_CUT - timedelta(days=1), GRAD_CUT, GRAD_CUT + timedelta(days=1),
              date(2000, 1, 1), N3_ANNOUNCEMENT]
HEADS = [None, "세대주", "세대원", "기타"]
AGES = [18, 19, 30, 39, 40, 45]
ROOKIES = [None, True, False]
YOUTH_ASSETS = [None, 0] + [v + d for v in (251_000_000, 276_000_000, 301_000_000) for d in (-1, 0, 1)]
YOUTH_CARS = [0, 1, "확인불가"] + [v + d for v in (45_420_000, 49_960_000, 54_510_000) for d in (-1, 0, 1)]


def same(profile, layer):
    old = snapshot(evaluate(profile, LEGACY_N3, layer))
    new = snapshot(evaluate(profile, N3, layer))
    assert old == new, f"\n계층: {layer}\n입력: {profile}\n기존: {old}\n데이터: {new}"


def youth(age, marital, home, head, rookie, size, kids, count, income, assets, car):
    return HouseholdProfile(
        "D", age, marital, home, house_head_status=head, household_size=size,
        monthly_income=income, total_assets=assets, car_value=car, is_social_rookie=rookie,
        children_birth_dates=kids, young_child_count=count)


def student(marital, home, status, grad, size, kids, count, income, assets, car):
    return HouseholdProfile(
        "D", 22, marital, home, household_size=size, monthly_income=income, total_assets=assets,
        car_value=car, student_status=status, grad_or_dropout_date=grad,
        children_birth_dates=kids, young_child_count=count)


# --- 정적 동일성 ---------------------------------------------------------------------------
@pytest.mark.parametrize("layer", ["대학생", "청년"])
def test_n3_static_fields_identical_to_legacy(layer):
    new, old = N3.layers[layer].conditions, LEGACY_N3.layers[layer].conditions
    assert [(c.rule_id, c.field, c.required, c.source_ref, c.note) for c in new] == \
           [(c.rule_id, c.field, c.required, c.source_ref, c.note) for c in old]


def test_n3_meta_and_timing():
    assert (N3.announcement_date, N3.title) == (LEGACY_N3.announcement_date, LEGACY_N3.title)
    assert N3.meta["review"]["status"] == "DRAFT"
    pdf = next((PROJECT / "sample_lh").glob("*번동3*.pdf"))
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == N3.meta["source"]["sha256"]
    timings = {c.rule_id: c.timing for c in N3.layers["청년"].conditions}
    assert timings["N3-R10"] == "BEFORE_MOVE_IN"      # 청약통장은 "입주 전까지 이행" — 현재 충족 조건과 구분
    assert all(t == "NOW" for k, t in timings.items() if k != "N3-R10")


def test_p2_scope_only_student_and_youth_layers_are_in_the_data_file():
    assert set(N3.layers) == {"대학생", "청년"}


# --- 대학생 계층 ---------------------------------------------------------------------------
def test_differential_student_random_n3():
    rng = random.Random(20261002)
    for _ in range(30_000):
        same(student(
            _biased(rng, ["미혼", "혼인중"], ["미혼"]), _biased(rng, ["무주택", "주택보유"], ["무주택"]),
            _biased(rng, STATUSES, ["재학중", "입학예정", "복학예정"]), rng.choice(GRAD_DATES),
            rng.choice(SIZES), rng.choice(CHILD_LISTS), rng.choice(LEGACY_COUNTS),
            rng.choice(INCOMES), rng.choice(ASSETS), _biased(rng, STUDENT_CARS, [0], 0.85)), "대학생")


def test_differential_student_exhaustive_n3():
    for size, kids, count, assets in itertools.product(SIZES, CHILD_LISTS, LEGACY_COUNTS, ASSETS):
        same(student("미혼", "무주택", "재학중", None, size, kids, count, 1, assets, 0), "대학생")
    for size, kids, income in itertools.product(SIZES, CHILD_LISTS, INCOMES):
        same(student("미혼", "무주택", "재학중", None, size, kids, 0, income, 1, 0), "대학생")
    for status, grad in itertools.product(STATUSES, GRAD_DATES):
        same(student("미혼", "무주택", status, grad, 1, None, 0, 1, 1, 0), "대학생")


# --- 청년 계층 -----------------------------------------------------------------------------
def test_differential_youth_random_n3():
    rng = random.Random(20261003)
    for _ in range(60_000):
        same(youth(
            rng.choice(AGES), _biased(rng, ["미혼", "혼인중"], ["미혼"]),
            _biased(rng, ["무주택", "주택보유"], ["무주택"]),
            _biased(rng, HEADS, ["세대주", "세대원"]), rng.choice(ROOKIES), rng.choice(SIZES),
            rng.choice(CHILD_LISTS), rng.choice(LEGACY_COUNTS), rng.choice(INCOMES),
            rng.choice(YOUTH_ASSETS), rng.choice(YOUTH_CARS)), "청년")


def test_differential_youth_exhaustive_income_n3():
    # 세대주/세대원 × 가구원수 × 자녀 × 해석 후보 × 소득 경계 — 소득 결정표 전체를 전수 비교
    for head, size, kids, count, income in itertools.product(
            HEADS, SIZES, CHILD_LISTS, LEGACY_COUNTS, INCOMES):
        same(youth(30, "미혼", "무주택", head, None, size, kids, count, income, 1, 0), "청년")


def test_differential_youth_exhaustive_asset_and_car_n3():
    for size, kids, count, assets in itertools.product(SIZES, CHILD_LISTS, LEGACY_COUNTS, YOUTH_ASSETS):
        same(youth(30, "미혼", "무주택", "세대주", None, size, kids, count, 1, assets, 0), "청년")
    for size, kids, count, car in itertools.product(SIZES, CHILD_LISTS, LEGACY_COUNTS, YOUTH_CARS):
        same(youth(30, "미혼", "무주택", "세대주", None, size, kids, count, 1, 1, car), "청년")


def test_differential_youth_exhaustive_age_rookie_n3():
    for age, rookie, marital, home in itertools.product(
            range(15, 50), ROOKIES, ["미혼", "혼인중"], ["무주택", "주택보유"]):
        same(youth(age, marital, home, "세대주", rookie, 1, None, 0, 1, 1, 0), "청년")
