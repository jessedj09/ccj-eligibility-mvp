# -*- coding: utf-8 -*-
"""
priority_scoring.py — N1(서울공릉) 우선공급(2세미만 자녀) 배점 계산.

verdict(ELIGIBLE 등)와는 완전히 분리된 별도 점수다. 우선공급 지원 자격이 있어도
이 점수가 낮으면 경쟁에서 밀릴 뿐, 자격 자체가 사라지는 건 아니다.

지난 세션 결론 반영:
- 1순위(노원구 거주): ①거주지·거주기간 + ②청약저축 납입횟수 둘 다 채점
- 2순위(노원구 외 서울시): 노원구 거주자가 아니므로 ①은 적용 불가, ②만 채점
- ①번 항목 점수표는 공고문 p.7에서 찾았으나 인쇄 위치가 '3-2 주거약자용주택' 섹션이라
  일반 우선공급에도 재사용되는지는 100% 확정이 아님(강한 정황) — 실사용 전 LH 재확인 권장
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PriorityResult:
    tier: Optional[str]          # "1순위" / "2순위" / None(우선공급 대상 아님)
    item1_residence: Optional[int]   # ①거주지·거주기간 배점 (2순위는 None=적용불가)
    item2_subscription: int          # ②청약저축 납입횟수 배점
    total: int
    caveat: str


def n1_priority(profile) -> PriorityResult:
    if profile.residence_region == "노원구":
        tier = "1순위"
    elif profile.residence_region in ("서울시", "서울"):
        tier = "2순위"
    else:
        tier = None

    # ②청약저축 납입횟수 배점 (1순위·2순위 공통)
    if profile.subscription_months >= 24 and profile.subscription_payment_count >= 24:
        item2 = 3
    elif profile.subscription_months >= 6 and profile.subscription_payment_count >= 6:
        item2 = 1
    else:
        item2 = 0  # 미가입 또는 이력 부족 — 청약통장 이력이 없으면 여기서 0점이 됨

    # ①거주지·거주기간 배점 — 1순위(노원구 거주자)만 해당
    item1 = None
    if tier == "1순위":
        item1 = 3 if profile.residence_years >= 3 else 1

    total = (item1 or 0) + item2
    caveat = ("①번 배점표의 일반 우선공급 적용 여부는 강한 정황(강한 추정)일 뿐 "
              "100% 확정은 아님 — 실사용 전 LH청약플러스·고객센터 재확인 권장")
    return PriorityResult(tier, item1, item2, total, caveat)
