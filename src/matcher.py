# -*- coding: utf-8 -*-
"""
matcher.py — 한 번 받은 입력으로 전 공고·계층을 판정한다(D 단계).

같은 질문이라도 계층마다 뜻이 다르다(주택 소유: 대학생·청년은 본인, 신혼부부는 세대 전원 / 소득: 대학생은 본인+부모,
청년매입임대는 본인, 그 밖은 세대). 그래서 입력은 범위별로 따로 받고(`MasterProfile`), 계층마다
`rules/reference/input_scope.json`이 정한 범위로 `HouseholdProfile`을 만들어 기존 엔진(`evaluate`)으로 판정한다.
엔진·규칙 데이터는 바꾸지 않는다 — 이 모듈은 입력을 옮겨 담는 층이다.
"""

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any, Dict, List, Optional

from rule_data import RULES_DIR
from rule_engine import (EvaluationResult, HouseholdProfile, NoticeRuleSet, ReviewNeeded, combine_tracks,
                         evaluate)

VERDICT_ORDER = ("ELIGIBLE", "MANUAL_REVIEW", "NEEDS_INFO", "INELIGIBLE")


@dataclass
class MasterProfile:
    """전체 공고 판정용 입력. 범위가 갈리는 항목만 따로 받고 나머지는 HouseholdProfile 필드를 그대로 쓴다."""
    home_self: Optional[str] = None           # 본인 "무주택"/"주택보유"
    home_household: Optional[str] = None      # 세대(무주택세대구성원) 전원 기준 "무주택"/"주택보유"
    income_self: Optional[int] = None         # 본인 월평균소득
    income_household: Optional[int] = None    # 세대 전원 월평균소득 합계
    assets_self: Optional[int] = None
    assets_household: Optional[int] = None
    car_self: Any = None                      # 본인 자동차가액(없으면 0, "확인불가")
    car_household: Any = None                 # 세대 보유 자동차 중 가장 높은 차량가액
    birth_date: Optional[date] = None         # 있으면 공고마다 공고일 기준 만 나이를 계산해 age로 쓴다
    common: Dict[str, Any] = field(default_factory=dict)   # 그 밖의 HouseholdProfile 필드(age, marital_status, …)


@lru_cache(maxsize=None)
def _scope_rules() -> List[dict]:
    return json.loads((RULES_DIR / "reference" / "input_scope.json").read_text(encoding="utf-8"))["rules"]


def scope_for(notice: NoticeRuleSet, layer: str) -> dict:
    """공고·계층의 입력 범위 규칙(input_scope.json에서 처음 맞는 것)."""
    program = notice.meta.get("program", "행복주택")
    base = layer.split("(")[0]
    for rule in _scope_rules():
        if (rule["program"] == "*" or program.startswith(rule["program"])) and \
                (rule["layers"] == ["*"] or base in rule["layers"]):
            return rule
    raise ValueError(f"입력 범위 규칙 없음: {notice.notice_id}/{layer}")


def _home(m: MasterProfile) -> Dict[str, Optional[str]]:
    """본인·세대 답의 함의를 채운다: 세대 전원 무주택이면 본인도 무주택, 본인 보유면 세대도 보유."""
    self_, house = m.home_self, m.home_household
    if self_ is None and house == "무주택":
        self_ = "무주택"
    if house is None and self_ == "주택보유":
        house = "주택보유"
    return {"self": self_, "household": house}


def _single_person(m: MasterProfile) -> bool:
    return m.common.get("household_size") == 1


def scoped_profile(m: MasterProfile, notice: NoticeRuleSet, layer: str, scope: Optional[dict] = None) -> HouseholdProfile:
    """MasterProfile → 이 계층의 뜻에 맞춘 HouseholdProfile."""
    scope = scope or scope_for(notice, layer)
    kw = dict(m.common)
    kw.setdefault("profile_id", "master")
    if m.birth_date is not None:         # 나이는 공고일 기준 만 나이 — 공고마다 다르다
        ann, b = notice.announcement_date, m.birth_date
        kw["age"] = ann.year - b.year - ((ann.month, ann.day) < (b.month, b.day))
    kw.setdefault("age", 0)
    kw.setdefault("marital_status", "미혼")
    home = _home(m)
    hs = scope["home"]
    if hs == "self_if_unmarried":
        hs = "household" if kw.get("marital_status") == "혼인중" else "self"
    kw["home_ownership"] = home[hs]

    single = _single_person(m)
    own = dict(income=m.income_self, assets=m.assets_self, car=m.car_self)
    house = dict(income=m.income_household, assets=m.assets_household, car=m.car_household)
    if single:   # 1인 가구면 본인 = 세대
        for k in own:
            if own[k] is None:
                own[k] = house[k]
            if house[k] is None:
                house[k] = own[k]
    s = scope["income"]
    if s == "household":
        pick = house
    elif s == "self":
        pick = own
    elif s == "youth_head":
        head = kw.get("house_head_status")
        pick = house if head == "세대주" else own if head == "세대원" else dict(income=None, assets=None, car=None)
    elif s == "self_plus_parents":
        parents = kw.get("parents_monthly_income")
        income = None if m.income_self is None or parents is None else m.income_self + parents
        pick = dict(income=income, assets=m.assets_self, car=m.car_self)
        pc = kw.get("parents_count")
        kids = kw.get("children_birth_dates") or []
        kw["household_size"] = None if pc is None else 1 + pc + len(kids)
    else:
        raise ValueError(f"알 수 없는 소득 범위: {s}")
    kw["monthly_income"], kw["total_assets"] = pick["income"], pick["assets"]
    kw["car_value"] = "확인불가" if pick["car"] is None else pick["car"]
    # 가구원수를 모르면 None 그대로 둔다 — 결정표 입력이 비면 엔진은 '정보 부족'으로 처리한다(0을 넣으면 '표에 없는 조합'이 된다)
    return HouseholdProfile(**kw)


