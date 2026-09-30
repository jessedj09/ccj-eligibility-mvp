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
from datetime import date
from typing import Optional, Literal, List, Dict, Any

Verdict = Literal["ELIGIBLE", "INELIGIBLE", "NEEDS_INFO", "MANUAL_REVIEW", "NOT_OFFERED"]


# ---------------------------------------------------------------------------
# MANUAL_REVIEW — "사용자 정보 부족(NEEDS_INFO)"과 구분되는 "정책 해석 미확정" 상태.
# 사용자에게 정보를 더 받아도 해결되지 않고, 원문 재확인·사람 검토가 필요하다는 뜻이다.
# check 함수가 True/False/None 대신 ReviewNeeded를 반환하면 이 상태로 집계된다.
# ---------------------------------------------------------------------------
REVIEW_AMBIGUOUS_SOURCE = "AMBIGUOUS_SOURCE"            # 원문 표에 없는 조합이거나 해석이 갈림
REVIEW_SELF_REPORT_UNVERIFIED = "SELF_REPORT_UNVERIFIED"  # 자기신고로만 처리하는 세부요건에 의존


@dataclass(frozen=True)
class ReviewNeeded:
    code: str
    detail: str


def resolve_interpretations(results: Dict[str, Any], detail: str):
    """같은 조건을 여러 해석으로 계산한 결과를 하나로 합친다.

    - 하나라도 None(정보 부족)이면 None.
    - 모든 해석이 같은 True/False로 일치하면 그 값(해석이 갈려도 결과가 같으면 확정).
    - 해석에 따라 True/False가 갈리면 ReviewNeeded(AMBIGUOUS_SOURCE).
    """
    values = list(results.values())
    if any(v is None for v in values):
        return None
    if all(v == values[0] for v in values):
        return values[0]
    shown = ", ".join(f"{name}={'충족' if v else '불충족'}" for name, v in results.items())
    return ReviewNeeded(REVIEW_AMBIGUOUS_SOURCE, f"{detail} [{shown}]")
Layer = Literal["대학생", "청년", "신혼부부", "한부모"]


# ---------------------------------------------------------------------------
# 0. 날짜 계산 헬퍼 — 혼인기간·자녀 연령·졸업(중퇴) 경과기간은 전부
#    "기준일로부터 정확히 N년 전 날짜(컷오프)와의 직접 비교"로 판정한다(MVP0.1 신규).
#    주의: "경과 연수 = (on.year - start.year), 생일 미도래시 -1" 같은 만 나이 floor
#    공식은 "N년 이내"(<=N년) 경계에서 최대 364일까지 오차가 생긴다(예: 2년+1일 경과를
#    '2년 이내'로 잘못 통과시킴) — 그래서 여기서는 쓰지 않는다.
# ---------------------------------------------------------------------------
def years_before(on: date, n_years: int) -> date:
    """on으로부터 정확히 n_years년 전 날짜(2/29 기준일은 2/28로 보정)."""
    try:
        return on.replace(year=on.year - n_years)
    except ValueError:
        return on.replace(year=on.year - n_years, day=28)


def marriage_cutoff(on: date) -> date:
    """'혼인기간 7년 이내' — 공고일 정확히 7년 전 날짜(당일 포함) 이후 혼인신고."""
    return years_before(on, 7)


def young_child_cutoff(on: date) -> date:
    """'6세 이하 자녀' — 만 6세 이하 = 아직 만 7세가 되지 않음 = 공고일 7년 전 날짜의 '다음 날' 이후 출생.
    N1 원문 리터럴(공고일 2026.7.29 → 혼인 2019.7.29 / 출생 2019.7.30)을 이 공식이 그대로
    재현한다(tests/test_mvp0_2_manual_review.py). 하루 차이는 원문의 특이값이 아니라 만 나이 정의다."""
    from datetime import timedelta
    return years_before(on, 7) + timedelta(days=1)


