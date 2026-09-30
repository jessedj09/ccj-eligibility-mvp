# -*- coding: utf-8 -*-
"""
notices_data.py
===============
rules 시트의 3개 공고(N1 공릉/N2 관악봉천/N3 번동3)를 실제 판정 가능한 코드로 옮긴 것.
각 조건의 check 함수는 profile을 받아 True(충족)/False(불충족)/None(확인불가)을 반환한다.

MVP0.1 갱신(ChatGPT Codex 리뷰 반영, docs/rule-coverage-matrix.md 참조):
- 대학생/청년의 재학·연령·자녀가산 요건, 신혼부부 혼인기간·한부모 자녀연령 요건 추가.
- 소득 None(미입력)·세대주 정보 None(미확인)을 더 이상 특정 값으로 추정하지 않고
  NEEDS_INFO(None)로 처리하도록 수정.
"""

from datetime import date

from rule_engine import (
    RuleCondition, LayerRuleSet, NoticeRuleSet, income_threshold,
    is_within_years, marriage_cutoff, young_child_cutoff, bonus_child_count,
    ReviewNeeded, resolve_interpretations,
    REVIEW_AMBIGUOUS_SOURCE, REVIEW_SELF_REPORT_UNVERIFIED,
)


def _car_ok(profile, limit):
    """car_value가 '확인불가'면 None, 숫자면 한도 비교."""
    if profile.car_value == "확인불가":
        return None
    return profile.car_value <= limit


def _children_for_bonus(p, announcement_date):
    """출생자녀 가산 대상 자녀 수. 자녀 생년월일 목록이 있으면 엔진이 공고별 기준일로 직접 계산하고,
    없으면 기존 입력(young_child_count)을 그대로 쓴다."""
    if p.children_birth_dates is not None:
        return bonus_child_count(p.children_birth_dates, announcement_date)
    return p.young_child_count


def _income_le(monthly_income, limit):
    if monthly_income is None or limit is None:
        return None
    return monthly_income <= limit


def _assets_le(total_assets, limit):
    if total_assets is None:
        return None
    return total_assets <= limit


# ---------------------------------------------------------------------------
# 대학생/청년 공통 — 출생자녀 수에 따른 소득비율 가산(공고문 p.5/p.7).
# 자녀가 있으려면 가구원수가 최소 3인 이상이어야 한다는 게 원문 표의 전제라
# 1인/2인 가구 행은 자녀 0인 값만 정의되어 있다(원문 그대로).
# ---------------------------------------------------------------------------
def _size_based_ratio(household_size, young_child_count):
    """1인=120%/2인=110%/3인이상은 자녀수(0/1/2+)에 따라 100%/110%/120%."""
    if household_size <= 1:
        return 120
    if household_size == 2:
        return 110
    if young_child_count <= 0:
        return 100
    if young_child_count == 1:
        return 110
    return 120


# ---------------------------------------------------------------------------
# 대학생 계층 — 재학요건 + 자녀가산 (공고문 N2 p.5, N3 대학생은 동일 조항 재사용)
# ---------------------------------------------------------------------------
def _student_status_ok(profile, announcement_date):
    """①-㉮(재학중/입학예정/복학예정) 또는 ①-㉯(취업준비생, 졸업·중퇴 2년 이내)."""
    if profile.student_status is None:
        return None
    if profile.student_status in ("재학중", "입학예정", "복학예정"):
        return True
    if profile.student_status == "취업준비생":
        if profile.grad_or_dropout_date is None:
            return None
        return is_within_years(profile.grad_or_dropout_date, announcement_date, 2)
    return False  # 위 범주에 없는 값은 재학·취업준비생 어느 쪽도 충족하지 못한 것으로 처리


def _student_asset_limit(household_size, young_child_count):
    if household_size <= 1 or household_size == 2 or young_child_count <= 0:
        return 108_000_000
    if young_child_count == 1:
        return 119_000_000
    return 130_000_000


_GENERAL_BONUS_NAME = "자녀 가산 일반규칙 적용(원문 표에 이 가구원수 행이 없음)"
_TABLE_NAME = "원문 표 그대로"


