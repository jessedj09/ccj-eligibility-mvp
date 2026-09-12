# -*- coding: utf-8 -*-
"""
notices_data.py
===============
rules 시트의 3개 공고(N1 공릉/N2 관악봉천/N3 번동3)를 실제 판정 가능한 코드로 옮긴 것.
각 조건의 check 함수는 profile을 받아 True(충족)/False(불충족)/None(확인불가)을 반환한다.

이번 갱신: 자녀수 가산(소득비율·자산·자동차가 동시에 바뀌는 결합표), 예비신혼부부/한부모
구분(marital_status 체크)을 추가로 반영했다. 우선공급 배점(N1-P2/P3)은 verdict에
영향을 주지 않으므로 별도 파일(priority_scoring.py)로 분리했다.
"""

from rule_engine import RuleCondition, LayerRuleSet, NoticeRuleSet, income_threshold


def _car_ok(profile, limit):
    """car_value가 '확인불가'면 None, 숫자면 한도 비교."""
    if profile.car_value == "확인불가":
        return None
    return profile.car_value <= limit


def _income_ok_simple(profile, ratio_100, ratio_dual=None):
    """household_size·monthly_income 기준 일반/맞벌이 비율 분기 (자녀가산 없는 계층용)."""
    ratio = ratio_dual if (ratio_dual and profile.dual_income) else ratio_100
    limit = income_threshold(profile.household_size, ratio)
    if limit is None:
        return None
    return profile.monthly_income <= limit


# ---------------------------------------------------------------------------
# 신혼부부·한부모 자녀수 가산 결합표 (공고문 p.6, N1/N3 공통 — 표 자체가 동일함)
# 맞벌이·가구원수·출생자녀수(2023.3.28 이후) 조합에 따라 소득비율·자산·자동차가 동시에 바뀐다.
# ---------------------------------------------------------------------------
def spouse_terms_married(profile):
    """신혼부부/예비신혼부부용. 한부모가족은 별도 함수(spouse_terms_singleparent) 사용."""
    dual, size, child = profile.dual_income, profile.household_size, profile.young_child_count
    if size <= 2:
        return (130 if dual else 110), 345_000_000, 45_420_000
    if size == 3:
        if child == 0:
            return (120 if dual else 100), 345_000_000, 45_420_000
        return (130 if dual else 110), 379_000_000, 49_960_000
    # size >= 4
    if child == 0:
        return (120 if dual else 100), 345_000_000, 45_420_000
    if child == 1:
        return (130 if dual else 110), 379_000_000, 49_960_000
    return (140 if dual else 120), 413_000_000, 54_510_000


def spouse_terms_singleparent(profile):
    """한부모가족용. 맞벌이 개념 없음(단독세대주)."""
    size, child = profile.household_size, profile.young_child_count
    if size <= 2:
        return (110 if child == 0 else 120), (345_000_000 if child == 0 else 379_000_000), \
               (45_420_000 if child == 0 else 49_960_000)
    # size >= 3
    if child == 0:
        return 100, 345_000_000, 45_420_000
    if child == 1:
        return 110, 379_000_000, 49_960_000
    return 120, 413_000_000, 54_510_000


def _make_spouse_conditions(prefix, terms_func, income_ref, asset_ref, car_ref, sub_ref,
                             marital_field, marital_ok, marital_note):
    def income_check(p):
        ratio, _asset, _car = terms_func(p)
        limit = income_threshold(p.household_size, ratio)
        return None if limit is None else p.monthly_income <= limit

    def asset_check(p):
        _ratio, asset, _car = terms_func(p)
        return p.total_assets <= asset

    def car_check(p):
        _ratio, _asset, car = terms_func(p)
        return _car_ok(p, car)

    return [
        RuleCondition(f"{prefix}-marital", "marital_status", True, marital_field,
                      lambda p: p.marital_status in marital_ok,
                      note=marital_note),
        RuleCondition(f"{prefix}-home", "home_ownership", True, "공통 무주택요건",
                      lambda p: p.home_ownership == "무주택",
                      note="무주택 세대구성원인지"),
        RuleCondition(f"{prefix}-income", "household_income", True, income_ref, income_check,
                      note="가구 소득이 자녀수·맞벌이 여부에 따른 소득기준(가산표) 이내인지"),
        RuleCondition(f"{prefix}-assets", "total_assets", True, asset_ref, asset_check,
                      note="총자산이 자녀수에 따른 자산기준(가산표) 이내인지"),
        RuleCondition(f"{prefix}-car", "car_value", True, car_ref, car_check,
                      note="자동차가액이 자녀수에 따른 자동차기준(가산표) 이내인지"),
        RuleCondition(f"{prefix}-sub", "has_subscription_account", True, sub_ref,
                      lambda p: True,
                      note="입주 전까지 본인 또는 배우자 명의 청약통장 가입사실을 증명할 수 있는지(신청 시점 미가입은 무방)"),  # 유예조건 — 입주 전까지 가입하면 됨
    ]


# ---------------------------------------------------------------------------
# N1. 서울공릉 신혼희망타운 행복주택 — 신혼부부·한부모만 공급
# ---------------------------------------------------------------------------
n1_married_conditions = _make_spouse_conditions(
    "N1-M", spouse_terms_married,
    "공고문 p.5 ③(+p.6 자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ⑤",
    "공고문 p.4 ①-㉮/㉯", {"혼인중", "예비신혼"},
    "혼인 중이거나 예비신혼부부인지",
)
n1_singleparent_conditions = _make_spouse_conditions(
    "N1-S", spouse_terms_singleparent,
    "공고문 p.5 ③(+p.6 자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ⑤",
    "공고문 p.4 ①-㉰", {"한부모"},
    "한부모가족인지",
)