def is_within_years(event_date: date, on: date, n_years: int) -> bool:
    """event_date가 on 기준 최근 n_years년 이내(컷오프 이후, 컷오프 당일 포함)인지."""
    return event_date >= years_before(on, n_years)

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
    house_head_status: Optional[str] = None   # "세대주" / "세대원" / None(정보 없음 — 대학생 등 무관 계층 포함)
    household_size: int = 1             # 판정 대상 가구원수 (계층별로 산정 기준이 다름 — 호출부에서 맞춰 넣음)
    # monthly_income/total_assets는 "미입력(모름)"과 "실제 0원"을 구분하기 위해 Optional이다.
    # None이면 확인불가(NEEDS_INFO)로 처리되고, 0은 실제 무소득/무자산으로 처리된다.
    monthly_income: Optional[int] = None   # 판정 대상 소득 (세대 전체 또는 본인만 — 계층별로 다름)
    total_assets: Optional[int] = None
    car_value: Any = 0                  # int 또는 "확인불가"
    has_subscription_account: bool = False
    subscription_months: int = 0
    subscription_payment_count: int = 0
    has_child_under_2: bool = False
    dual_income: bool = False           # 맞벌이 여부(신혼부부 소득비율 분기용)
    young_child_count: int = 0          # 2023.3.28 이후 출생(태아포함) 자녀 수 — 소득·자산 가산기준용
    residence_region: Optional[str] = None    # 우선공급 배점용(예: "노원구", "서울시(노원구외)")
    residence_years: float = 0.0        # 우선공급 배점용 — 해당 지역 거주기간(년)

    # --- MVP0.1 신규 필드 ---
    is_social_rookie: Optional[bool] = None
    # 청년계층 ①-㉯(사회초년생) 해당 여부 — 소득활동기간 5년 이내 등 세부요건은 자기신고 사실로만
    # 처리하며 엔진이 세부 증빙(예술인 인증, 구직급여 수급 등)을 검증하지 않는다(지원 범위 밖).

    student_status: Optional[str] = None
    # 대학생계층 ①-㉮/㉯ 해당 상태: "재학중" / "입학예정" / "복학예정" / "취업준비생" / None(미확인)
    grad_or_dropout_date: Optional[date] = None
    # student_status == "취업준비생"일 때만 사용 — 대학 또는 고등학교 졸업·중퇴일

    marriage_date: Optional[date] = None
    # 신혼부부(혼인중)의 혼인신고일 — 혼인기간 7년 이내 요건 판정용(예비신혼부부는 이 요건 자체가 없음)
    has_children: Optional[bool] = None
    # 자녀(6세 이하 여부와 무관)가 있는지: True/False/None(모름). False면 "6세 이하 자녀 없음"이
    # 확정된다. 이 필드가 없으면 '자녀 없음'과 '아직 입력 안 함'을 구분할 수 없어 혼인 7년 초과
    # 신혼부부·한부모가 영원히 NEEDS_INFO에 머문다(MVP0.2에서 발견).
    youngest_child_birth_date: Optional[date] = None
    # 막내 자녀 생년월일(태아 포함 시 예정일) — 신혼부부의 "6세 이하 자녀" 대체요건,
    # 한부모가족의 "6세 이하 자녀를 둔 자" 필수요건 판정용. young_child_count(출생자녀 가산용)와는
    # 별개 개념이다 — 가산은 2023.3.28 이후 출생아 수, 이 요건은 현재 6세 이하인지 여부다.


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
    announcement_date: Optional[date] = None   # 입주자모집공고일 — 혼인기간/자녀연령/졸업경과 계산 기준일
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
    review: List[str] = field(default_factory=list)              # 정책 해석 미확정 조건 rule_id
    review_reasons: Dict[str, ReviewNeeded] = field(default_factory=dict)


