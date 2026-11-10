# -*- coding: utf-8 -*-
"""live_judge.py — 공고문 분석 전인 수집 공고의 예비 판정(흥신소 주 흐름, docs/12 '2단계 재설계').

같은 기관·같은 판정 틀의 앞선 등록 공고(대표 공고) 규칙으로 판정하고, 결과를 예비 판정으로 바꾼다.

    LIKELY    가능성 있음 — 대표 공고 기준 지원 가능. 화면 표시 '지원 가능 (단, 공고문 내 지원자격 상세 확인 필요)'(2026-11-11 사용자 결정, src/find.py).
    CHECK     확인 필요 — 대표 공고 기준 보류, 또는 공고마다 다를 수 있는 조건으로 걸림
    UNLIKELY  어려움 — 같은 사업 등록 공고 모두에 같은 식으로 있는 조건으로만 걸림(숨기지 않고 접어서 보인다)
    NONE      판정하지 않음 — 대표 공고에 그 계층이 없음

'어려움'의 기준(2026-11-10 되짚어 보기 `tools/eval_preview.py`로 정함):
- 걸린 조건마다 **같은 판정 틀의 등록 공고 모두**에서 그 계층에 같은 field 조건이 있어야 한다(공통 조건 — `CommonIndex`).
  신혼희망타운의 '만 19세 이상'·소득 조건, 공공임대의 재당첨 제한처럼 공고 유형에 따라 있기도 없기도 한 조건은 '확인 필요'.
- 금액이 아닌 조건은 식(check)까지 모든 공고에서 같아야 한다(다자녀 3명 → 2명처럼 기준이 바뀐 조건은 '확인 필요').
- 금액 한도(소득·자산·자동차)는 같은 해에도 공고마다 다르다 — 금액을 MONEY_MARGIN 배로 줄여도 걸릴 때만.
- 대표 공고가 STALE_DAYS 넘게 앞서면 '어려움'을 쓰지 않는다(그사이 법령·지침 개정 — 2024.3. 나눔형·선택형 개정).

판정 엔진·규칙은 바꾸지 않는다 — 이 모듈은 대표 공고를 고르고 결과를 옮겨 담는다.
"""
import json
from collections import defaultdict
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Dict, Iterable, List, Optional, Set, Tuple

from rule_data import RULES_DIR
from rule_engine import EvaluationResult, HouseholdProfile, NoticeRuleSet, evaluate

LIKELY, CHECK, UNLIKELY, NONE = "likely", "check", "unlikely", "none"
ORDER = (LIKELY, CHECK, UNLIKELY, NONE)

MONEY_FIELDS = frozenset({
    "total_assets", "car_value", "monthly_income", "household_income", "income(본인+부모)", "monthly_income/dual_income",
    "real_estate_value", "parents_total_assets",
})
MONEY_ATTRS = ("monthly_income", "total_assets", "car_value", "parents_monthly_income", "parents_total_assets",
               "parents_car_value", "real_estate_value")
MONEY_MARGIN = 0.7          # 한도가 대표 공고보다 43% 높은 공고여도 걸리는 경우만
STALE_DAYS = 365
# 공고마다 기준이 달라도 이상하지 않은 조건 — 공통 조건이어도 '확인 필요'(거주 지역·청약통장·우선공급·근무 등)
VARIABLE_FIELDS = frozenset({
    "residence_area", "has_subscription_account", "has_subscription_account/subscription_months/subscription_payment_count",
    "subscription_deposit", "rewin_restricted", "past_special_supply", "household_won_5y", "house_head_status",
    "job_criterion_met", "regional_industry_type", "industrial_workplace", "industrial_affiliation", "workplace_area",
    "supports_elderly_parent_1y", "supports_elderly_parent_3y", "veteran_priority_notified",
})


