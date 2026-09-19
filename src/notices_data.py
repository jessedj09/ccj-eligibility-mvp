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
    is_within_years, years_before,
)


def _car_ok(profile, limit):
    """car_value가 '확인불가'면 None, 숫자면 한도 비교."""
    if profile.car_value == "확인불가":
        return None
    return profile.car_value <= limit


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


def _make_student_conditions(prefix, marital_ref, home_ref, student_ref, income_ref,
                              asset_ref, car_ref, announcement_date):
    def student_check(p):
        return _student_status_ok(p, announcement_date)

    def income_check(p):
        ratio = _size_based_ratio(p.household_size, p.young_child_count)
        limit = income_threshold(p.household_size, ratio)
        return _income_le(p.monthly_income, limit)

    def asset_check(p):
        limit = _student_asset_limit(p.household_size, p.young_child_count)
        return _assets_le(p.total_assets, limit)

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


def _marriage_or_child_ok(p, marriage_cutoff, child_cutoff):
    """②(신혼부부 전용) 혼인기간 7년 이내 OR 6세 이하 자녀. 예비신혼부부는 이 요건 자체가 없다."""
    if p.marital_status == "예비신혼":
        return True
    duration_ok = None
    if p.marriage_date is not None:
        duration_ok = p.marriage_date >= marriage_cutoff
    child_ok = None
    if p.youngest_child_birth_date is not None:
        child_ok = p.youngest_child_birth_date >= child_cutoff
    if duration_ok or child_ok:
        return True
    if duration_ok is False and child_ok is False:
        return False
    return None  # 최소 한쪽이 미확인이고 나머지도 통과가 아님


def _child_under6_ok(p, child_cutoff):
    """①-㉰(한부모 전용) 6세 이하 자녀를 둔 자."""
    if p.youngest_child_birth_date is None:
        return None
    return p.youngest_child_birth_date >= child_cutoff


