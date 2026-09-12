# -*- coding: utf-8 -*-
"""
notices_data.py
===============
rules 시트의 3개 공고(N1 공릉/N2 관악봉천/N3 번동3)를 실제 판정 가능한 코드로 옮긴 것.
각 조건의 check 함수는 profile을 받아 True(충족)/False(불충족)/None(확인불가)을 반환한다.

주의: 여기서는 '소득/자산 판정' 핵심 조건 위주로 구현했다. 우선공급 배점(N1-P2/P3),
서류제출 절차, 단지여건 등 verdict에 영향 없는 항목은 옮기지 않았다 — MVP0 검증 목적에
필요한 최소 범위다.
"""

from rule_engine import RuleCondition, LayerRuleSet, NoticeRuleSet, income_threshold


def _car_ok(profile, limit):
    """car_value가 '확인불가'면 None, 숫자면 한도 비교."""
    if profile.car_value == "확인불가":
        return None
    return profile.car_value <= limit


def _income_ok(profile, ratio_100, ratio_dual=None):
    """household_size·monthly_income 기준 일반/맞벌이 비율 분기."""
    ratio = ratio_dual if (ratio_dual and profile.dual_income) else ratio_100
    limit = income_threshold(profile.household_size, ratio)
    if limit is None:
        return None
    return profile.monthly_income <= limit


# ---------------------------------------------------------------------------
# N1. 서울공릉 신혼희망타운 행복주택 — 신혼부부·한부모만 공급
# ---------------------------------------------------------------------------
n1_spouse_conditions = [
    RuleCondition("N1-R1", "home_ownership", True, "공고문 p.3",
                  lambda p: p.home_ownership == "무주택"),
    RuleCondition("N1-R5", "household_income", True, "공고문 p.5 ③",
                  # 2인가구는 110%(맞벌이130%), 3인이상은 100%(맞벌이120%)
                  lambda p: _income_ok(p, 110 if p.household_size == 2 else 100,
                                       130 if p.household_size == 2 else 120)),
    RuleCondition("N1-R6", "total_assets", True, "공고문 p.6 ④",
                  lambda p: p.total_assets <= 345_000_000),
    RuleCondition("N1-R7", "car_value", True, "공고문 p.6 ④",
                  lambda p: _car_ok(p, 45_420_000)),
    RuleCondition("N1-R8", "has_subscription_account", True, "공고문 p.6 ⑤",
                  # 유예조건: 신청시점 미가입이어도 '입주전까지 가입예정' 의사만 있으면 통과 처리
                  lambda p: True),
    RuleCondition("N1-R2/R4", "home_ownership_extra", True, "공고문 p.4-5",
                  lambda p: p.home_ownership == "무주택"),  # 무주택 중복 체크(단순화)
]

N1 = NoticeRuleSet(
    notice_id="N1", title="서울공릉 신혼희망타운 행복주택",
    layers={
        "신혼부부": LayerRuleSet("신혼부부", n1_spouse_conditions),
        "한부모": LayerRuleSet("한부모", n1_spouse_conditions),
    },
)

# ---------------------------------------------------------------------------
# N2. 서울관악봉천 행복주택 — 대학생만 공급(기숙사형)
# ---------------------------------------------------------------------------
n2_student_conditions = [
    RuleCondition("N2-R4", "marital_status", True, "공고문 p.5 ②",
                  lambda p: p.marital_status == "미혼"),
    RuleCondition("N2-R5", "home_ownership", True, "공고문 p.4",
                  lambda p: p.home_ownership == "무주택"),
    RuleCondition("N2-R6", "income(본인+부모)", True, "공고문 p.5 ③",
                  lambda p: _income_ok(p, 120 if p.household_size == 1
                                        else 110 if p.household_size == 2 else 100)),
    RuleCondition("N2-R7", "total_assets", True, "공고문 p.5 ④",
                  lambda p: p.total_assets <= 108_000_000),
    RuleCondition("N2-R8", "car_value", True, "공고문 p.5 ④",
                  # 대학생계층은 '소유 자체 금지' — 확인불가면 None, 0이면 True, 아니면 False
                  lambda p: None if p.car_value == "확인불가" else (p.car_value == 0)),
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
                  lambda p: p.marital_status == "미혼"),
    RuleCondition("N3-R7/R7b", "household_income", True, "공고문 p.7 ③, p.8 소득기준표",
                  _youth_income_ok),
    RuleCondition("N3-R8", "total_assets", True, "공고문 p.7 ④",
                  # ★ 자산은 세대원이어도 실제 가구원수 그대로 사용(비대칭 — 위 소득규칙과 다름)
                  lambda p: p.total_assets <= 251_000_000),
    RuleCondition("N3-R9", "car_value", True, "공고문 p.7 ④",
                  lambda p: _car_ok(p, 45_420_000)),
    RuleCondition("N3-R10", "has_subscription_account", True, "공고문 p.7 ⑤",
                  lambda p: True),  # 유예조건
]

n3_spouse_conditions = [
    RuleCondition("N3-R11", "household_income", True, "공고문 p.9 ③",
                  lambda p: _income_ok(p, 110 if p.household_size == 2 else 100,
                                       130 if p.household_size == 2 else 120)),
    RuleCondition("N3-R12", "total_assets", True, "공고문 p.9-10 ④",
                  lambda p: p.total_assets <= 345_000_000),
    RuleCondition("N3-R13", "car_value", True, "공고문 p.9-10 ④",
                  lambda p: _car_ok(p, 45_420_000)),
    RuleCondition("N3-R14", "has_subscription_account", True, "공고문 p.9 ⑤",
                  lambda p: True),  # 유예조건
    RuleCondition("N3-home", "home_ownership", True, "공고문 p.4",
                  lambda p: p.home_ownership == "무주택"),
]

N3 = NoticeRuleSet(
    notice_id="N3", title="서울번동3 행복주택",
    layers={
        "대학생": LayerRuleSet("대학생", n3_student_conditions),
        "청년": LayerRuleSet("청년", n3_youth_conditions),
        "신혼부부": LayerRuleSet("신혼부부", n3_spouse_conditions),
        "한부모": LayerRuleSet("한부모", n3_spouse_conditions),
    },
)

ALL_NOTICES = {"N1": N1, "N2": N2, "N3": N3}