@dataclass(frozen=True)
class Registered:
    """대표 공고 후보(등록 공고) — 판정 틀·기관·사업 이름·공고일."""
    notice_id: str
    template: str
    issuer: str
    program: str
    announcement_date: date


@dataclass
class LayerPreview:
    layer: str
    outcome: str
    verdict: Optional[str] = None            # 대표 공고 기준 엔진 판정
    reasons: List[str] = field(default_factory=list)   # 걸린 조건 note(어려움·확인 필요의 이유)
    fields: List[str] = field(default_factory=list)
    result: Optional[EvaluationResult] = None          # 대표 공고 기준 엔진 결과(추가 질문 집계용)


def base_layer(layer: str) -> str:
    return layer.split("(")[0].strip()


def _raw(nid: str) -> Dict:
    return json.loads((RULES_DIR / "notices" / f"{nid}.json").read_text(encoding="utf-8"))


def _walk_raw(conds, out: Dict[str, Tuple[str, str, bool]]):
    """rule_id → (field, 식 문자열, 묶음 머리인가)."""
    for c in conds:
        out[c["id"]] = (c.get("field") or "", json.dumps(c.get("check"), ensure_ascii=False, sort_keys=True),
                        bool(c.get("tracks")))
        for t in c.get("tracks") or []:
            _walk_raw(t.get("conditions", []), out)


class CommonIndex:
    """판정 틀·계층(기본 이름)마다 등록 공고 모두에 있는 조건 field와 그 식들."""

    def __init__(self, members: Iterable[Registered]):
        self._raw: Dict[str, Dict[str, Dict[str, Tuple[str, str, bool]]]] = {}
        groups: Dict[Tuple[str, str], List[Dict[str, Tuple[str, str, bool]]]] = defaultdict(list)
        for r in members:
            doc = _raw(r.notice_id)
            per = {}
            for layer, body in doc["layers"].items():
                idx: Dict[str, Tuple[str, str, bool]] = {}
                _walk_raw(body.get("conditions", []), idx)
                per[layer] = idx
                groups[(r.template, base_layer(layer))].append(idx)
            self._raw[r.notice_id] = per
        self._common: Dict[Tuple[str, str], Dict[str, Set[str]]] = {}
        for key, idxs in groups.items():
            fields = None
            checks: Dict[str, Set[str]] = defaultdict(set)
            for idx in idxs:
                fs = {f for f, _c, grp in idx.values() if f and not grp}
                fields = fs if fields is None else fields & fs
                for f, c, grp in idx.values():
                    if f and not grp:
                        checks[f].add(c)
            self._common[key] = {f: checks[f] for f in (fields or set())}

    def conditions(self, nid: str, layer: str) -> Dict[str, Tuple[str, str, bool]]:
        return self._raw.get(nid, {}).get(layer, {})

    def common(self, template: str, layer: str) -> Dict[str, Set[str]]:
        return self._common.get((template, base_layer(layer)), {})


def pick_representative(template: str, issuer: str, program: Optional[str], announced: Optional[date],
                        candidates: Iterable[Registered]) -> Optional[Registered]:
    """같은 판정 틀·같은 기관 중 사업 이름이 같은 것을 먼저, 그 안에서 공고일이 가장 가까운 앞선 공고(없으면 가장 최근 공고)."""
    pool = [c for c in candidates if c.template == template and c.issuer == issuer]
    if not pool:
        return None
    same = [c for c in pool if program and c.program == program]
    pool = same or pool
    if announced is not None:
        before = [c for c in pool if c.announcement_date < announced]
        if before:
            return max(before, key=lambda c: (c.announcement_date, c.notice_id))
    return max(pool, key=lambda c: (c.announcement_date, c.notice_id))


def match_layer(layer: str, notice: NoticeRuleSet) -> Optional[str]:
    """대표 공고에서 같은 계층(이름이 같으면 그것, 아니면 괄호 앞 기본 이름이 같은 첫 계층)."""
    if layer in notice.layers:
        return layer
    base = base_layer(layer)
    return next((x for x in notice.layers if base_layer(x) == base), None)


