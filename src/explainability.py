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

from dataclasses import dataclass, field
from typing import List, Optional

from rule_engine import EvaluationResult, NoticeRuleSet, RuleCondition


@dataclass
class ReasonItem:
    rule_id: str
    description: str   # RuleCondition.note
    source_ref: str     # RuleCondition.source_ref


@dataclass
class ReviewItem:
    rule_id: str
    description: str   # RuleCondition.note
    source_ref: str
    code: str          # AMBIGUOUS_SOURCE / SELF_REPORT_UNVERIFIED / INPUT_INCONSISTENT
    detail: str        # 어떤 해석들이 어떻게 갈렸는지 / 무엇이 검증되지 않았는지


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
    review: List[ReviewItem] = field(default_factory=list)


_HEADLINES = {
    # "신청 가능"이라는 확정적 표현 대신, 이 엔진이 확인한 범위 안에서만 충족했다는 점을
    # 명확히 한다 — 서류심사·경쟁 시 선정(추첨/배점)·미지원 세부요건은 이 결과에 포함되지 않는다.
    "ELIGIBLE": "현재 확인한 필수조건은 모두 충족했습니다.",
    "INELIGIBLE": "이 조건으로는 신청할 수 없습니다.",
    "NEEDS_INFO": "추가 정보를 입력하면 판정할 수 있습니다.",
    # 정보를 더 입력해도 해결되지 않는다 — 원문 해석이 갈리거나 자기신고 항목이라 사람이 확인해야 한다.
    "MANUAL_REVIEW": "자동으로 확정할 수 없는 조건이 있어 수동 확인이 필요합니다.",
}

SCOPE_CAVEAT = (
    "이 결과는 이 서비스가 확인한 필수조건에 한한 판정입니다. 서류심사·경쟁 시 선정(순위·추첨· "
    "배점) 결과나 최종 당첨을 보장하지 않으며, 사회초년생 세부요건 등 일부 항목은 자기신고 "
    "사실로만 처리됩니다. 최종 신청 전 반드시 LH 청약플러스 원문 공고문을 확인하세요."
)


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
    notes = list(result.notes)
    review_items = [
        ReviewItem(rule_id=rid, description=conditions_by_id[rid].note,
                   source_ref=conditions_by_id[rid].source_ref,
                   code=reason.code, detail=reason.detail)
        for rid, reason in result.review_reasons.items()
    ]
    if result.verdict == "ELIGIBLE":
        notes.append(SCOPE_CAVEAT)

    return Explanation(
        profile_id=result.profile_id, notice_id=result.notice_id, layer=result.layer,
        verdict=result.verdict, headline=headline, score=result.score,
        matched=_reason_items(result.matched, conditions_by_id),
        failed=_reason_items(result.failed, conditions_by_id),
        unknown=_reason_items(result.unknown, conditions_by_id),
        notes=notes, review=review_items,
    )