def _no_table_row(p):
    """가구원수 1인인데 출생자녀 가산을 받는 조합 — 자녀가 가구원에 포함되므로 입력 모순이거나
    원문 표에 없는 조합이다. 임의로 한쪽을 택하지 않고 수동 검토로 넘긴다."""
    return ReviewNeeded(
        REVIEW_AMBIGUOUS_SOURCE,
        "가구원수 1인인데 출생자녀 가산 대상 자녀가 있음 — 입력 모순이거나 원문 표에 없는 조합")


def _student_interpretations(p, child):
    """대학생 (비율%, 자산한도) 해석 후보.

    원문 표(N2 p.5)는 가구원수 3인 이상에만 자녀 1명/2명 행이 있다. 그런데 대학생의 가구원수에는
    직계비속이 포함되므로(N2 p.6) 본인+자녀 2인 가구가 가능하고, 이 조합은 표에 없다. 본문의
    "출산자녀 1인 10%/2인 이상 20% 가산" 일반규칙을 적용하면 가산이 붙는다 — 표를 글자 그대로
    읽으면 안 붙는다. 어느 쪽이 맞는지 원문만으로 확정할 수 없어 두 해석을 모두 계산한다.
    """
    size = p.household_size
    options = {_TABLE_NAME: (_size_based_ratio(size, child), _student_asset_limit(size, child))}
    if size == 2 and child >= 1:
        options[_GENERAL_BONUS_NAME] = (120 if child == 1 else 130,
                                        119_000_000 if child == 1 else 130_000_000)
    return options


def _make_student_conditions(prefix, marital_ref, home_ref, student_ref, income_ref,
                              asset_ref, car_ref, announcement_date):
    def student_check(p):
        return _student_status_ok(p, announcement_date)

    def income_check(p):
        if p.monthly_income is None:
            return None
        child = _children_for_bonus(p, announcement_date)
        if p.household_size <= 1 and child >= 1:
            return _no_table_row(p)
        limits = {name: income_threshold(p.household_size, ratio)
                  for name, (ratio, _a) in _student_interpretations(p, child).items()}
        if any(v is None for v in limits.values()):
            return None
        return resolve_interpretations(
            {name: p.monthly_income <= v for name, v in limits.items()},
            "대학생 출생자녀 가산 소득기준 해석 불일치")

    def asset_check(p):
        if p.total_assets is None:
            return None
        child = _children_for_bonus(p, announcement_date)
        if p.household_size <= 1 and child >= 1:
            return _no_table_row(p)
        limits = {name: asset for name, (_r, asset) in _student_interpretations(p, child).items()}
        return resolve_interpretations(
            {name: p.total_assets <= v for name, v in limits.items()},
            "대학생 출생자녀 가산 자산기준 해석 불일치")

    return [
        RuleCondition(f"{prefix}4", "marital_status", True, marital_ref,
                      lambda p: p.marital_status == "미혼",
                      note="미혼인지"),
        RuleCondition(f"{prefix}5", "home_ownership", True, home_ref,
                      lambda p: p.home_ownership == "무주택",
                      note="무주택자인지(본인 기준)"),
        RuleCondition(f"{prefix}5c", "student_status", True, student_ref,
                      student_check,
                      note="'대학'에 재학중/입학·복학예정이거나, 대학·고등학교 졸업·중퇴 2년 "
                           "이내의 취업준비생인지"),
        RuleCondition(f"{prefix}6", "income(본인+부모)", True, income_ref,
                      income_check,
                      note="본인+부모(등본 등재 여부 무관, 1인가구는 본인만) 합산 소득이 "
                           "출생자녀 가산을 반영한 소득기준 이내인지"),
        RuleCondition(f"{prefix}7", "total_assets", True, asset_ref,
                      asset_check,
                      note="본인 총자산이 출생자녀 가산을 반영한 자산기준 이내인지"),
        RuleCondition(f"{prefix}8", "car_value", True, car_ref,
                      lambda p: None if p.car_value == "확인불가" else (p.car_value == 0),
                      note="자동차를 소유하고 있지 않은지(대학생계층은 소유 자체가 금지됨)"),
    ]


