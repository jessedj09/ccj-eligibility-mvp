# -*- coding: utf-8 -*-
"""whatif.py — "무엇을 바꾸면 지원 가능해지나"(PRD v2.1 F19, 주요 기능2 보강).

판정 로직은 갖지 않는다 — 입력을 바꿔 기존 엔진·매처로 다시 판정하고 결과를 비교한다.
1) near_misses: 지원 불가인데 걸린 조건이 하나뿐인 공고·계층. 그 조건이 소득·총자산·자동차가액으로 정해지면
   "이 금액 이하면 충족"되는 한도를 이분 탐색으로 찾는다(엔진을 그대로 불러 확인하므로 한도는 원 단위로 정확하다).
2) 시나리오(혼인신고·예비신혼·거주지 이전·세대 분리): MasterProfile을 바꿔 전 공고를 다시 판정하고 얻는 것과 잃는 것을 비교.

주의: 판정 기준일은 공고일이다. 이미 공고된 공고에는 공고일 이후의 변화(혼인신고·전입·세대 분리·소득 변화)가 반영되지 않는다 —
이 결과는 다음 공고를 준비하는 참고용이다.
"""
import dataclasses
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, List, Optional

from matcher import MasterProfile, Match, match_all, scope_for, scoped_profile
from rule_engine import evaluate

CAVEAT = ("판정은 공고일 기준입니다. 이미 공고된 공고에는 공고일 이후의 변화(혼인신고·전입·세대 분리·소득 변화 등)가 "
          "반영되지 않으므로, 이 결과는 다음 공고를 준비하는 참고용입니다.")

# 한도를 찾을 수 있는 금액 항목(프로필 필드 → 화면 이름)
AMOUNT_FIELDS = {"monthly_income": "월평균소득", "total_assets": "총자산", "car_value": "자동차가액"}
# input_scope.json의 소득 범위 → 화면 설명(이 계층이 '소득·자산'을 누구 기준으로 보는지)
SCOPE_LABEL = {"household": "세대 합계", "self": "본인", "self_plus_parents": "본인+부모 합계",
               "youth_head": "세대주면 세대 합계·세대원이면 본인"}


@dataclass
class Threshold:
    field: str          # monthly_income / total_assets / car_value
    label: str          # 월평균소득 등
    scope: str          # 세대 합계 등
    current: int
    limit: int                          # 이 값 이하면 그 조건 충족
    review_limit: Optional[int] = None  # 이 값 이하면 '수동 확인'(원문 해석이 갈리는 구간, limit보다 클 때만)

    @property
    def gap(self) -> int:
        return self.current - self.limit


@dataclass
class NearMiss:
    match: Match
    condition_id: str
    description: str
    after: str                                  # 그 조건이 풀리면: "지원 가능" / "보류"
    thresholds: List[Threshold] = field(default_factory=list)


def _cond(match: Match, cid: str):
    for c in match.notice.layers[match.layer].conditions:
        if c.rule_id == cid:
            return c
    return None


def _passes(profile, match: Match, cid: str) -> bool:
    return cid in evaluate(profile, match.notice, match.layer).matched


def _not_failed(profile, match: Match, cid: str) -> bool:
    return cid not in evaluate(profile, match.notice, match.layer).failed


def _max_ok(p, match: Match, cid: str, fname: str, ok, lo: int, hi: int) -> int:
    """ok(lo)=참, ok(hi)=거짓일 때 ok가 참인 가장 큰 값(금액이 클수록 불리한 한도 조건 — 단조)."""
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ok(dataclasses.replace(p, **{fname: mid}), match, cid):
            lo = mid
        else:
            hi = mid
    return lo


def _threshold(m: MasterProfile, match: Match, cid: str, fname: str) -> Optional[Threshold]:
    p = scoped_profile(m, match.notice, match.layer)
    current = getattr(p, fname)
    if not isinstance(current, int) or current <= 0:
        return None
    # 이 계층이 매처의 특수 처리(트랙마다 다른 계층 범위) 없이 그대로 판정되는지 확인 — 아니면 한도를 계산하지 않는다
    direct = evaluate(p, match.notice, match.layer)
    if direct.failed != match.result.failed:
        return None
    if _passes(p, match, cid) or not _passes(dataclasses.replace(p, **{fname: 0}), match, cid):
        return None         # 이 금액만 바꿔서는 풀리지 않는 조건
    limit = _max_ok(p, match, cid, fname, _passes, 0, current)
    # 원문 해석이 갈리는 조건은 '충족'과 '불충족' 사이에 '수동 확인' 구간이 있다(예: 출생자녀 가산 적용 여부)
    review = _max_ok(p, match, cid, fname, _not_failed, limit, current)
    return Threshold(fname, AMOUNT_FIELDS[fname], SCOPE_LABEL.get(scope_for(match.notice, match.layer)["income"], ""),
                     current, limit, review if review > limit else None)