N1 = NoticeRuleSet(
    notice_id="N1", title="서울공릉 신혼희망타운 행복주택",
    layers={
        "신혼부부": LayerRuleSet("신혼부부", n1_married_conditions),
        "한부모": LayerRuleSet("한부모", n1_singleparent_conditions),
    },
)

# ---------------------------------------------------------------------------
# N2. 서울관악봉천 행복주택 — 대학생만 공급(기숙사형)
# ---------------------------------------------------------------------------
n2_student_conditions = [
    RuleCondition("N2-R4", "marital_status", True, "공고문 p.5 ②",
                  lambda p: p.marital_status == "미혼",
                  note="미혼인지"),
    RuleCondition("N2-R5", "home_ownership", True, "공고문 p.4",
                  lambda p: p.home_ownership == "무주택",
                  note="무주택 세대구성원인지"),
    RuleCondition("N2-R6", "income(본인+부모)", True, "공고문 p.5 ③",
                  lambda p: _income_ok_simple(p, 120 if p.household_size == 1
                                               else 110 if p.household_size == 2 else 100),
                  note="본인+부모(1인가구는 본인만) 합산 소득이 가구원수별 소득기준 이내인지"),
    RuleCondition("N2-R7", "total_assets", True, "공고문 p.5 ④",
                  lambda p: p.total_assets <= 108_000_000,
                  note="총자산이 1억 800만원 이내인지"),
    RuleCondition("N2-R8", "car_value", True, "공고문 p.5 ④",
                  # 대학생계층은 '소유 자체 금지' — 확인불가면 None, 0이면 True, 아니면 False
                  lambda p: None if p.car_value == "확인불가" else (p.car_value == 0),
                  note="자동차를 소유하고 있지 않은지(대학생계층은 소유 자체가 금지됨)"),
]

N2 = NoticeRuleSet(
    notice_id="N2", title="서울관악봉천 행복주택 예비입주자모집",
    layers={"대학생": LayerRuleSet("대학생", n2_student_conditions)},
)

# ---------------------------------------------------------------------------
# N3. 서울번동3 행복주택 — 대학생 + 청년 + 신혼부부·한부모 복합
# ---------------------------------------------------------------------------
n3_student_conditions = n2_student_conditions  # 대학생 조건은 N2와 동일(공고문 p.5)


def _youth_income_ok(p):
    """청년계층 소득판정: 세대원이면 가구원수를 무조건 1로 고정(income_basis 확인사항),
    세대주면 실제 가구원수로 조회."""
    if p.house_head_status == "세대원":
        limit = income_threshold(1, 120)  # 항상 1인가구 120% 기준(4,576,036원)
    else:
        ratio = 120 if p.household_size == 1 else 110 if p.household_size == 2 else 100
        limit = income_threshold(p.household_size, ratio)
    if limit is None:
        return None
    return p.monthly_income <= limit


n3_youth_conditions = [
    RuleCondition("N3-R6", "marital_status", True, "공고문 p.7 ②",
                  lambda p: p.marital_status == "미혼",
                  note="미혼인지"),
    RuleCondition("N3-R7/R7b", "household_income", True, "공고문 p.7 ③, p.8 소득기준표",
                  _youth_income_ok,
                  note="소득이 기준 이내인지(세대원은 가구원수 1인 기준 120%로 고정, 세대주는 실제 가구원수 기준)"),
    RuleCondition("N3-R8", "total_assets", True, "공고문 p.7 ④",
                  # ★ 자산은 세대원이어도 실제 가구원수 그대로 사용(비대칭 — 위 소득규칙과 다름)
                  lambda p: p.total_assets <= 251_000_000,
                  note="총자산이 2억 5,100만원 이내인지"),
    RuleCondition("N3-R9", "car_value", True, "공고문 p.7 ④",
                  lambda p: _car_ok(p, 45_420_000),
                  note="자동차가액이 4,542만원 이내인지"),
    RuleCondition("N3-R10", "has_subscription_account", True, "공고문 p.7 ⑤",
                  lambda p: True,
                  note="입주 전까지 청약통장 가입사실을 증명할 수 있는지(신청 시점 미가입은 무방)"),  # 유예조건
]

n3_married_conditions = _make_spouse_conditions(
    "N3-M", spouse_terms_married,
    "공고문 p.9 ③(+가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9 ⑤",
    "공고문 p.9 ①-㉮/㉯", {"혼인중", "예비신혼"},
    "혼인 중이거나 예비신혼부부인지",
)
n3_singleparent_conditions = _make_spouse_conditions(
    "N3-S", spouse_terms_singleparent,
    "공고문 p.9 ③(+가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9 ⑤",
    "공고문 p.9 ①-㉰", {"한부모"},
    "한부모가족인지",
)

N3 = NoticeRuleSet(
    notice_id="N3", title="서울번동3 행복주택",
    layers={
        "대학생": LayerRuleSet("대학생", n3_student_conditions),
        "청년": LayerRuleSet("청년", n3_youth_conditions),
        "신혼부부": LayerRuleSet("신혼부부", n3_married_conditions),
        "한부모": LayerRuleSet("한부모", n3_singleparent_conditions),
    },
)

ALL_NOTICES = {"N1": N1, "N2": N2, "N3": N3}

