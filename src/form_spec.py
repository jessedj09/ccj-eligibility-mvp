# -*- coding: utf-8 -*-
"""form_spec.py — 공고·계층 하나를 판정할 때 묻는 입력 양식(④-4). 판정 로직 없음.

    form_for(notice, layer) → {"fields": [...], "notes": [...], ...}   # 판정 API GET /form이 그대로 내려준다

화면(Next.js 공개 화면·Streamlit)은 이 정의대로 그리기만 한다 — 어떤 항목을 언제 묻는지는 여기 한 곳에 둔다.
- 늘 묻는 항목(나이·혼인·주택·가구원수·소득·자산·자동차·자녀 등) + **그 계층의 조건이 읽는 항목만**(계층 inputs).
- 항목 하나 = {name(HouseholdProfile 필드), label, type, options?, help?, section, show_if?, scope?}.
  type: age(생년월일 또는 만 나이 — 생년월일은 API가 공고일 기준으로 계산) / select / tri(예·아니오·모름) / bool / int /
  amount(원, 모름 가능) / car(원 또는 확인불가) / date / children(생년월일 목록) / region(지역 표준 이름).
  select·tri·region·amount의 '모름'은 null로 보낸다. show_if: {"field": 다른 항목, "in": [값…]} — 그 값일 때만 묻는다.
  scope: 이 계층에서 그 항목을 읽는 조건의 설명(같은 '주택 소유'라도 대학생은 본인, 신혼부부는 세대 전원).
"""
from typing import Dict, List

from rule_data import REGION_NONE, region_groups

UNKNOWN = "모름"
MARITAL = ["미혼", "혼인중", "예비신혼", "한부모"]
STUDENT = ["재학중", "입학예정", "복학예정", "취업준비생"]

HOUSEHOLD_HELP = ("신혼부부는 부부 2인 이상입니다. 예비신혼부부는 신청자 본인과 예비배우자, 공고일 기준 동일 세대에 등재된 "
                  "직계존속·비속을 포함한 '혼인으로 구성될 세대' 기준이며 2인 이상입니다. 한부모는 본인과 자녀를 포함합니다.")
CHILD_HELP = ("출생자녀 가산은 공고문 기준대로 자동 계산합니다: 2023.3.28. 이후 출생(입양·태아 포함) 자녀가 1명이라도 있으면 "
              "그 이전에 태어난 기존 미성년 자녀도 합산해 최대 2명, 이후 출생 자녀가 없으면 0명입니다. 가산 기준일 이후 출생 여부와 "
              "미성년 여부는 선택한 공고의 공고일로 판단합니다.")
SUBSCRIPTION_HELP = ("미가입이어도 대부분의 계층은 '입주 전까지'만 가입하면 되므로 현재 자격에는 영향이 없습니다"
                     "(우선공급 배점에는 영향 가능).")
REGION_HELP = ("이 공고는 순위 지역(서울특별시·연접 시 등)이 신청 자격을 가릅니다. 시·군 단위로 골라 주세요. '해당없음'은 그런 곳이 "
               "없다는 뜻입니다(예: 소득이 없어 소득 근거지가 없음, 대학생이 아님).")
EXTRA_HELP = "순위·유형마다 필요한 정보가 다릅니다. 모르는 항목은 '모름'으로 두면 그 순위는 '추가 정보 필요'로 표시됩니다."

