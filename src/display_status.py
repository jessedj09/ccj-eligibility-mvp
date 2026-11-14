# -*- coding: utf-8 -*-
"""display_status.py — 엔진 판정(5상태)을 화면의 3상태(지원 가능 / 보류 / 지원 불가)로 보여 주는 대응표(PRD v2.1 F18).

엔진의 5상태는 바꾸지 않는다. '보류'는 원인마다 사용자가 할 일이 달라 원인을 함께 보인다.
"""
import re
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
    kind: Optional[str] = None   # 보류 갈래(R-② 2026-11-14): input / source / ambiguous / self_report / input_check

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
                   "다른 조건으로는 결론이 정해지지 않았습니다. 아래 표시한 곳만 공고문 원문에서 확인하면 결과가 확정됩니다.",
                   kind=SOURCE)


# ------------------------------------------------------------------ 보류 나누기(R-② 2026-11-14 사용자 결정, 점검 세션 docs/13 2-4)
# 보류 한 칸을 원인별 갈래로 — 갈래마다 사용자가 할 일이 다르다. 엔진 5상태·사유 코드는 그대로, 표시만 나눈다(4분류 집계에서는 모두 '확정 아님').
INPUT, SOURCE, AMBIGUOUS, SELF_REPORT, INPUT_CHECK = "input", "source", "ambiguous", "self_report", "input_check"
HOLD_KINDS = (INPUT, SOURCE, AMBIGUOUS, SELF_REPORT, INPUT_CHECK)
_INTERP = re.compile(r"\[([^\[\]]*=(?:충족|불충족)[^\[\]]*)\]\s*$")


def _ambiguous_todo(details) -> str:
    """해석이 갈리는 조건 — 해석별 결과를 알면 'A로 보면 …, B로 보면 …'으로 보이고 문의처를 붙인다."""
    shown = []
    for d in details:
        m = _INTERP.search(d)
        if m:
            parts = [x.strip() for x in m.group(1).split(",")]
            shown.append(" / ".join("'{}' 해석이면 {}".format(*p.rsplit("=", 1)) for p in parts if "=" in p))
    head = "공고문 원문의 해석이 갈려 결과가 해석에 따라 달라집니다"
    return (head + (f"({'; '.join(shown)})" if shown else "") +
            f". 어느 해석이 맞는지는 공고 기관({CONTACT})에 문의하세요 — 문의할 때 아래 조건과 원문 쪽을 알려 주세요.")


def display_result(verdict: str, review_reasons=None, checks: int = 0) -> Display:
    """엔진 결과 → 화면 표시. 보류는 갈래를 정해 할 일을 붙인다(갈래 없는 보류 없음 — tests/test_hold_kinds.py).
    갈래 우선순위(사용자가 먼저 할 수 있는 것부터): 입력 확인 > 원문 확인(자동 분석 공고) > 해석이 갈림 > 자기신고 > 입력하면 판정."""
    if checks:
        return display_checks(checks)
    if verdict == "NEEDS_INFO":
        return Display(HOLD_GROUP, "⚠️", "입력하면 판정",
                       "판정에 필요한 정보가 비어 있습니다. 아래 '추가로 입력하면 판정할 수 있는 조건'을 입력하면 판정됩니다.", kind=INPUT)
    if verdict != "MANUAL_REVIEW":
        return display(verdict)
    reasons = list((review_reasons or {}).values())
    codes = {getattr(r, "code", None) for r in reasons}
    if "INPUT_INCONSISTENT" in codes:
        return Display(HOLD_GROUP, "✏️", "입력 확인",
                       "입력하신 가구원수와 혼인·자녀 정보가 서로 맞지 않습니다. 가구원수(본인·배우자·자녀 포함)를 다시 확인해 주세요.",
                       kind=INPUT_CHECK)
    if "AMBIGUOUS_SOURCE" in codes or "SELF_REPORT_UNVERIFIED" not in codes:   # 사유를 모르는 수동 확인도 해석 갈림 쪽(문의처 안내)
        return Display(HOLD_GROUP, "⚖️", "해석이 갈림",
                       _ambiguous_todo(r.detail for r in reasons if getattr(r, "code", None) == "AMBIGUOUS_SOURCE"),
                       kind=AMBIGUOUS)
    return Display(HOLD_GROUP, "🙋", "자기신고",
                   "서류로만 확인되는 요건이 있어 자동으로 확정하지 않았습니다. 본인이 그 요건에 해당하면 지원 가능, 아니면 지원 불가입니다 — "
                   "아래 조건의 원문을 확인하세요.", kind=SELF_REPORT)