# ---------------------------------------------------------------------------
# 신혼부부·한부모 자녀수 가산 결합표 (공고문 p.6, N1/N3 공통 — 표 자체가 동일함)
# 맞벌이·가구원수·출생자녀수(2023.3.28 이후) 조합에 따라 소득비율·자산·자동차가 동시에 바뀐다.
# ---------------------------------------------------------------------------
def spouse_terms_married(profile, child):
    """신혼부부/예비신혼부부용. 한부모가족은 별도 함수(spouse_terms_singleparent) 사용."""
    dual, size = profile.dual_income, profile.household_size
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


def spouse_terms_singleparent(profile, child):
    """한부모가족용. 맞벌이 개념 없음(단독세대주)."""
    size = profile.household_size
    if size <= 2:
        return (110 if child == 0 else 120), (345_000_000 if child == 0 else 379_000_000), \
               (45_420_000 if child == 0 else 49_960_000)
    # size >= 3
    if child == 0:
        return 100, 345_000_000, 45_420_000
    if child == 1:
        return 110, 379_000_000, 49_960_000
    return 120, 413_000_000, 54_510_000


def _marriage_or_child_ok(p, marriage_cutoff, child_cutoff):
    """②(신혼부부 전용) 혼인기간 7년 이내 OR 6세 이하 자녀. 예비신혼부부는 이 요건 자체가 없다."""
    if p.marital_status == "예비신혼":
        return True
    duration_ok = None
    if p.marriage_date is not None:
        duration_ok = p.marriage_date >= marriage_cutoff
    child_ok = _young_child_status(p, child_cutoff)
    if duration_ok or child_ok:
        return True
    if duration_ok is False and child_ok is False:
        return False
    return None  # 최소 한쪽이 미확인이고 나머지도 통과가 아님


def _young_child_status(p, child_cutoff):
    """6세 이하 자녀 여부: 자녀 없음 확정(False) / 막내 생년월일로 판정 / 모름(None)."""
    if p.has_children is False:
        return False
    if p.youngest_child_birth_date is None:
        return None
    return p.youngest_child_birth_date >= child_cutoff


def _child_under6_ok(p, child_cutoff):
    """①-㉰(한부모 전용) 6세 이하 자녀를 둔 자."""
    return _young_child_status(p, child_cutoff)


def _make_spouse_conditions(prefix, terms_func, income_ref, asset_ref, car_ref, sub_ref,
                             marital_field, marital_ok, marital_note, group,
                             marriage_cutoff, child_cutoff, announcement_date, duration_ref):
    def income_check(p):
        ratio, _asset, _car = terms_func(p, _children_for_bonus(p, announcement_date))
        limit = income_threshold(p.household_size, ratio)
        return _income_le(p.monthly_income, limit)

    def asset_check(p):
        _ratio, asset, _car = terms_func(p, _children_for_bonus(p, announcement_date))
        return _assets_le(p.total_assets, asset)

    def car_check(p):
        _ratio, _asset, car = terms_func(p, _children_for_bonus(p, announcement_date))
        return _car_ok(p, car)

    conditions = [
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
                      note="[입주 전까지 이행] 본인 또는 배우자 명의 청약통장 가입사실을 "
                           "증명할 수 있는지(신청 시점 미가입은 현재 자격에 영향 없음)"),
    ]

    if group == "married":
        conditions.append(RuleCondition(
            f"{prefix}-duration", "marriage_duration_or_child",
            True, duration_ref,
            lambda p: _marriage_or_child_ok(p, marriage_cutoff, child_cutoff),
            note="혼인기간 7년 이내이거나 6세 이하 자녀(태아포함)를 두었는지 "
                 "(예비신혼부부는 이 요건이 적용되지 않음)",
        ))
    elif group == "singleparent":
        conditions.append(RuleCondition(
            f"{prefix}-child6", "youngest_child_birth_date",
            True, duration_ref,
            lambda p: _child_under6_ok(p, child_cutoff),
            note="6세 이하 자녀(태아포함)를 둔 한부모인지",
        ))

    return conditions


