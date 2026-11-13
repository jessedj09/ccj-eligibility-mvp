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


def _group_sigs(conds) -> Dict[str, Tuple[str, Tuple[str, ...]]]:
    """순위·유형 묶음(최상위 조건 중 tracks가 있는 것) rule_id → (field, 트랙 ID 목록) — 묶음 구성이 공고마다 같은지 보려고."""
    return {c["id"]: (c.get("field") or "", tuple(str(t.get("id")) for t in c["tracks"])) for c in conds if c.get("tracks")}


class CommonIndex:
    """판정 틀·계층(기본 이름)마다 등록 공고 모두에 있는 조건 field와 그 식들, 모든 공고에 같은 구성으로 있는 순위·유형 묶음."""

    def __init__(self, members: Iterable[Registered]):
        self._raw: Dict[str, Dict[str, Dict[str, Tuple[str, str, bool]]]] = {}
        self._raw_groups: Dict[str, Dict[str, Dict[str, Tuple[str, Tuple[str, ...]]]]] = {}
        groups: Dict[Tuple[str, str], List[Dict[str, Tuple[str, str, bool]]]] = defaultdict(list)
        sigs: Dict[Tuple[str, str], List[set]] = defaultdict(list)
        self._members: Dict[str, List[str]] = defaultdict(list)
        for r in members:
            self._members[r.template].append(r.notice_id)
            doc = _raw(r.notice_id)
            per, per_g = {}, {}
            for layer, body in doc["layers"].items():
                idx: Dict[str, Tuple[str, str, bool]] = {}
                _walk_raw(body.get("conditions", []), idx)
                per[layer] = idx
                per_g[layer] = _group_sigs(body.get("conditions", []))
                groups[(r.template, base_layer(layer))].append(idx)
                sigs[(r.template, base_layer(layer))].append(set(per_g[layer].values()))
            self._raw[r.notice_id] = per
            self._raw_groups[r.notice_id] = per_g
        self._common_groups = {k: set.intersection(*v) for k, v in sigs.items()}
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

    def group_sig(self, nid: str, layer: str, rule_id: str) -> Optional[Tuple[str, Tuple[str, ...]]]:
        return self._raw_groups.get(nid, {}).get(layer, {}).get(rule_id)

    def members(self, template: str) -> List[str]:
        return list(self._members.get(template, []))

    def common_groups(self, template: str, layer: str) -> set:
        return self._common_groups.get((template, base_layer(layer)), set())


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


def _solid_kind(rid: str, conds: Dict[str, Tuple[str, str, bool]], common: Dict[str, Set[str]]) -> Optional[str]:
    """조건 하나가 '어려움' 근거가 되는가 → "stable"(모든 공고에 같은 식) / "money"(모든 공고에 있는 금액 — 여유 폭 검사 필요) / None."""
    f, check, group = conds.get(rid, ("", "", False))
    if group or not f or f in VARIABLE_FIELDS or f not in common:
        return None
    if f in MONEY_FIELDS:
        return "money"
    return "stable" if common[f] == {check} else None


def _top_level_solid(result: EvaluationResult, profile: HouseholdProfile, rep: NoticeRuleSet, layer: str,
                     conds: Dict[str, Tuple[str, str, bool]], common: Dict[str, Set[str]]) -> bool:
    """필수 조건(순위·유형 묶음 밖) 중 하나라도 '어려움' 근거 조건에 걸리면 다른 조건과 상관없이 어렵다(2026-11-14 묶음 B):
    그 조건은 같은 판정 틀의 모든 공고에 같은 식으로 있으므로 이 공고에도 있고, 묶음 밖 조건은 하나만 걸려도 지원 불가다.
    금액 조건은 금액을 MONEY_MARGIN 배로 줄여도 그 조건에 걸릴 때만. 묶음(트랙) 안 조건은 다른 순위로 통과할 수 있어 여기서 보지 않는다."""
    kinds = {rid: _solid_kind(rid, conds, common) for rid in result.failed}
    if any(k == "stable" for k in kinds.values()):
        return True
    money = [rid for rid, k in kinds.items() if k == "money"]
    if not money:
        return False
    r2 = evaluate(_scaled(profile), rep, layer)
    return any(rid in r2.failed for rid in money)


