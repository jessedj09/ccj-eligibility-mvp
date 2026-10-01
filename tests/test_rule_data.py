# -*- coding: utf-8 -*-
"""test_rule_data.py — 규칙 데이터화(B단계 P1) 검증.

1) 차분 테스트: 기존 파이썬 규칙(notices_data.N2)과 JSON 규칙(rules/notices/N2.json)이 같은 입력에
   verdict·score·matched·failed·unknown·review(사유 코드·상세 문구 포함)까지 전부 같은 결과를 내는지.
   입력은 모든 수치 한도·컷오프 날짜의 경계(-1/0/+1)와 enum·None 조합에서 만든다(데이터의 한도에서
   자동 파생 + 시드 고정 무작위 표본).
2) 평가기 단위 테스트: any/all 우선순위, None/표에 없음/해석 불일치 전파.
3) 로더 검증: 잘못된 데이터가 로드 시점에 거부되는지(런타임 오판정 방지).
"""

import copy
import hashlib
import itertools
import json
import random
from datetime import date, timedelta
from pathlib import Path

import pytest
from rule_engine import (
    CHILD_BONUS_CUTOFF, HouseholdProfile, evaluate, income_threshold, years_before,
)
from notices_data import N2 as LEGACY_N2, N2_ANNOUNCEMENT
from rule_data import (
    RuleDataError, build_notice, load_notice, load_reference, RULES_DIR,
)

N2 = load_notice("N2")
PROJECT = Path(__file__).resolve().parent.parent


def snapshot(r):
    return (r.verdict, r.score, tuple(r.matched), tuple(r.failed), tuple(r.unknown),
            tuple(r.review), tuple(r.notes),
            {k: (v.code, v.detail) for k, v in r.review_reasons.items()})


# ---------------------------------------------------------------------------
# 정적 동일성 — 설명 계층이 쓰는 모든 필드가 기존과 글자까지 같다
# ---------------------------------------------------------------------------
def test_n2_static_fields_identical_to_legacy():
    assert (N2.notice_id, N2.title, N2.announcement_date) == \
           (LEGACY_N2.notice_id, LEGACY_N2.title, LEGACY_N2.announcement_date)
    new, old = N2.layers["대학생"].conditions, LEGACY_N2.layers["대학생"].conditions
    assert [(c.rule_id, c.field, c.required, c.source_ref, c.note) for c in new] == \
           [(c.rule_id, c.field, c.required, c.source_ref, c.note) for c in old]


def test_reference_lookup_identical_to_income_threshold():
    ref = load_reference("income_standard")
    for size, ratio in itertools.product(range(1, 13), (100, 110, 120, 130, 140, 150)):
        assert ref.lookup(size, ratio) == income_threshold(size, ratio), (size, ratio)


def test_n2_meta_status_and_source_hash():
    assert N2.meta["review"]["status"] == "DRAFT"
    assert N2.meta["version"] == 1
    pdf = next((PROJECT / "sample_lh").glob("*관악봉천*.pdf"))
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == N2.meta["source"]["sha256"]


# ---------------------------------------------------------------------------
# 차분 테스트
# ---------------------------------------------------------------------------
AFTER, AFTER2, BEFORE_MINOR = date(2024, 1, 1), date(2025, 6, 1), date(2015, 5, 5)
ADULT_LINE = years_before(N2_ANNOUNCEMENT, 19)
GRAD_CUT = years_before(N2_ANNOUNCEMENT, 2)
SIZES = [1, 2, 3, 4, 6, 7, 8]
CHILD_LISTS = [
    None, [], [AFTER], [AFTER, BEFORE_MINOR], [BEFORE_MINOR], [AFTER, AFTER2, BEFORE_MINOR],
    [AFTER, ADULT_LINE], [AFTER, ADULT_LINE + timedelta(days=1)],
    [CHILD_BONUS_CUTOFF], [CHILD_BONUS_CUTOFF - timedelta(days=1)],
]
LEGACY_COUNTS = [0, 1, 2, 3]
GRAD_DATES = [None, GRAD_CUT - timedelta(days=1), GRAD_CUT, GRAD_CUT + timedelta(days=1),
              date(2000, 1, 1), N2_ANNOUNCEMENT]
STATUSES = [None, "재학중", "입학예정", "복학예정", "취업준비생", "해당없음"]

INCOMES = [None, 0, 1]
for _size in SIZES:
    for _ratio in (100, 110, 120, 130, 140):
        _limit = income_threshold(_size, _ratio)
        if _limit is not None:
            INCOMES += [_limit - 1, _limit, _limit + 1]
ASSETS = [None, 0] + [v + d for v in (108_000_000, 119_000_000, 130_000_000) for d in (-1, 0, 1)]
CARS = [0, 1, "확인불가"]