# ---------------------------------------------------------------------------
# N1. 서울공릉 신혼희망타운 행복주택 — 신혼부부·한부모만 공급 (공고일 2026.7.29)
# ---------------------------------------------------------------------------
N1_ANNOUNCEMENT = date(2026, 7, 29)
# 원문(p.5)이 명시한 리터럴 컷오프 — 일반 공식(공고일-N년)으로 재계산하지 않는다.
# "혼인기간 7년 이내: 2019.7.29. 이후 혼인신고" / "6세 이하 자녀: 2019.7.30. 이후 출생"
N1_MARRIAGE_CUTOFF = date(2019, 7, 29)
N1_CHILD_CUTOFF = date(2019, 7, 30)

n1_married_conditions = _make_spouse_conditions(
    "N1-M", spouse_terms_married,
    "공고문 p.5 ③(+p.6 자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ⑤",
    "공고문 p.4 ①-㉮/㉯", {"혼인중", "예비신혼"},
    "혼인 중이거나 예비신혼부부인지", "married", N1_MARRIAGE_CUTOFF, N1_CHILD_CUTOFF, N1_ANNOUNCEMENT,
    "공고문 p.5 ②",
)
n1_singleparent_conditions = _make_spouse_conditions(
    "N1-S", spouse_terms_singleparent,
    "공고문 p.5 ③(+p.6 자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ⑤",
    "공고문 p.4 ①-㉰", {"한부모"},
    "한부모가족인지", "singleparent", N1_MARRIAGE_CUTOFF, N1_CHILD_CUTOFF, N1_ANNOUNCEMENT,
    "공고문 p.4 ①-㉰",
)

N1 = NoticeRuleSet(
    notice_id="N1", title="서울공릉 신혼희망타운 행복주택",
    announcement_date=N1_ANNOUNCEMENT,
    layers={
        "신혼부부": LayerRuleSet("신혼부부", n1_married_conditions),
        "한부모": LayerRuleSet("한부모", n1_singleparent_conditions),
    },
)

# ---------------------------------------------------------------------------
# N2. 서울관악봉천 행복주택 — 대학생만 공급(기숙사형) (공고일 2026.7.15)
# ---------------------------------------------------------------------------
N2_ANNOUNCEMENT = date(2026, 7, 15)

n2_student_conditions = _make_student_conditions(
    "N2-R", "공고문 p.5 ②", "공고문 p.4", "공고문 p.5 ①-㉮/㉯", "공고문 p.5 ③",
    "공고문 p.5 ④", "공고문 p.5 ④", N2_ANNOUNCEMENT,
)

N2 = NoticeRuleSet(
    notice_id="N2", title="서울관악봉천 행복주택 예비입주자모집",
    announcement_date=N2_ANNOUNCEMENT,
    layers={"대학생": LayerRuleSet("대학생", n2_student_conditions)},
)

# ---------------------------------------------------------------------------
# N3. 서울번동3 행복주택 — 대학생 + 청년 + 신혼부부·한부모 복합 (공고일 2026.8.19)
# ---------------------------------------------------------------------------
N3_ANNOUNCEMENT = date(2026, 8, 19)

n3_student_conditions = _make_student_conditions(
    "N3-R", "공고문 p.7 ②", "공고문 p.7", "공고문 p.7 ①-㉮/㉯", "공고문 p.7 ③",
    "공고문 p.7 ④", "공고문 p.7 ④", N3_ANNOUNCEMENT,
)


def _youth_age_or_rookie_ok(p):
    """➀-㉮(19~39세) 또는 ➀-㉯(사회초년생).

    나이가 범위 안이면 사회초년생 정보와 무관하게 확정 충족이다. 나이가 범위 밖인데 사회초년생이
    '예'라고 자기신고한 경우는 세부요건(소득활동기간 5년 이내, 재직/구직급여/예술인 3가지 경로)을
    엔진이 검증하지 못하므로 ELIGIBLE로 확정하지 않고 수동 검토로 넘긴다(MVP0.2).
    """
    if 19 <= p.age <= 39:
        return True
    if p.is_social_rookie is True:
        return ReviewNeeded(
            REVIEW_SELF_REPORT_UNVERIFIED,
            "사회초년생 경로(소득활동기간 5년 이내 등 세부요건)는 자기신고이며 증빙을 검증하지 않음")
    if p.is_social_rookie is False:
        return False
    return None