def _group_solid(result: EvaluationResult, profile: HouseholdProfile, rep: NoticeRuleSet, layer: str,
                 conds: Dict[str, Tuple[str, str, bool]], common: Dict[str, Set[str]], index: "CommonIndex", template: str) -> bool:
    """순위·유형 묶음에서 모두 떨어진 경우(2026-11-14 묶음 B — 영구임대 1순위 신분 '가~타'): 묶음 구성이 같은 틀의 모든 공고에서 같고,
    모든 순위가 '어려움' 근거 조건(모든 공고에 같은 식 — 금액은 여유 폭을 줘도)으로 떨어질 때만."""
    r2 = None
    for rid in result.failed:
        sig = index.group_sig(rep.notice_id, layer, rid)
        if sig is None or sig not in index.common_groups(template, layer):
            continue
        ok = True
        for tid in sig[1]:
            tr = result.tracks.get(tid)
            if tr is None or tr.verdict != "INELIGIBLE":
                ok = False
                break
            kinds = {x: _solid_kind(x, conds, common) for x in tr.failed}
            if any(k == "stable" for k in kinds.values()):
                continue
            money = [x for x, k in kinds.items() if k == "money"]
            if not money:
                ok = False
                break
            if r2 is None:
                r2 = evaluate(_scaled(profile), rep, layer)
            t2 = r2.tracks.get(tid)
            if t2 is None or not any(x in t2.failed for x in money):
                ok = False
                break
        if ok:
            return True
    return False


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
        extra = _sibling_extra(profile, layer, rep, rl, rep_template, index)
        if extra:     # 같은 사업 다른 공고에만 있는 조건에 걸림 — '지원 가능(단서)' 대신 '실제 공고문 확인필요'
            return LayerPreview(layer, CHECK, "INELIGIBLE", [SIBLING_NOTE.format(", ".join(extra))], extra, r)
        return LayerPreview(layer, LIKELY, v, result=r)
    if v != "INELIGIBLE":
        return LayerPreview(layer, CHECK if v in ("NEEDS_INFO", "MANUAL_REVIEW") else NONE, v, result=r)
    conds, common = index.conditions(rep.notice_id, rl), index.common(rep_template, rl)
    fields, solid, money = _judge_failed(r, conds, common)
    if solid and money:
        # 금액 한도로 걸림 — 금액을 줄여서도 걸리고 그때 걸린 조건도 모두 '어려움' 조건이어야
        r2 = evaluate(_scaled(profile), rep, rl)
        solid = r2.verdict == "INELIGIBLE" and _judge_failed(r2, conds, common)[1]
    if not solid:
        solid = _top_level_solid(r, profile, rep, rl, conds, common)
    if not solid:
        solid = _group_solid(r, profile, rep, rl, conds, common, index, rep_template)
    reasons = [conds_note for conds_note in _notes(rep, rl, _failed(r))]
    return LayerPreview(layer, UNLIKELY if solid and not stale else CHECK, v, reasons, fields, r)


SIBLING_NOTE = "같은 사업의 다른 공고에는 이 조건으로 지원할 수 없는 기준이 있습니다({}) — 이 공고문에서 확인하세요"
_SIBLINGS: Dict[str, NoticeRuleSet] = {}


def _sibling_extra(profile: HouseholdProfile, layer: str, rep: NoticeRuleSet, rl: str, template: str,
                   index: CommonIndex) -> List[str]:
    """대표 공고 기준 지원 가능일 때, 같은 판정 틀의 다른 등록 공고에서 대표 공고에 없는 조건(field)으로 떨어지면 그 field들(2026-11-14 묶음 B —
    신혼희망타운 하위 유형마다 소득·나이 조건 유무가 달라 생기던 헛걸음). 공고일 기준 계산은 수집 공고 날짜(rep에 이미 반영)로."""
    from rule_data import load_notice
    rep_fields = {f for f, _c, g in index.conditions(rep.notice_id, rl).values() if f and not g}
    out: List[str] = []
    for nid in index.members(template):
        if nid == rep.notice_id:
            continue
        sib = _SIBLINGS.get(nid) or _SIBLINGS.setdefault(nid, load_notice(nid))
        sl = match_layer(layer, sib)
        if sl is None:
            continue
        rs = evaluate(profile, replace(sib, announcement_date=rep.announcement_date), sl)
        if rs.verdict != "INELIGIBLE":
            continue
        conds = index.conditions(nid, sl)
        for rid in _failed(rs):
            f, _c, g = conds.get(rid, ("", "", False))
            if f and not g and f not in rep_fields and f not in out:
                out.append(f)
    return out


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
