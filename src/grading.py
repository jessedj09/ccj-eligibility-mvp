# -*- coding: utf-8 -*-
"""grading.py — 자동 판정 v3 ③: 공고·계층 등급과 사용자 단위 확정(docs/10 §2-3·§2-5).

    grades(d)                    → {계층: Grade(등급, 이유)}          — 초안(src/draft.py)의 계층마다
    judge(d, profile, layer)     → (엔진 결과(판정만 바꾼 복사본), [Check])

등급
- 자동 확정(AUTO): 그 계층의 모든 조건 근거를 원문에서 확인했고, 조항 장부의 미분류 문장·새 제한 문구가 그 계층에 걸리지 않음
- 일부 확인(PARTIAL): 확인하지 못한 조건(보류) 또는 걸리는 미분류 문장·제한 문구가 있음 — 판정은 하되 사용자 단위로 확정
- (검증됨은 등록 공고 — 초안이 아니므로 여기서 다루지 않는다. 판정 불가는 초안을 만들 수 없을 때 — draft.status != ok)

사용자 단위 확정: 확실하지 않은 것(보류 조건, 규칙이 모르는 문장)이 **그 사용자의 결론을 바꿀 수 있을 때만** 보류한다.
- 엔진이 '지원 가능'인데 확실하지 않은 것이 있으면 → 그것이 실제 조건이면 결론이 바뀔 수 있다 → 보류(원문 확인 N건)
- 엔진이 '지원 불가'인데 불충족 조건이 전부 보류 조건이면 → 보류(원문 확인)
- 그 밖(다른 확인된 조건으로 이미 지원 불가, 정보 부족 등) → 엔진 판정 그대로 확정
사용자에게는 어디를 확인할지(쪽·조건·문장)를 함께 준다.
"""
import dataclasses
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from rule_engine import evaluate

AUTO, PARTIAL = "auto", "partial"
GRADE_LABEL = {AUTO: "자동 확정", PARTIAL: "일부 확인"}


@dataclass(frozen=True)
class Check:
    kind: str            # held(원문에서 확인 못 한 조건) / unclassified(규칙에 없는 조건형 문장) / restriction(새 제한 문구)
    page: Optional[int]
    text: str            # 사용자에게 보일 한 줄


@dataclass(frozen=True)
class Grade:
    grade: str
    held: Tuple[str, ...]
    clauses: Tuple[Tuple[int, str], ...]


def _conditions(doc: Dict, layer: str):
    def walk(conds):
        for c in conds:
            yield c
            for t in c.get("tracks", []):
                yield from walk(t["conditions"])
    return list(walk(doc["layers"][layer]["conditions"]))


def layer_pages(doc: Dict) -> Dict[str, Tuple[int, int]]:
    """계층마다 조건 근거가 있는 쪽 범위(처음~끝)."""
    out = {}
    for layer in doc["layers"]:
        pages = [c.get("source", {}).get("page") for c in _conditions(doc, layer)]
        pages = [p for p in pages if isinstance(p, int)]
        if pages:
            out[layer] = (min(pages), max(pages))
    return out


def layer_clauses(d, layer: str) -> List[Tuple[int, str]]:
    """그 계층에 걸리는 미분류 문장 — 문장의 쪽이 그 계층 조건들의 쪽 범위 안이면 그 계층, 어느 계층 범위에도 없으면 모든 계층
    (어디에 붙는 조건인지 모르면 모두에 건다)."""
    ranges = layer_pages(d.doc)
    out = []
    for page, text in d.unclassified:
        inside = [lay for lay, (a, b) in ranges.items() if a <= page <= b]
        if layer in inside or not inside:
            out.append((page, text))
    return out


LAYER_FIELDS = ("layers", "weak", "extra_layers")


def layers_may_be_missing(d) -> bool:
    """계층 구성 빈칸(계층 목록·주거약자형·추가 계층)을 원문에서 확인하지 못했으면, 초안에 없는 계층이 실제로는 공급될 수 있다
    — 그 계층을 '해당 없음'으로 단정하지 않는다(2026-10-29: N5 주거약자형 계층 누락에서 발견)."""
    return any(h.split(".")[0] in LAYER_FIELDS for h in d.held_fields)


def offered(d, layer: str) -> Optional[bool]:
    """초안 기준으로 그 계층이 공급되는가 — True / False(해당 없음 확정) / None(모름: 판정 불가)."""
    if d.notice is not None and layer in d.notice.layers:
        return True
    return None if (d.notice is None or layers_may_be_missing(d)) else False


def grades(d) -> Dict[str, Grade]:
    if d.notice is None:
        return {}
    out = {}
    for layer in d.notice.layers:
        held = tuple(sorted(d.held_conditions.get(layer, set())))
        clauses = tuple(layer_clauses(d, layer)) + tuple((p, t) for p, t in d.restrictions)
        out[layer] = Grade(PARTIAL if held or clauses else AUTO, held, clauses)
    return out


def _held_check(d, layer: str, cid: str) -> Check:
    cond = next((c for c in _conditions(d.doc, layer) if c["id"] == cid), {})
    page = cond.get("source", {}).get("page")
    what = cond.get("note") or cid.split("-", 1)[-1]
    return Check("held", page, f"{'p.' + str(page) + ' ' if page else ''}{what} — 이 조건의 원문 문장을 자동으로 확인하지 못했습니다")


def checks_for(d, layer: str, held_ids) -> List[Check]:
    out = [_held_check(d, layer, cid) for cid in sorted(held_ids)]
    out += [Check("unclassified", p, f"p.{p} \"{t[:60]}{'…' if len(t) > 60 else ''}\" — 규칙에 없는 조건일 수 있습니다")
            for p, t in layer_clauses(d, layer)]
    out += [Check("restriction", p, f"p.{p} \"{t[:40]}\" — 규칙에 없는 지역·모집 제한 문구입니다") for p, t in d.restrictions]
    return out


def judge(d, profile, layer: str):
    """→ (엔진 결과 — 판정만 바꾼 복사본, 원문에서 확인할 곳). 결론이 갈리지 않는 사용자는 확인할 곳 없이 확정."""
    if d.notice is None:
        raise ValueError("판정할 수 있는 초안이 아닙니다")
    r = evaluate(profile, d.notice, layer)
    g = grades(d)[layer]
    if r.verdict == "ELIGIBLE" and (g.held or g.clauses):
        checks = checks_for(d, layer, g.held)
    elif r.verdict == "INELIGIBLE" and g.held and set(r.failed) <= set(g.held):
        checks = [_held_check(d, layer, cid) for cid in sorted(set(r.failed))]
    else:
        return r, []
    return dataclasses.replace(r, verdict="MANUAL_REVIEW"), checks