def _youth_interpretations(p):
    """청년 해석 후보 {이름: (소득한도, 자산한도, 자동차한도)}. 소득한도는 None일 수 있다(표에 없는 조합).

    - 무자녀 세대원: 소득은 1인 120% 고정(결정 로그 5번, 소득기준표에 세대원 1인 행만 존재).
    - 그 외: 원문 표 그대로(실제 가구원수 + 출생자녀 가산).
    - 2인 가구 + 자녀: 표에 행이 없어 '일반규칙 가산' 해석을 추가(대학생과 동일한 이유).
    - 세대원 + 자녀: 세대원 행이 세대주 행과 동일 수치로 재게재되어 있어 '표 그대로'와
      '세대원은 여전히 1인 120% 고정' 두 해석을 추가.
    자산·자동차는 세대주/세대원 구분 없이 실제 가구원수 기준(비대칭 유지).
    """
    size, child = p.household_size, _children_for_bonus(p, N3_ANNOUNCEMENT)
    one_person_limit = income_threshold(1, 120)

    if p.house_head_status == "세대원" and child <= 0:
        return {_TABLE_NAME: (one_person_limit, 251_000_000, 45_420_000)}

    def table_ratio(s, c):
        if s <= 1:
            return 120
        if s == 2:
            return 110
        return 100 if c <= 0 else 110 if c == 1 else 120

    def table_asset_car(s, c):
        if s <= 2 or c <= 0:
            return 251_000_000, 45_420_000
        return (276_000_000, 49_960_000) if c == 1 else (301_000_000, 54_510_000)

    asset, car = table_asset_car(size, child)
    options = {_TABLE_NAME: (income_threshold(size, table_ratio(size, child)), asset, car)}

    if size == 2 and child >= 1:
        bonus_ratio = 120 if child == 1 else 130
        bonus_asset, bonus_car = ((276_000_000, 49_960_000) if child == 1
                                  else (301_000_000, 54_510_000))
        options[_GENERAL_BONUS_NAME] = (income_threshold(2, bonus_ratio), bonus_asset, bonus_car)

    if p.house_head_status == "세대원" and child >= 1:
        options["세대원은 자녀가산과 무관하게 1인 120% 고정"] = (one_person_limit, asset, car)

    return options


def _youth_income_ok(p):
    if p.house_head_status is None:
        return None  # 세대주/세대원에 따라 적용 기준이 달라 확인 없이는 판단 불가
    if p.monthly_income is None:
        return None
    if p.household_size <= 1 and _children_for_bonus(p, N3_ANNOUNCEMENT) >= 1:
        return _no_table_row(p)
    limits = {name: income for name, (income, _a, _c) in _youth_interpretations(p).items()}
    if any(v is None for v in limits.values()):
        return None
    return resolve_interpretations(
        {name: p.monthly_income <= v for name, v in limits.items()},
        "청년 소득기준 해석 불일치")


def _youth_asset_ok(p):
    if p.total_assets is None:
        return None
    if p.household_size <= 1 and _children_for_bonus(p, N3_ANNOUNCEMENT) >= 1:
        return _no_table_row(p)
    limits = {name: asset for name, (_i, asset, _c) in _youth_interpretations(p).items()}
    return resolve_interpretations(
        {name: p.total_assets <= v for name, v in limits.items()},
        "청년 자산기준 해석 불일치")


def _youth_car_ok(p):
    if p.car_value == "확인불가":
        return None
    if p.household_size <= 1 and _children_for_bonus(p, N3_ANNOUNCEMENT) >= 1:
        return _no_table_row(p)
    limits = {name: car for name, (_i, _a, car) in _youth_interpretations(p).items()}
    return resolve_interpretations(
        {name: p.car_value <= v for name, v in limits.items()},
        "청년 자동차가액 기준 해석 불일치")