def _verdict(failed, review, unknown) -> str:
    return "INELIGIBLE" if failed else "MANUAL_REVIEW" if review else "NEEDS_INFO" if unknown else "ELIGIBLE"


def evaluate_layer(m: MasterProfile, notice: NoticeRuleSet, layer: str) -> EvaluationResult:
    """한 계층 판정. 트랙이 다른 계층 이름(예: 부천 '주거약자' = 지역전략·청년·대학생 중 하나)이면 트랙마다 그 계층의 범위로 판정해 합친다."""
    ruleset = notice.layers[layer]
    group = next((c for c in ruleset.conditions if c.tracks
                  and all(t.track_id in notice.layers for t in c.tracks)), None)
    base = evaluate(scoped_profile(m, notice, layer), notice, layer)
    if group is None:
        return base
    subs = {}
    for t in group.tracks:
        r = evaluate(scoped_profile(m, notice, layer, scope_for(notice, t.track_id)), notice, layer)
        subs[t.track_id] = r.tracks[t.track_id]
    value = combine_tracks(subs)
    lists = {k: [x for x in getattr(base, k) if x != group.rule_id] for k in ("matched", "failed", "unknown", "review")}
    reasons = {k: v for k, v in base.review_reasons.items() if k != group.rule_id}
    if value is True:
        lists["matched"].append(group.rule_id)
    elif value is False:
        lists["failed"].append(group.rule_id)
    elif isinstance(value, ReviewNeeded):
        lists["review"].append(group.rule_id)
        reasons[group.rule_id] = value
    else:
        lists["unknown"].append(group.rule_id)
    return dataclasses.replace(base, verdict=_verdict(lists["failed"], lists["review"], lists["unknown"]),
                               review_reasons=reasons, tracks=subs, **lists)


@dataclass
class Match:
    notice: NoticeRuleSet
    layer: str
    result: EvaluationResult

    @property
    def verdict(self) -> str:
        return self.result.verdict


def match_all(m: MasterProfile, notices: Dict[str, NoticeRuleSet]) -> List[Match]:
    """모든 공고 × 모든 (구현된) 계층의 판정. 판정 순서(충족 → 수동 확인 → 정보 부족 → 불충족), 공고일 늦은 순으로 정렬."""
    out = [Match(n, layer, evaluate_layer(m, n, layer)) for n in notices.values() for layer in n.layers]
    return sorted(out, key=lambda x: (VERDICT_ORDER.index(x.verdict), -x.notice.announcement_date.toordinal(),
                                      x.notice.notice_id, x.layer))


# 정보 부족 조건이 읽는 프로필 필드 → 사용자에게 물을 항목 이름
FIELD_LABELS = {
    "monthly_income": "소득", "total_assets": "총자산", "car_value": "자동차가액", "home_ownership": "주택 소유",
    "household_size": "가구원수", "age": "나이", "marital_status": "혼인 상태", "marriage_date": "혼인신고일",
    "has_children": "자녀 유무", "youngest_child_birth_date": "자녀 생년월일", "children_birth_dates": "자녀 생년월일",
    "dual_income": "맞벌이 여부", "house_head_status": "세대주/세대원", "is_social_rookie": "사회초년생 여부",
    "student_status": "재학 상태", "grad_or_dropout_date": "졸업·중퇴일", "residence_area": "거주지",
    "school_area": "대학 소재지", "income_base_area": "소득 근거지", "spouse_residence_area": "배우자 거주지",
    "spouse_income_base_area": "배우자 소득 근거지", "workplace_area": "근무처 소재지",
    "industrial_workplace": "산업단지 근무처 유형", "industrial_affiliation": "근무처 소속 여부",
    "housing_benefit_status": "주거급여 수급", "regional_industry_type": "지역전략산업 종사 유형",
    "welfare_status": "복지 자격", "parent_welfare_status": "부모 복지 자격", "registered_with_parents": "부모와 동일 등재",
    "is_supported_single_parent": "지원대상 한부모", "is_employed": "취업 여부", "parents_count": "부모 수",
    "parents_monthly_income": "부모 소득", "parents_total_assets": "부모 자산", "parents_car_value": "부모 자동차",
    "housing_weak_type": "주거약자 유형", "owned_home_in_5y": "최근 5년 주택 소유",
    "disabled_spouse_qualifies": "배우자 장애", "supports_elderly_parent_1y": "노부모 부양",
    "veteran_priority_notified": "국가보훈부 우선공급 통보",
}


def missing_inputs(matches: List[Match]) -> Dict[str, int]:
    """'추가 정보 필요' 판정에서 정보 부족 조건이 읽는 항목별로, 그 항목 때문에 판정이 멈춘 공고·계층 수."""
    counts: Dict[str, int] = {}
    for x in matches:
        if x.verdict != "NEEDS_INFO":
            continue
        conds = {c.rule_id: c for c in _all_conditions(x.notice.layers[x.layer].conditions)}
        labels = set()
        unknown_ids = list(x.result.unknown)
        if not x.result.eligible_tracks:      # 충족한 트랙이 있으면 다른 트랙의 미입력은 판정을 막지 않는다
            for sub in x.result.tracks.values():
                unknown_ids += sub.unknown
        for rid in unknown_ids:
            c = conds.get(rid)
            if c is None:
                continue
            for f in c.inputs:
                labels.add(FIELD_LABELS.get(f, f))
        for label in labels:
            counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _all_conditions(conditions):
    for c in conditions:
        yield c
        for t in c.tracks or []:
            yield from _all_conditions(t.conditions)