def make_profile(marital, home, status, grad, size, kids, legacy_count, income, assets, car):
    return HouseholdProfile(
        "D", 22, marital, home, household_size=size, monthly_income=income,
        total_assets=assets, car_value=car, student_status=status, grad_or_dropout_date=grad,
        children_birth_dates=kids, young_child_count=legacy_count)


def assert_same(profile):
    old = snapshot(evaluate(profile, LEGACY_N2, "대학생"))
    new = snapshot(evaluate(profile, N2, "대학생"))
    assert old == new, f"\n입력: {profile}\n기존: {old}\n데이터: {new}"


def _biased(rng, pool, pass_values, p_pass=0.75):
    """통과하는 값에 가중치를 둔 표본 — 무작위로만 뽑으면 다른 조건에서 먼저 탈락해
    '모든 조건이 통과 근처'인 영역(경계 판정이 실제로 결과를 가르는 영역)이 거의 검증되지 않는다."""
    return rng.choice(pass_values) if rng.random() < p_pass else rng.choice(pool)


def test_differential_random_sample_n2():
    rng = random.Random(20261001)
    for _ in range(40_000):
        assert_same(make_profile(
            _biased(rng, ["미혼", "혼인중"], ["미혼"]),
            _biased(rng, ["무주택", "주택보유"], ["무주택"]),
            _biased(rng, STATUSES, ["재학중", "입학예정", "복학예정"]),
            rng.choice(GRAD_DATES), rng.choice(SIZES),
            rng.choice(CHILD_LISTS), rng.choice(LEGACY_COUNTS),
            rng.choice(INCOMES), rng.choice(ASSETS),
            _biased(rng, CARS, [0], 0.85)))


def test_differential_exhaustive_household_x_children_x_assets_n2():
    # 결정표(가구원수×자녀수×해석)와 자산 경계는 전수 조합으로 비교한다
    for size, kids, count, assets in itertools.product(SIZES, CHILD_LISTS, LEGACY_COUNTS, ASSETS):
        assert_same(make_profile("미혼", "무주택", "재학중", None, size, kids, count, 1, assets, 0))


def test_differential_exhaustive_status_x_grad_date_n2():
    for status, grad in itertools.product(STATUSES, GRAD_DATES):
        assert_same(make_profile("미혼", "무주택", status, grad, 1, None, 0, 1, 1, 0))


def test_differential_exhaustive_income_boundaries_n2():
    for size, kids, income in itertools.product(SIZES, CHILD_LISTS, INCOMES):
        assert_same(make_profile("미혼", "무주택", "재학중", None, size, kids, 0, income, 1, 0))


# ---------------------------------------------------------------------------
# 평가기 단위 테스트 — 합성 공고 파일로 연산자 의미를 직접 검증
# ---------------------------------------------------------------------------
def synthetic(check, **extra):
    cond = {"id": "T-1", "field": "x", "required": True,
            "source": {"page": 1}, "note": "테스트", "check": check}
    cond.update(extra)
    return {
        "notice_id": "T", "title": "합성 공고", "announcement_date": "2026-01-01",
        "review": {"status": "DRAFT"}, "layers": {"청년": {"conditions": [cond]}},
    }


def run(check, **profile_kwargs):
    base = dict(profile_id="T", age=30, marital_status="미혼", home_ownership="무주택")
    base.update(profile_kwargs)
    return evaluate(HouseholdProfile(**base), build_notice(synthetic(check)), "청년")


ROOKIE_OR_AGE = {"any": [
    {"between": [{"var": "age"}, 19, 39]},
    {"eq": [{"var": "is_social_rookie"}, True],
     "review_if_true": {"code": "SELF_REPORT_UNVERIFIED", "detail": "자기신고"}},
]}


@pytest.mark.parametrize("age,rookie,verdict", [
    (30, None, "ELIGIBLE"),          # 나이가 범위 안이면 사회초년생 정보와 무관하게 확정
    (45, True, "MANUAL_REVIEW"),     # 자기신고 경로는 확정하지 않는다
    (45, False, "INELIGIBLE"),
    (45, None, "NEEDS_INFO"),
])
def test_any_precedence_true_over_review_over_unknown_over_false(age, rookie, verdict):
    assert run(ROOKIE_OR_AGE, age=age, is_social_rookie=rookie).verdict == verdict


def test_all_precedence_false_over_review_and_unknown():
    check = {"all": [
        {"eq": [{"var": "home_ownership"}, "주택보유"]},                       # False
        {"eq": [{"var": "is_social_rookie"}, True],
         "review_if_true": {"code": "AMBIGUOUS_SOURCE", "detail": "x"}},     # Review
        {"eq": [{"var": "monthly_income"}, 1]},                              # None
    ]}
    r = run(check, is_social_rookie=True, monthly_income=None)
    assert r.verdict == "INELIGIBLE"


