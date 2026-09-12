# -*- coding: utf-8 -*-
"""
Eligibility Rule Engine — MVP0
==============================
역할: 저장된 사용자 프로필(HouseholdProfile) + 검증된 정책 조건(NoticeRuleSet)을 입력받아
     결정론적으로 ELIGIBLE / INELIGIBLE / NEEDS_INFO / NOT_OFFERED 를 판정한다.
     LLM은 여기 관여하지 않는다 — 이 파일은 순수 조건식 평가기다.

이 파일에 들어있는 3개 공고(N1 공릉, N2 관악봉천, N3 번동3)의 조건은
워크북 rules/reference_values/income_basis 시트를 그대로 코드로 옮긴 것이다.
"""

from dataclasses import dataclass, field
from typing import Optional, Literal, List, Dict, Any

Verdict = Literal["ELIGIBLE", "INELIGIBLE", "NEEDS_INFO", "NOT_OFFERED"]
Layer = Literal["대학생", "청년", "신혼부부", "한부모"]

# ---------------------------------------------------------------------------
# 1. reference_values — 도시근로자 가구원수별 가구당 월평균소득 (2025년도 기준)
#    3개 공고문 전부 교차검증되어 일치함(income_basis 시트 참조)
# ---------------------------------------------------------------------------
INCOME_TABLE: Dict[int, Dict[int, int]] = {
    # 가구원수: {비율(%): 원}
    1: {100: None, 110: None, 120: 4_576_036, 130: None, 140: None},
    2: {100: None, 110: 6_452_897, 120: 7_039_524, 130: 7_626_151, 140: 8_212_778},
    3: {100: 8_168_429, 110: 8_985_272, 120: 9_802_115, 130: 10_618_958, 140: 11_435_801},
    4: {100: 8_802_202, 110: 9_682_422, 120: 10_562_642, 130: 11_442_863, 140: 12_323_083},
    5: {100: 9_326_985, 110: 10_259_684, 120: 11_192_382, 130: 12_125_081, 140: 13_057_779},
    6: {100: 9_906_263, 110: 10_896_889, 120: 11_887_516, 130: 12_878_142, 140: 13_868_768},
}
PER_PERSON_ADDER_7PLUS = 579_278  # 7인 이상 가구는 6인 기준 + 1인당 이 금액


def income_threshold(household_size: int, ratio_pct: int) -> Optional[int]:
    """가구원수·비율로 소득 상한액 조회. 표에 없는 조합이면 None(=확인불가)."""
    size = min(household_size, 6)
    base = INCOME_TABLE.get(size, {}).get(ratio_pct)
    if base is None:
        return None
    if household_size > 6:
        return base + PER_PERSON_ADDER_7PLUS * (household_size - 6)
    return base


# ---------------------------------------------------------------------------
# 2. HouseholdProfile — 사용자 입력. house_head_status 등은 "등본 사실값"으로
#    그대로 받는다(Rule Engine이 추론하지 않는다 — income_basis 시트 결론).
# ---------------------------------------------------------------------------
@dataclass
class HouseholdProfile:
    profile_id: str
    age: int
    marital_status: str                 # "미혼" / "혼인중" / "예비신혼" / "한부모"
    home_ownership: str                 # "무주택" / "주택보유"
    house_head_status: Optional[str] = None   # "세대주" / "세대원" / None(대학생 등 무관 계층)
    household_size: int = 1             # 판정 대상 가구원수 (계층별로 산정 기준이 다름 — 호출부에서 맞춰 넣음)
    monthly_income: int = 0             # 판정 대상 소득 (세대 전체 또는 본인만 — 계층별로 다름)
    total_assets: int = 0
    car_value: Any = 0                  # int 또는 "확인불가"
    has_subscription_account: bool = False
    subscription_months: int = 0
    subscription_payment_count: int = 0
    has_child_under_2: bool = False
    dual_income: bool = False           # 맞벌이 여부(신혼부부 소득비율 분기용)
    young_child_count: int = 0          # 2023.3.28 이후 출생(태아포함) 자녀 수 — 소득·자산 가산기준용
    residence_region: Optional[str] = None    # 우선공급 배점용(예: "노원구", "서울시(노원구외)")
    residence_years: float = 0.0        # 우선공급 배점용 — 해당 지역 거주기간(년)


# ---------------------------------------------------------------------------
# 3. RuleCondition — rules 시트 한 행에 대응
# ---------------------------------------------------------------------------
@dataclass
class RuleCondition:
    rule_id: str
    field: str
    required: bool
    source_ref: str
    check: Any        # callable(profile) -> True/False/None(확인불가)
    note: str = ""


@dataclass
class LayerRuleSet:
    layer: Layer
    conditions: List[RuleCondition]


@dataclass
class NoticeRuleSet:
    notice_id: str
    title: str
    layers: Dict[Layer, LayerRuleSet] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 4. 판정 엔진
# ---------------------------------------------------------------------------
@dataclass
class EvaluationResult:
    profile_id: str
    notice_id: str
    layer: Layer
    verdict: Verdict
    score: Optional[float]
    matched: List[str]
    failed: List[str]
    unknown: List[str]
    notes: List[str]


def evaluate(profile: HouseholdProfile, notice: NoticeRuleSet, layer: Layer) -> EvaluationResult:
    if layer not in notice.layers:
        return EvaluationResult(
            profile.profile_id, notice.notice_id, layer,
            verdict="NOT_OFFERED", score=None,
            matched=[], failed=[], unknown=[],
            notes=[f"{notice.title}에는 '{layer}' 계층 자체가 공급되지 않음"],
        )

    ruleset = notice.layers[layer]
    matched, failed, unknown = [], [], []

    for cond in ruleset.conditions:
        if not cond.required:
            continue  # 가점/배점 항목은 verdict에 영향 없음 (score도 별도 관리)
        result = cond.check(profile)
        if result is True:
            matched.append(cond.rule_id)
        elif result is False:
            failed.append(cond.rule_id)
        else:  # None = 확인 불가
            unknown.append(cond.rule_id)

    total_required = len(matched) + len(failed) + len(unknown)
    score = round(len(matched) / total_required * 100, 1) if total_required else None

    if failed:
        verdict: Verdict = "INELIGIBLE"
    elif unknown:
        verdict = "NEEDS_INFO"
    else:
        verdict = "ELIGIBLE"

    return EvaluationResult(
        profile.profile_id, notice.notice_id, layer, verdict, score,
        matched, failed, unknown, notes=[],
    )