REGION_LABELS = {
    "residence_area": "본인 거주지(주민등록상)",
    "school_area": "재학 중(또는 다음 학기 입·복학 예정)인 대학 캠퍼스 소재지",
    "income_base_area": "본인 소득 근거지(사업자등록증 소재지, 실제 근무지 증빙 시 근무지)",
    "spouse_residence_area": "배우자(예비신혼은 예비배우자) 거주지",
    "spouse_income_base_area": "배우자(예비신혼은 예비배우자) 소득 근거지",
    "workplace_area": "근무처(산업단지·경제자유구역) 소재지",
}
# 계층 전용 선택 항목(C3: 산업단지근로자·주거급여수급자·지역전략산업종사자·주거약자)
CHOICE_FIELDS = {
    "industrial_workplace": ("근무처 유형(입주예정 포함)",
                             ["산업단지 입주기업", "산업단지 교육·연구기관", "경제자유구역 입주 중소기업", "해당없음"]),
    "industrial_affiliation": ("그 근무처 소속 여부",
                               ["소속", "비소속 1년 이상 근무(예정)", "비소속 1년 미만"]),
    "housing_benefit_status": ("주거급여(「주거급여법」) 수급 여부", ["수급자", "수급권자", "해당없음"]),
    "regional_industry_type": ("지역전략산업종사자 유형(부천)",
                               ["콘텐츠산업 종사자", "전문예술법인·단체 종사자", "등록 예술인", "부천시 추천자", "해당없음"]),
    "housing_weak_type": ("주거약자 유형(신청자 본인) — 65세 이상은 나이로 판단",
                          ["장애인", "국가유공자(상이 1~7급)", "보훈보상대상자(상이 1~7급)", "5·18민주화운동부상자(장해 1~14급)",
                           "고엽제후유의증환자(경도 이상)", "국가유공자에 준하는 군경(상이 1~7급)", "해당없음"]),
}
REGIONAL_INDUSTRY_NOTE = "콘텐츠산업 종사자·부천시 추천자는 신청 후 부천시가 자격을 확인하므로 '수동 확인'으로 표시됩니다."
# C4(매입임대 등): 복지 자격·부모 정보·취업 여부 — 순위·유형 판정에 쓰는 항목
WELFARE_OPTIONS = ["생계·의료·주거급여 수급자", "교육급여만 수급", "차상위계층", "해당없음"]
C4_CHOICES = {
    "welfare_status": ("본인(가구) 복지 자격", WELFARE_OPTIONS),
    "parent_welfare_status": ("부모의 복지 자격", WELFARE_OPTIONS),
}
C4_BOOLS = {
    "is_supported_single_parent": "지원대상 한부모가족(본인 이름으로 한부모가족 증명서 발급 가능)",
    "registered_with_parents": "부모와 같은 주민등록표에 등재돼 있음",
    "is_employed": "현재 취업 중",
    "owned_home_in_5y": "신청자·배우자(예비배우자)가 공고일 기준 최근 5년 안에 주택을 소유한 적 있음",
    "disabled_spouse_qualifies": "배우자가 지적·정신장애인 또는 장애 정도가 심한 뇌병변장애인",
    "supports_elderly_parent_1y": "만 65세 이상 부모(배우자 부모 포함)를 같은 등본에서 1년 이상 부양 — 부모와 그 배우자도 무주택",
    "veteran_priority_notified": "국가보훈부로부터 장기전세 우선공급 대상자로 통보받음(국가유공자·유족 등)",
}
C4_AMOUNTS = {
    "parents_monthly_income": "부모 월평균소득 합계(원)",
    "parents_total_assets": "부모 총자산 합계(원)",
    "parents_car_value": "부모 보유 자동차 중 가장 높은 차량가액(원, 없으면 0)",
}
PARENTS_COUNT = ("소득·자산 검증대상 부모 수", [0, 1, 2])
# 엔진이 자녀 생년월일 목록(children_birth_dates)에서 계산하는 항목 — 따로 묻지 않는다
DERIVED = {"has_children": "children_birth_dates", "youngest_child_birth_date": "children_birth_dates"}

SCOPE_MAX_INPUTS = 3      # 입력란 아래 '이 계층 기준' 설명을 붙일 조건 — 읽는 항목이 이 수 이하인 조건만
BASIC, MONEY, REGION, LAYER_EXTRA, EXTRA ="기본", "소득·자산", "지역", "계층 요건", "추가 자격 정보"


def _f(name, label, type_, section, **kw) -> Dict:
    return dict(name=name, label=label, type=type_, section=section, **kw)


def region_options() -> List[str]:
    return [REGION_NONE] + [n for names in region_groups().values() for n in names]


