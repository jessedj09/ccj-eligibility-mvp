# -*- coding: utf-8 -*-
"""test_mvp0_6_household_consistency.py — 가구원수와 혼인·자녀 입력이 모순이면 확정하지 않는다.

가구원수는 최소 "부부(또는 한부모) + 자녀 수"이다. 예비신혼부부는 신청자 본인과 예비배우자, 공고일 기준
동일 세대에 등재된 직계존속·비속을 포함해 산정하므로(정부 지침; 공고문은 '혼인으로 구성될 세대'만 명시:
N1 p.5 ③④) 마찬가지로 2인 이상이다. 원문 표에 이런 칸이 없으므로 가까운 칸의 기준으로 확정하지 않고
MANUAL_REVIEW(INPUT_INCONSISTENT)로 보낸다.

손계산 기준(N1 p.5 자녀가산표, 신혼부부 자산): 자녀 0명 345,000,000 / 1명 379,000,000 / 2명 413,000,000.
"""

import copy
import json
from datetime import date

import pytest
from notices_data import N1, N3
from rule_data import RULES_DIR, RuleDataError, build_notice
from rule_engine import HouseholdProfile, evaluate

CHILD_1 = [date(2025, 1, 1)]
CHILD_2 = [date(2025, 1, 1), date(2024, 1, 1)]


def spouse(size, children, marital="혼인중", assets=100_000_000, dual=False, **kw):
    base = dict(profile_id="T", age=33, marital_status=marital, home_ownership="무주택",
                household_size=size, monthly_income=3_000_000, total_assets=assets, car_value=0,
                dual_income=dual, marriage_date=date(2025, 1, 1) if marital == "혼인중" else None,
                children_birth_dates=children)
    base.update(kw)
    return HouseholdProfile(**base)


def single_parent(size, children, assets=100_000_000):
    return HouseholdProfile(profile_id="T", age=35, marital_status="한부모", home_ownership="무주택",
                            household_size=size, monthly_income=2_000_000, total_assets=assets,
                            car_value=0, children_birth_dates=children)


def reasons(result):
    return {r.code for r in result.review_reasons.values()}


@pytest.mark.parametrize("notice", [N1, N3])
@pytest.mark.parametrize("marital", ["혼인중", "예비신혼"])
def test_married_or_prospective_household_of_one_is_inconsistent(notice, marital):
    r = evaluate(spouse(1, [], marital), notice, "신혼부부")
    assert r.verdict == "MANUAL_REVIEW" and reasons(r) == {"INPUT_INCONSISTENT"}
    # 더 이상 풀리지 않는 NEEDS_INFO 막다른 길이 아니다
    assert not r.unknown


@pytest.mark.parametrize("notice", [N1, N3])
def test_couple_only_without_bonus_child_is_normal(notice):
    assert evaluate(spouse(2, []), notice, "신혼부부").verdict == "ELIGIBLE"
    assert evaluate(spouse(2, [], "예비신혼"), notice, "신혼부부").verdict == "ELIGIBLE"


@pytest.mark.parametrize("notice", [N1, N3])
@pytest.mark.parametrize("size,children", [(2, CHILD_1), (3, CHILD_2)])
def test_married_household_smaller_than_couple_plus_children(notice, size, children):
    r = evaluate(spouse(size, children), notice, "신혼부부")
    assert r.verdict == "MANUAL_REVIEW" and reasons(r) == {"INPUT_INCONSISTENT"}


@pytest.mark.parametrize("notice", [N1, N3])
def test_consistent_sizes_keep_bonus_limits(notice):
    # 3인+자녀1명: 한도 379,000,000
    assert evaluate(spouse(3, CHILD_1, assets=379_000_000), notice, "신혼부부").verdict == "ELIGIBLE"
    assert evaluate(spouse(3, CHILD_1, assets=379_000_001), notice, "신혼부부").verdict == "INELIGIBLE"
    # 4인+자녀2명: 한도 413,000,000
    assert evaluate(spouse(4, CHILD_2, assets=413_000_000), notice, "신혼부부").verdict == "ELIGIBLE"
    assert evaluate(spouse(4, CHILD_2, assets=413_000_001), notice, "신혼부부").verdict == "INELIGIBLE"


def test_two_person_household_with_bonus_child_no_longer_gives_confident_ineligible():
    """수정 전: 가구원수 2로 적으면 자산 3.6억이 345,000,000 초과로 확정 불충족, 3으로 적으면 충족이었다."""
    assert evaluate(spouse(2, CHILD_1, assets=360_000_000), N1, "신혼부부").verdict == "MANUAL_REVIEW"
    assert evaluate(spouse(3, CHILD_1, assets=360_000_000), N1, "신혼부부").verdict == "ELIGIBLE"


def test_confirmed_failure_still_outranks_input_inconsistency():
    r = evaluate(spouse(2, CHILD_1, home_ownership="주택보유"), N1, "신혼부부")
    assert r.verdict == "INELIGIBLE"
    r = evaluate(spouse(1, [], marital="미혼"), N1, "신혼부부")   # 혼인 상태 불충족이 확정
    assert r.verdict == "INELIGIBLE"


@pytest.mark.parametrize("notice", [N1, N3])
def test_single_parent_two_children_needs_three_or_more(notice):
    assert evaluate(single_parent(2, CHILD_2), notice, "한부모").verdict == "MANUAL_REVIEW"
    assert evaluate(single_parent(1, CHILD_2), notice, "한부모").verdict == "MANUAL_REVIEW"
    assert evaluate(single_parent(3, CHILD_2, assets=413_000_000), notice, "한부모").verdict == "ELIGIBLE"
    assert evaluate(single_parent(3, CHILD_2, assets=413_000_001), notice, "한부모").verdict == "INELIGIBLE"


@pytest.mark.parametrize("notice", [N1, N3])
def test_single_parent_two_person_one_child_unchanged(notice):
    # 한부모+자녀 1명 = 2인, 가산 한도 379,000,000
    assert evaluate(single_parent(2, CHILD_1, assets=379_000_000), notice, "한부모").verdict == "ELIGIBLE"
    assert evaluate(single_parent(2, CHILD_1, assets=379_000_001), notice, "한부모").verdict == "INELIGIBLE"


def test_review_item_is_explained_with_input_check_message():
    from explainability import explain
    exp = explain(evaluate(spouse(2, CHILD_1), N1, "신혼부부"), N1)
    assert exp.review and all(i.code == "INPUT_INCONSISTENT" for i in exp.review)
    assert "가구원수" in exp.review[0].detail


# --- 로더: 행 단위 no_row 사유 ---------------------------------------------------------
def n1_doc():
    return json.loads((RULES_DIR / "notices" / "N1.json").read_text(encoding="utf-8"))


def test_loader_accepts_known_code_and_rejects_bad_row_no_row():
    build_notice(n1_doc())
    bad_code = copy.deepcopy(n1_doc())
    bad_code["tables"]["spouse_terms_married"]["rows"][0]["no_row"]["code"] = "NOPE"
    with pytest.raises(RuleDataError):
        build_notice(bad_code)
    on_normal_row = copy.deepcopy(n1_doc())
    on_normal_row["tables"]["spouse_terms_married"]["rows"][1]["no_row"] = {
        "code": "INPUT_INCONSISTENT", "detail": "x"}
    with pytest.raises(RuleDataError):
        build_notice(on_normal_row)
    missing_detail = copy.deepcopy(n1_doc())
    del missing_detail["tables"]["spouse_terms_married"]["rows"][0]["no_row"]["detail"]
    with pytest.raises(RuleDataError):
        build_notice(missing_detail)