n3_youth_conditions = [
    RuleCondition("N3-R5", "home_ownership", True, "공고문 p.7 (무주택자로서)",
                  lambda p: p.home_ownership == "무주택",
                  note="무주택자인지"),
    RuleCondition("N3-R5b", "age_or_social_rookie", True, "공고문 p.7 ①-㉮/㉯",
                  _youth_age_or_rookie_ok,
                  note="19세 이상 39세 이하이거나, 사회초년생(소득활동기간 5년 이내 등)에 "
                       "해당하는지"),
    RuleCondition("N3-R6", "marital_status", True, "공고문 p.7 ②",
                  lambda p: p.marital_status == "미혼",
                  note="미혼인지"),
    RuleCondition("N3-R7/R7b", "household_income", True, "공고문 p.7 ③, p.8 소득기준표",
                  _youth_income_ok,
                  note="소득이 자녀수·세대주 여부에 따른 소득기준 이내인지"),
    RuleCondition("N3-R8", "total_assets", True, "공고문 p.7 ④",
                  _youth_asset_ok,
                  note="총자산이 자녀수에 따른 자산기준 이내인지"),
    RuleCondition("N3-R9", "car_value", True, "공고문 p.7 ④",
                  _youth_car_ok,
                  note="자동차가액이 자녀수에 따른 자동차기준 이내인지"),
    RuleCondition("N3-R10", "has_subscription_account", True, "공고문 p.7 ⑤",
                  lambda p: True,
                  note="[입주 전까지 이행] 청약통장 가입사실을 증명할 수 있는지"
                       "(신청 시점 미가입은 현재 자격에 영향 없음)"),
]

# N3 원문(p.9)은 N1과 달리 컷오프 날짜를 리터럴로 적지 않고 같은 문구("혼인기간 7년 이내 /
# 6세 이하 자녀")만 쓴다. N1의 리터럴(2019.7.29 / 2019.7.30)은 "혼인=공고일-7년, 6세이하=만 7세
# 미만=공고일-7년의 다음 날"이라는 일반 공식으로 정확히 재현되므로(tests 참조) N3에도 같은
# 공식을 적용한다. 남는 가정은 "N3가 N1과 같은 LH 표준 문구·만 나이 기준을 쓴다"는 것뿐이다.
N3_MARRIAGE_CUTOFF = marriage_cutoff(N3_ANNOUNCEMENT)
N3_CHILD_CUTOFF = young_child_cutoff(N3_ANNOUNCEMENT)

n3_married_conditions = _make_spouse_conditions(
    "N3-M", spouse_terms_married,
    "공고문 p.9 ③(+가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9 ⑤",
    "공고문 p.9 ①-㉮/㉯", {"혼인중", "예비신혼"},
    "혼인 중이거나 예비신혼부부인지", "married", N3_MARRIAGE_CUTOFF, N3_CHILD_CUTOFF, N3_ANNOUNCEMENT,
    "공고문 p.9 ② (컷오프 날짜는 원문에 리터럴이 없어 N1과 같은 공식으로 공고일에서 도출 — "
    "docs/rule-coverage-matrix.md §3)",
)
n3_singleparent_conditions = _make_spouse_conditions(
    "N3-S", spouse_terms_singleparent,
    "공고문 p.9 ③(+가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9 ⑤",
    "공고문 p.9 ①-㉰", {"한부모"},
    "한부모가족인지", "singleparent", N3_MARRIAGE_CUTOFF, N3_CHILD_CUTOFF, N3_ANNOUNCEMENT,
    "공고문 p.9 ①-㉰ (6세 컷오프는 원문에 리터럴이 없어 N1과 같은 공식으로 도출 — "
    "docs/rule-coverage-matrix.md §3)",
)

N3 = NoticeRuleSet(
    notice_id="N3", title="서울번동3 행복주택",
    announcement_date=N3_ANNOUNCEMENT,
    layers={
        "대학생": LayerRuleSet("대학생", n3_student_conditions),
        "청년": LayerRuleSet("청년", n3_youth_conditions),
        "신혼부부": LayerRuleSet("신혼부부", n3_married_conditions),
        "한부모": LayerRuleSet("한부모", n3_singleparent_conditions),
    },
)

ALL_NOTICES = {"N1": N1, "N2": N2, "N3": N3}