def test_unknown_values_marker_becomes_none():
    check = {"eq": [{"var": "car_value", "unknown_values": ["확인불가"]}, 0]}
    assert run(check, car_value="확인불가").verdict == "NEEDS_INFO"
    assert run(check, car_value=0).verdict == "ELIGIBLE"
    assert run(check, car_value=1).verdict == "INELIGIBLE"


def test_lookup_missing_entry_is_unknown_not_crash():
    # 1인 가구에는 100% 기준액이 없다(표에 없음) → 정보 부족
    check = {"lte": [1, {"lookup": ["income_standard", 1, 100]}]}
    assert run(check).verdict == "NEEDS_INFO"


def test_date_comparison_with_years_before():
    check = {"gte": [{"var": "marriage_date"},
                     {"fn": "years_before", "args": [{"ctx": "announcement_date"}, 7]}]}
    assert run(check, marriage_date=date(2019, 1, 1)).verdict == "ELIGIBLE"    # 컷오프 당일
    assert run(check, marriage_date=date(2018, 12, 31)).verdict == "INELIGIBLE"
    assert run(check, marriage_date=None).verdict == "NEEDS_INFO"


# ---------------------------------------------------------------------------
# 로더 검증 — 잘못된 데이터는 로드 시점에 거부된다
# ---------------------------------------------------------------------------
def load_n2_doc():
    return json.loads((RULES_DIR / "notices" / "N2.json").read_text(encoding="utf-8"))


def mutated(fn):
    doc = copy.deepcopy(load_n2_doc())
    fn(doc)
    return doc


BAD_DOCS = {
    "알 수 없는 연산자": lambda d: d["layers"]["대학생"]["conditions"][0].update(
        check={"regex": ["a", "b"]}),
    "프로필에 없는 변수": lambda d: d["layers"]["대학생"]["conditions"][0].update(
        check={"eq": [{"var": "marital_stauts"}, "미혼"]}),
    "허용 목록 밖 함수": lambda d: d["layers"]["대학생"]["conditions"][0].update(
        check={"eq": [{"fn": "eval", "args": []}, 1]}),
    "함수 인자 개수": lambda d: d["layers"]["대학생"]["conditions"][0].update(
        check={"eq": [{"fn": "years_before", "args": [1]}, 1]}),
    "정의되지 않은 결정표": lambda d: d["layers"]["대학생"]["conditions"][3].update(table="nope"),
    "표 밖에서 term 사용": lambda d: d["layers"]["대학생"]["conditions"][0].update(
        check={"eq": [{"term": "ratio"}, 1]}),
    "표에 없는 출력 term": lambda d: d["layers"]["대학생"]["conditions"][3].update(
        check={"lte": [1, {"term": "no_such_output"}]}),
    "정의되지 않은 기준값 표": lambda d: d["layers"]["대학생"]["conditions"][3].update(
        check={"lte": [1, {"lookup": ["no_ref", 1, 100]}]}),
    "알 수 없는 컨텍스트": lambda d: d["layers"]["대학생"]["conditions"][0].update(
        check={"eq": [{"ctx": "today"}, 1]}),
    "조건 ID 중복": lambda d: d["layers"]["대학생"]["conditions"][1].update(id="N2-R4"),
    "잘못된 검수 상태": lambda d: d["review"].update(status="APPROVED"),
    "source.page 누락": lambda d: d["layers"]["대학생"]["conditions"][0].update(source={}),
    "필수 키 누락": lambda d: d["layers"]["대학생"]["conditions"][0].pop("note"),
    "알 수 없는 계층": lambda d: d["layers"].update({"노인": d["layers"]["대학생"]}),
    "결정표 행 표기 오류": lambda d: d["tables"]["student_terms"]["rows"][0]["when"].update(size="x+"),
    "결정표 out 길이": lambda d: d["tables"]["student_terms"]["rows"][0].update(out=[1]),
    "선언 안 된 reading": lambda d: d["tables"]["student_terms"]["rows"][0].update(readings=["??"]),
    "날짜 형식": lambda d: d.update(announcement_date="2026/07/15"),
    "연산자 둘": lambda d: d["layers"]["대학생"]["conditions"][0].update(
        check={"eq": [1, 1], "ne": [1, 2]}),
}


@pytest.mark.parametrize("name", list(BAD_DOCS))
def test_loader_rejects_bad_data(name):
    with pytest.raises((RuleDataError, ValueError)):
        build_notice(mutated(BAD_DOCS[name]))


def test_non_boolean_check_result_is_rejected_at_evaluation():
    doc = synthetic({"var": "age"})
    notice = build_notice(doc)
    with pytest.raises(RuleDataError):
        evaluate(HouseholdProfile("T", 30, "미혼", "무주택"), notice, "청년")