def near_misses(m: MasterProfile, matches: List[Match]) -> List[NearMiss]:
    """지원 불가 중 걸린 조건이 하나뿐인 것. 금액 한도가 있으면 한도까지(차이가 작은 순)."""
    out = []
    for x in matches:
        if x.verdict != "INELIGIBLE" or len(x.result.failed) != 1:
            continue
        cid = x.result.failed[0]
        cond = _cond(x, cid)
        if cond is None:
            continue
        after = "보류" if (x.result.unknown or x.result.review) else "지원 가능"
        ths = [t for f in AMOUNT_FIELDS if f in cond.inputs for t in [_threshold(m, x, cid, f)] if t]
        out.append(NearMiss(x, cid, cond.note, after, ths))
    return sorted(out, key=lambda n: (not n.thresholds, min((t.gap for t in n.thresholds), default=0)))


# ---- 시나리오 ----

def _plus(a: Optional[int], b: Optional[int]) -> Optional[int]:
    return None if a is None or b is None else a + b


def marry(m: MasterProfile, marriage_date: date, spouse_income: Optional[int], spouse_assets: Optional[int],
          spouse_car: Optional[int], spouse_has_home: bool, dual_income: bool, prenuptial: bool = False) -> MasterProfile:
    """혼인신고(또는 예비신혼부부로 신청). 본인·배우자(·본인 자녀)로 **새 세대**를 꾸리고(부모 세대에서 분리) 같은 곳에
    산다고 가정한다 — 세대 소득·자산은 본인+배우자, 주택은 둘 중 하나라도 있으면 보유. 예비신혼은 혼인신고일 없음."""
    base = separate_household(m)
    c = dict(base.common)
    c.update(marital_status="예비신혼" if prenuptial else "혼인중", marriage_date=None if prenuptial else marriage_date,
             household_size=c["household_size"] + 1, dual_income=dual_income,
             spouse_residence_area=c.get("spouse_residence_area") or c.get("residence_area"),
             spouse_income_base_area=c.get("spouse_income_base_area") or c.get("income_base_area"))
    home = "주택보유" if spouse_has_home or m.home_self == "주택보유" else m.home_self
    car = None if m.car_self is None or spouse_car is None else max(m.car_self, spouse_car)
    return dataclasses.replace(base, income_household=_plus(m.income_self, spouse_income),
                               assets_household=_plus(m.assets_self, spouse_assets), car_household=car,
                               home_household=home, common=c)


def move(m: MasterProfile, region: str) -> MasterProfile:
    """거주지(주민등록) 이전."""
    return dataclasses.replace(m, common={**m.common, "residence_area": region})


def separate_household(m: MasterProfile) -> MasterProfile:
    """부모 세대에서 분리해 본인(과 자녀)으로 세대를 구성 — 세대주가 되고 세대 소득·자산·주택은 본인 것만."""
    c = dict(m.common)
    kids = c.get("children_birth_dates") or []
    c.update(house_head_status="세대주", household_size=1 + len(kids), registered_with_parents=False)
    return dataclasses.replace(m, home_household=m.home_self, income_household=m.income_self,
                               assets_household=m.assets_self, car_household=m.car_self, common=c)


@dataclass
class ScenarioResult:
    name: str
    before: Dict[str, int]
    after: Dict[str, int]
    gained: List[Match]          # 지원 가능이 된 것
    lost: List[Match]            # 지원 가능이었는데 아니게 된 것


def _count(matches: List[Match]) -> Dict[str, int]:
    """화면 3상태(지원 가능 / 보류 / 지원 불가)별 개수."""
    out = {"ELIGIBLE": 0, "HOLD": 0, "INELIGIBLE": 0}
    for x in matches:
        out["HOLD" if x.verdict in ("NEEDS_INFO", "MANUAL_REVIEW") else x.verdict] += 1
    return out


def run_scenario(name: str, m: MasterProfile, change: Callable[[MasterProfile], MasterProfile], notices,
                 keep: Optional[Callable[[Match], bool]] = None) -> ScenarioResult:
    """시나리오 전후로 전 공고를 판정해 비교. keep으로 비교 대상을 거른다(예: 접수 중·예정 공고만)."""
    keep = keep or (lambda x: True)
    before = [x for x in match_all(m, notices) if keep(x)]
    after = [x for x in match_all(change(m), notices) if keep(x)]
    key = lambda x: (x.notice.notice_id, x.layer)  # noqa: E731
    b_ok = {key(x) for x in before if x.verdict == "ELIGIBLE"}
    a_ok = {key(x) for x in after if x.verdict == "ELIGIBLE"}
    return ScenarioResult(name, _count(before), _count(after),
                          gained=[x for x in after if key(x) in a_ok - b_ok],
                          lost=[x for x in before if key(x) in b_ok - a_ok])