def _failed(result: EvaluationResult) -> List[str]:
    """지원 불가를 만든 조건 rule_id — 묶음이면 그 안 트랙들이 걸린 조건까지 내려간다."""
    ids = list(result.failed)
    for t in result.tracks.values():
        if t.verdict == "INELIGIBLE":
            ids += _failed(t)
    return ids


def _judge_failed(result: EvaluationResult, conds: Dict[str, Tuple[str, str, bool]], common: Dict[str, Set[str]]):
    """→ (field 목록, 모두 '어려움'으로 볼 수 있는가, 금액 조건이 있는가)."""
    fields, solid, money = [], True, False
    for rid in _failed(result):
        f, check, group = conds.get(rid, ("", "", False))
        if group:                   # 묶음 머리(유형·순위) — 트랙 안 조건이 따로 들어온다
            continue
        fields.append(f)
        if not f or f in VARIABLE_FIELDS or f not in common:
            solid = False
        elif f in MONEY_FIELDS:
            money = True
        elif common[f] != {check}:  # 공고마다 식이 다름(기준 변경)
            solid = False
    return fields, solid and bool(fields), money


def _scaled(profile: HouseholdProfile) -> HouseholdProfile:
    kw = {a: int(getattr(profile, a) * MONEY_MARGIN) for a in MONEY_ATTRS
          if isinstance(getattr(profile, a, None), int) and not isinstance(getattr(profile, a), bool)}
    return replace(profile, **kw)


def preview_layer(profile: HouseholdProfile, layer: str, rep: NoticeRuleSet, rep_template: str, index: CommonIndex,
                  announced: Optional[date]) -> LayerPreview:
    """수집 공고의 한 계층을 대표 공고 rep로 예비 판정. 공고일 기준 계산(혼인 기간·자녀 나이·졸업 경과)은 수집 공고의 공고일로."""
    rl = match_layer(layer, rep)
    if rl is None:
        return LayerPreview(layer, NONE)
    stale = (announced is not None and rep.announcement_date is not None
             and (announced - rep.announcement_date).days > STALE_DAYS)
    if announced is not None:
        rep = replace(rep, announcement_date=announced)
    r = evaluate(profile, rep, rl)
    v = r.verdict
    if v == "ELIGIBLE":
        return LayerPreview(layer, LIKELY, v, result=r)
    if v != "INELIGIBLE":
        return LayerPreview(layer, CHECK if v in ("NEEDS_INFO", "MANUAL_REVIEW") else NONE, v, result=r)
    conds, common = index.conditions(rep.notice_id, rl), index.common(rep_template, rl)
    fields, solid, money = _judge_failed(r, conds, common)
    if solid and money:
        # 금액 한도로 걸림 — 금액을 줄여서도 걸리고 그때 걸린 조건도 모두 '어려움' 조건이어야
        r2 = evaluate(_scaled(profile), rep, rl)
        solid = r2.verdict == "INELIGIBLE" and _judge_failed(r2, conds, common)[1]
    reasons = [conds_note for conds_note in _notes(rep, rl, _failed(r))]
    return LayerPreview(layer, UNLIKELY if solid and not stale else CHECK, v, reasons, fields, r)


def _notes(notice: NoticeRuleSet, layer: str, ids: List[str]) -> List[str]:
    want, out = set(ids), []

    def walk(conds):
        for c in conds:
            if c.rule_id in want and c.note and not c.tracks:
                out.append(c.note)
            for t in c.tracks or []:
                walk(t.conditions)
    walk(notice.layers[layer].conditions)
    return out


def summary(layers: Iterable[LayerPreview]) -> str:
    """공고 카드의 요약 — 계층 중 가장 좋은 결과."""
    got = {x.outcome for x in layers}
    return next((o for o in ORDER if o in got), NONE)