def evaluate(profile: HouseholdProfile, notice: NoticeRuleSet, layer: Layer) -> EvaluationResult:
    if layer not in notice.layers:
        return EvaluationResult(
            profile.profile_id, notice.notice_id, layer,
            verdict="NOT_OFFERED", score=None,
            matched=[], failed=[], unknown=[],
            notes=[f"{notice.title}에는 '{layer}' 계층 자체가 공급되지 않음"],
        )

    ruleset = notice.layers[layer]
    matched, failed, unknown, review = [], [], [], []
    review_reasons: Dict[str, ReviewNeeded] = {}

    for cond in ruleset.conditions:
        if not cond.required:
            continue  # 가점/배점 항목은 verdict에 영향 없음 (score도 별도 관리)
        result = cond.check(profile)
        if isinstance(result, ReviewNeeded):
            review.append(cond.rule_id)
            review_reasons[cond.rule_id] = result
        elif result is True:
            matched.append(cond.rule_id)
        elif result is False:
            failed.append(cond.rule_id)
        else:  # None = 확인 불가
            unknown.append(cond.rule_id)

    total_required = len(matched) + len(failed) + len(unknown) + len(review)
    score = round(len(matched) / total_required * 100, 1) if total_required else None

    # 우선순위: 확정 불충족 > 정책 해석 미확정 > 정보 부족 > 충족.
    # 해석 미확정이 남아 있으면 사용자가 정보를 더 입력해도 최종 확정이 안 되므로
    # 정보 부족(NEEDS_INFO)보다 먼저 알린다(정보 부족 조건은 unknown 목록에 그대로 남는다).
    if failed:
        verdict: Verdict = "INELIGIBLE"
    elif review:
        verdict = "MANUAL_REVIEW"
    elif unknown:
        verdict = "NEEDS_INFO"
    else:
        verdict = "ELIGIBLE"

    return EvaluationResult(
        profile.profile_id, notice.notice_id, layer, verdict, score,
        matched, failed, unknown, notes=[],
        review=review, review_reasons=review_reasons,
    )


# ---------------------------------------------------------------------------
# 5. 입력 검증 — evaluate() 진입 전에 자료형·범위·모순을 걸러낸다.
#    (MVP0.1: "엔진에 소득 None을 전달하면 예외가 발생하는 문제" 등 방지)
#    반환값이 비어있지 않으면 evaluate()를 호출하지 말고 이 오류를 그대로 사용자에게 보여준다.
# ---------------------------------------------------------------------------
def validate_profile(profile: HouseholdProfile) -> List[str]:
    errors: List[str] = []

    if not (0 <= profile.age <= 120):
        errors.append("나이는 0~120 사이여야 합니다.")
    if profile.household_size < 1:
        errors.append("가구원수는 1 이상이어야 합니다.")
    if profile.monthly_income is not None and profile.monthly_income < 0:
        errors.append("월소득은 음수일 수 없습니다.")
    if profile.total_assets is not None and profile.total_assets < 0:
        errors.append("총자산은 음수일 수 없습니다.")
    if isinstance(profile.car_value, (int, float)) and profile.car_value < 0:
        errors.append("자동차가액은 음수일 수 없습니다.")
    if profile.young_child_count < 0:
        errors.append("출생자녀 수는 음수일 수 없습니다.")

    today = date.today()
    if profile.marriage_date is not None and profile.marriage_date > today:
        errors.append("혼인일이 미래 날짜입니다.")
    if profile.youngest_child_birth_date is not None and profile.youngest_child_birth_date > today:
        errors.append("자녀 생년월일이 미래 날짜입니다.")
    if profile.grad_or_dropout_date is not None and profile.grad_or_dropout_date > today:
        errors.append("졸업/중퇴일이 미래 날짜입니다.")

    if profile.has_children is False and (
            profile.youngest_child_birth_date is not None or profile.young_child_count > 0):
        errors.append("자녀가 없다고 입력했는데 자녀 생년월일 또는 출생자녀 가산 수가 입력되어 있습니다.")
    if profile.house_head_status not in (None, "세대주", "세대원"):
        errors.append("세대주/세대원 값이 올바르지 않습니다.")

    return errors