def fields_for(inputs) -> List[Dict]:
    """계층이 읽는 항목(inputs)에 따라 묻는 항목 목록 — 순서는 화면에 보이는 순서."""
    out = [
        _f("age", "나이", "age", BASIC, help="생년월일로 넣으면 공고일 기준 만 나이로 계산합니다."),
        _f("marital_status", "혼인 상태", "select", BASIC, options=MARITAL, default="미혼"),
        _f("home_ownership", "주택 소유", "select", BASIC, options=["무주택", "주택보유"], default="무주택"),
        _f("household_size", "가구원수(판정 대상)", "int", BASIC, min=1, max=10, default=1, help=HOUSEHOLD_HELP),
        _f("dual_income", "맞벌이 여부", "bool", BASIC, default=False),
    ]
    if "house_head_status" in inputs:
        out.append(_f("house_head_status", "세대주/세대원 (등본 기준)", "select", BASIC, options=["세대주", "세대원"],
                      unknown=True))
    if "is_social_rookie" in inputs:
        out.append(_f("is_social_rookie", "사회초년생 해당 여부(19~39세가 아닐 때만 의미 있음)", "tri", BASIC))
    if "student_status" in inputs:
        out.append(_f("student_status", "재학 상태", "select", BASIC, options=STUDENT, unknown=True))
    if "grad_or_dropout_date" in inputs:
        kw = {"show_if": {"field": "student_status", "in": ["취업준비생"]}} if "student_status" in inputs else {}
        out.append(_f("grad_or_dropout_date", "대학·고등학교 졸업(또는 중퇴)일", "date", BASIC, **kw))
    if "marriage_date" in inputs:
        out.append(_f("marriage_date", "혼인신고일", "date", BASIC, nullable=True,
                      show_if={"field": "marital_status", "in": ["혼인중"]}))
    out.append(_f("children_birth_dates", "자녀(태아 포함) — 세대별 주민등록표에 등재된 미성년 자녀 생년월일", "children", BASIC,
                  help=CHILD_HELP, max=8))
    out += [
        _f("monthly_income", "월소득(원)", "amount", MONEY),
        _f("total_assets", "총자산(원)", "amount", MONEY),
        _f("car_value", "자동차가액(원)", "car", MONEY, default=0),
        _f("has_subscription_account", "청약통장 가입 여부(현재)", "bool", MONEY, default=False, help=SUBSCRIPTION_HELP),
    ]
    regions = [f for f in REGION_LABELS if f in inputs]
    for i, f in enumerate(regions):
        out.append(_f(f, REGION_LABELS[f], "region", REGION, unknown=True, **({"help": REGION_HELP} if i == 0 else {})))
    for f, (label, opts) in CHOICE_FIELDS.items():
        if f in inputs:
            kw = {"help": REGIONAL_INDUSTRY_NOTE} if f == "regional_industry_type" else {}
            out.append(_f(f, label, "select", LAYER_EXTRA, options=opts, unknown=True, **kw))
    extra = [f for f in list(C4_CHOICES) + list(C4_BOOLS) + ["parents_count"] + list(C4_AMOUNTS) if f in inputs]
    for i, f in enumerate(extra):
        kw = {"help": EXTRA_HELP} if i == 0 else {}
        if f in C4_CHOICES:
            out.append(_f(f, C4_CHOICES[f][0], "select", EXTRA, options=C4_CHOICES[f][1], unknown=True, **kw))
        elif f in C4_BOOLS:
            out.append(_f(f, C4_BOOLS[f], "tri", EXTRA, **kw))
        elif f == "parents_count":
            out.append(_f(f, PARENTS_COUNT[0], "select", EXTRA, options=PARENTS_COUNT[1], unknown=True, **kw))
        else:
            out.append(_f(f, C4_AMOUNTS[f], "amount", EXTRA, **kw))
    return out


def form_for(notice, layer: str) -> Dict:
    """공고(NoticeRuleSet — 등록 공고 또는 자동 분석 초안)·계층 하나의 입력 양식."""
    ls = notice.layers[layer]
    scope: Dict[str, List[str]] = {}
    for c in ls.conditions:
        if len(c.inputs) > SCOPE_MAX_INPUTS:      # 순위 묶음처럼 항목을 많이 읽는 조건 — 모든 입력란에 같은 설명이 반복되지 않게
            continue
        for name in c.inputs:
            if c.note not in scope.setdefault(name, []):
                scope[name].append(c.note)
    fields = fields_for(ls.inputs)
    for f in fields:
        if scope.get(f["name"]):
            f["scope"] = scope[f["name"]]
    return {"announcement_date": notice.announcement_date.isoformat(), "layer": layer,
            "notes": list(notice.meta.get("notes", [])), "sections": [BASIC, MONEY, REGION, LAYER_EXTRA, EXTRA],
            "section_titles": {LAYER_EXTRA: f"{layer} 요건"}, "region_options": region_options(),
            "region_groups": {g: list(names) for g, names in region_groups().items()}, "unknown": UNKNOWN,
            "fields": fields}