def _make_spouse_conditions(prefix, terms_func, income_ref, asset_ref, car_ref, sub_ref,
                             marital_field, marital_ok, marital_note, group,
                             marriage_cutoff, child_cutoff, duration_ref):
    def income_check(p):
        ratio, _asset, _car = terms_func(p)
        limit = income_threshold(p.household_size, ratio)
        return _income_le(p.monthly_income, limit)

    def asset_check(p):
        _ratio, asset, _car = terms_func(p)
        return _assets_le(p.total_assets, asset)

    def car_check(p):
        _ratio, _asset, car = terms_func(p)
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
    "혼인 중이거나 예비신혼부부인지", "married", N1_MARRIAGE_CUTOFF, N1_CHILD_CUTOFF,
    "공고문 p.5 ②",
)
n1_singleparent_conditions = _make_spouse_conditions(
    "N1-S", spouse_terms_singleparent,
    "공고문 p.5 ③(+p.6 자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ④(자녀가산표)", "공고문 p.6 ⑤",
    "공고문 p.4 ①-㉰", {"한부모"},
    "한부모가족인지", "singleparent", N1_MARRIAGE_CUTOFF, N1_CHILD_CUTOFF,
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
    """➀-㉮(19~39세) 또는 ➀-㉯(사회초년생, 자기신고).

    사회초년생의 세부요건(소득활동기간 5년 이내, 예술인 인증 등 3가지 경로)은
    이 엔진이 증빙을 검증하지 않는다 — is_social_rookie는 사용자 자기신고 사실로만 다룬다
    (docs/rule-coverage-matrix.md '지원 범위 밖' 참조).
    """
    age_ok = 19 <= p.age <= 39
    if age_ok:
        return True
    if p.is_social_rookie is True:
        return True
    if p.is_social_rookie is False:
        return False
    return None


def _youth_income_ratio_and_size(p):
    """소득판정에 적용할 (비율%, 가구원수) 쌍.

    무자녀 세대원은 기존 결정(docs/01-decisions-log.md 5번)대로 가구원수를 1로 고정한다.
    자녀가산이 있는 세대원의 가구원수 적용 방식은 원문 표(p.7)가 세대주 표와 동일한
    수치를 그대로 반복 게재하고 있어, 실제로 세대원도 가구원수를 그대로 쓰는지 표가
    단순 재게재(오탈자성)인지 원문만으로 확정할 수 없다 — 이 구현은 '표에 적힌 대로'
    실제 household_size를 사용하는 쪽을 택했다(docs/rule-coverage-matrix.md 확인 필요 항목).
    """
    if p.house_head_status == "세대원" and p.young_child_count <= 0:
        return 120, 1
    size = p.household_size
    child = p.young_child_count
    if size <= 1:
        return 120, size
    if size == 2:
        return 110, size
    if child <= 0:
        return 100, size
    if child == 1:
        return 110, size
    return 120, size


def _youth_asset_car_limits(p):
    """자산·자동차 한도는 세대주/세대원 구분 없이 실제 가구원수 기준(기존 비대칭 결정 유지)."""
    size, child = p.household_size, p.young_child_count
    if size <= 2 or child <= 0:
        return 251_000_000, 45_420_000
    if child == 1:
        return 276_000_000, 49_960_000
    return 301_000_000, 54_510_000


def _youth_income_ok(p):
    if p.house_head_status is None:
        return None  # 세대주/세대원에 따라 적용 기준이 달라 확인 없이는 판단 불가
    ratio, size = _youth_income_ratio_and_size(p)
    limit = income_threshold(size, ratio)
    return _income_le(p.monthly_income, limit)


def _youth_asset_ok(p):
    asset, _car = _youth_asset_car_limits(p)
    return _assets_le(p.total_assets, asset)


def _youth_car_ok(p):
    _asset, car = _youth_asset_car_limits(p)
    return _car_ok(p, car)


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

# N3 원문(p.9)은 N1과 달리 "혼인기간 7년/6세 이하"의 리터럴 컷오프 날짜를 명시하지 않는다.
# N1을 대조해보면 '6세 이하' 컷오프가 '혼인기간 7년' 컷오프보다 정확히 하루 늦다는 규칙성이
# 있었지만(2019.7.29 vs 2019.7.30), 이 하루 차이가 일반화 가능한 계산식인지 N1만의 우연인지
# 원문만으로는 확정할 수 없다. 이 구현은 두 컷오프를 모두 "공고일 - 7년"으로 근사한다
# (docs/rule-coverage-matrix.md 확인 필요 항목 — 실사용 전 LH 재확인 권장).
N3_MARRIAGE_CUTOFF = years_before(N3_ANNOUNCEMENT, 7)
N3_CHILD_CUTOFF = N3_MARRIAGE_CUTOFF

n3_married_conditions = _make_spouse_conditions(
    "N3-M", spouse_terms_married,
    "공고문 p.9 ③(+가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9 ⑤",
    "공고문 p.9 ①-㉮/㉯", {"혼인중", "예비신혼"},
    "혼인 중이거나 예비신혼부부인지", "married", N3_MARRIAGE_CUTOFF, N3_CHILD_CUTOFF,
    "공고문 p.9 ② (※ N1과 달리 7년/6세 기준일이 원문에 명시되어 있지 않아 "
    "공고일 기준 역산으로 근사함 — docs/rule-coverage-matrix.md 확인 필요)",
)
n3_singleparent_conditions = _make_spouse_conditions(
    "N3-S", spouse_terms_singleparent,
    "공고문 p.9 ③(+가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9-10 ④(가산표)", "공고문 p.9 ⑤",
    "공고문 p.9 ①-㉰", {"한부모"},
    "한부모가족인지", "singleparent", N3_MARRIAGE_CUTOFF, N3_CHILD_CUTOFF,
    "공고문 p.9 ①-㉰ (※ 6세 기준일이 원문에 명시되어 있지 않아 공고일 기준 역산으로 근사 — "
    "docs/rule-coverage-matrix.md 확인 필요)",
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
