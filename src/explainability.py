# -*- coding: utf-8 -*-
"""
Explainability Layer
=====================
역할: rule_engine.evaluate()가 만든 EvaluationResult(matched/failed/unknown rule_id
     리스트)를 사용자에게 보여줄 자연어 근거 문구로 변환한다.

이 파일은 verdict를 다시 계산하거나 새로운 판단을 추가하지 않는다 — evaluate()의
결과를 그대로 신뢰의 원천으로 삼아 텍스트로 옮기기만 하는 순수 프레젠테이션 계층이다
(CLAUDE.md 원칙 1의 연장: LLM은 물론 어떤 형태의 재판단도 여기 들어오지 않는다).
"""

from dataclasses import dataclass
from typing import List, Optional

from rule_engine import EvaluationResult, NoticeRuleSet, RuleCondition


@dataclass
class ReasonItem:
    rule_id: str
    description: str   # RuleCondition.note
    source_ref: str     # RuleCondition.source_ref


@dataclass
class Explanation:
    profile_id: str
    notice_id: str
    layer: str
    verdict: str
    headline: str
    score: Optional[float]
    matched: List[ReasonItem]
    failed: List[ReasonItem]
    unknown: List[ReasonItem]
    notes: List[str]


_HEADLINES = {
    "ELIGIBLE": "신청 가능합니다.",
    "INELIGIBLE": "이 조건으로는 신청할 수 없습니다.",
    "NEEDS_INFO": "추가 확인이 필요합니다.",
}


def _reason_items(rule_ids: List[str], conditions_by_id: dict) -> List[ReasonItem]:
    items = []
    for rule_id in rule_ids:
        cond: RuleCondition = conditions_by_id[rule_id]
        items.append(ReasonItem(rule_id=cond.rule_id, description=cond.note,
                                 source_ref=cond.source_ref))
    return items


def explain(result: EvaluationResult, notice: NoticeRuleSet) -> Explanation:
    if result.verdict == "NOT_OFFERED":
        return Explanation(
            profile_id=result.profile_id, notice_id=result.notice_id, layer=result.layer,
            verdict=result.verdict, headline=result.notes[0] if result.notes else "",
            score=result.score, matched=[], failed=[], unknown=[], notes=result.notes,
        )

    conditions_by_id = {c.rule_id: c for c in notice.layers[result.layer].conditions}

    headline = _HEADLINES[result.verdict]
    if result.verdict == "ELIGIBLE" and result.score is not None:
        headline = f"{headline} (충족도 {result.score}%)"

    return Explanation(
        profile_id=result.profile_id, notice_id=result.notice_id, layer=result.layer,
        verdict=result.verdict, headline=headline, score=result.score,
        matched=_reason_items(result.matched, conditions_by_id),
        failed=_reason_items(result.failed, conditions_by_id),
        unknown=_reason_items(result.unknown, conditions_by_id),
        notes=result.notes,
    )
