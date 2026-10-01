# -*- coding: utf-8 -*-
"""test_rule_data.py — 규칙 데이터 로더·조건식 평가기 검증.

1) 평가기 단위 테스트: any/all 우선순위, None/표에 없음/해석 불일치 전파, 연산자 의미.
2) 로더 검증: 잘못된 데이터가 로드 시점에 거부되는지(런타임 오판정 방지).
3) 기준값 표: JSON 원본의 값이 PDF 원문 수치와 같다.
기존 파이썬 규칙과의 차분 테스트는 B단계 P1~P3에서 동등성을 증명한 뒤 골든 스냅샷
(test_rules_golden.py)으로 대체되었다.
"""

import copy
import json
from datetime import date

import pytest
from rule_engine import HouseholdProfile, evaluate, income_threshold
from rule_data import RuleDataError, build_notice, load_reference, RULES_DIR


# 소득기준표(전년도 도시근로자 가구원수별 가구당 월평균소득) 원문 수치 — N1 p.6 / N2 p.5 / N3 p.8 표를
# 손으로 옮긴 값. JSON 원본이 이 값과 같아야 한다.
INCOME_FROM_PDF = {
    (1, 120): 4_576_036,
    (2, 110): 6_452_897, (2, 120): 7_039_524, (2, 130): 7_626_151, (2, 140): 8_212_778,
    (3, 100): 8_168_429, (3, 110): 8_985_272, (3, 120): 9_802_115, (3, 130): 10_618_958, (3, 140): 11_435_801,
    (4, 100): 8_802_202, (4, 110): 9_682_422, (4, 120): 10_562_642, (4, 130): 11_442_863, (4, 140): 12_323_083,
    (5, 100): 9_326_985, (5, 110): 10_259_684, (5, 120): 11_192_382, (5, 130): 12_125_081, (5, 140): 13_057_779,
    (6, 100): 9_906_263, (6, 110): 10_896_889, (6, 120): 11_887_516, (6, 130): 12_878_142, (6, 140): 13_868_768,
}


def test_income_reference_matches_pdf_table():
    for (size, ratio), expected in INCOME_FROM_PDF.items():
        assert load_reference("income_standard").lookup(size, ratio) == expected, (size, ratio)
        assert income_threshold(size, ratio) == expected


def test_income_reference_missing_combinations_and_7plus_adder():
    assert income_threshold(1, 100) is None and income_threshold(1, 110) is None   # 표에 없는 조합
    assert income_threshold(7, 120) == 11_887_516 + 579_278        # 7인 이상: 6인 + 1인당 579,278원
    assert income_threshold(9, 100) == 9_906_263 + 579_278 * 3


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
