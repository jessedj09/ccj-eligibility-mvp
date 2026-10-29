# -*- coding: utf-8 -*-
"""display_status.py — 엔진 판정(5상태)을 화면의 3상태(지원 가능 / 보류 / 지원 불가)로 보여 주는 대응표(PRD v2.1 F18).

엔진의 5상태는 바꾸지 않는다. '보류'는 원인마다 사용자가 할 일이 달라 원인을 함께 보인다.
"""
from dataclasses import dataclass
from typing import Optional

ELIGIBLE_GROUP, HOLD_GROUP, INELIGIBLE_GROUP, NOT_OFFERED_GROUP = "지원 가능", "보류", "지원 불가", "해당 없음"
GROUP_ICON = {ELIGIBLE_GROUP: "✅", HOLD_GROUP: "🟡", INELIGIBLE_GROUP: "❌", NOT_OFFERED_GROUP: "➖"}

CONTACT = "LH 1600-1004 / SH 1600-3456"   # 공고문에 적힌 임대 문의·ARS 번호


@dataclass(frozen=True)
class Display:
    group: str              # 지원 가능 / 보류 / 지원 불가 / 해당 없음
    icon: str               # 원인까지 구분한 아이콘
    cause: Optional[str]    # 보류 원인(보류일 때만)
    todo: str               # 사용자가 할 일

    @property
    def title(self) -> str:
        return self.group + (f" — {self.cause}" if self.cause else "")


DISPLAY = {
    "ELIGIBLE": Display(ELIGIBLE_GROUP, "✅", None,
                        "확인한 필수조건을 모두 충족했습니다. 순위·추첨·서류심사는 판정하지 않으니 신청 전 공고 원문을 확인하세요."),
    "INELIGIBLE": Display(INELIGIBLE_GROUP, "❌", None,
                          "충족하지 못한 조건이 하나라도 있으면 신청할 수 없습니다. 아래 근거를 확인하세요."),
    "NEEDS_INFO": Display(HOLD_GROUP, "⚠️", "추가 정보 필요",
                          "판정에 필요한 정보가 비어 있습니다. '추가로 입력하면 판정할 수 있는 조건'을 입력하면 판정됩니다."),
    "MANUAL_REVIEW": Display(HOLD_GROUP, "🔍", "수동 확인 필요",
                             "원문 해석이 갈리거나 자기신고로만 확인되는 조건이 있어 자동으로 확정하지 않았습니다. "
                             f"공고문 해당 쪽을 확인하거나 공고 기관({CONTACT})에 문의하세요."),
    "NOT_OFFERED": Display(NOT_OFFERED_GROUP, "➖", None, "이 공고에는 해당 계층의 공급이 없습니다."),
}


def display(verdict: str) -> Display:
    return DISPLAY[verdict]


# 모든 판정 결과에 붙는 공통 문구(PRD v3 5절 — '참고용 판정' 표현은 쓰지 않는다)
COMMON_NOTE = "판정 근거는 조건별로 표시한 공고문 원문입니다. 최종 자격은 공고 기관의 서류 심사로 확정됩니다."


def display_checks(n: int) -> Display:
    """자동 분석 공고에서 그 사용자의 결론이 확실하지 않은 곳에 따라 갈릴 때(v3 사용자 단위 확정, src/grading.py)."""
    return Display(HOLD_GROUP, "🔍", f"원문 확인 {n}건",
                   "다른 조건으로는 결론이 정해지지 않았습니다. 아래 표시한 곳만 공고문 원문에서 확인하면 결과가 확정됩니다.")
