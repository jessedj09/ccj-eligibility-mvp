# -*- coding: utf-8 -*-
"""clause_resolution.py — R-③ 공고 단위 해소(2026-11-15 사용자 승인: 최종안 + 보완 A·B·C, docs/13 2-4).

조항 장부의 미분류 문장(규칙에 없는 조건일 수 있는 문장) 하나가 걸리면 그 계층의 '지원 가능'이 모두 보류가 된다(grading).
그 문장을 한 번 판정해 두면 **그 공고를 보는 모든 사용자**의 보류가 풀린다 — 사용자 수만큼이 아니라 문장 수만큼만 일한다.

    rows = store.resolutions_for(sha256, template)
    d2 = apply(d, sha256, rows)            # 판정에 쓸 초안 — '조건 아님'으로 해소된 문장을 미분류에서 빼고 d2.resolved에 남김

원칙(먼저 반영하고 뒤에서 확인한다 — 기다리지 않으면서 위험을 관리)
- 판정 하나로 바로 반영한다. '참고' 문장(자격 영역 밖·제한 표현 없음)은 확정(active), '필수' 문장(자격 영역 안이거나 제한 표현)은
  잠정(provisional) — 화면에 '운영 검토로 조건 아님 판단(교차 확인 중)'. 다른 판정자가 뒤에서 교차 확인해 '새 조건'이면 자동 취소.
- 같은 사업(판정 틀)에서 해소된 같은 문장(정규화 기준)은 새 공고에도 바로 적용한다(문장 사전). 기록을 읽을 때 계산하므로 원래 기록을
  취소하면 사전 적용도 함께 풀린다.
- '새 조건' 판정이 하나라도 있는 문장은 빼지 않는다(애매하면 보류 유지). 판정자 단위로 되돌릴 수 있다(revoke_judge).
- 문장 단위 LLM 판정(sentence_check)·위치 자동 해소(auto_position)는 묶음 C 시험을 통과하기 전까지 '초안'(proposed)으로만 받고
  판정에 쓰지 않는다. 정식 등록(registered)·운영자(operator — 사람)·두 판정 일치(r2_agree)는 바로 쓴다.
- Claude 세션 판정(session — 피드백 세션 권고 11-15)은 판정 지침·세션을 묶음 E로 시험하기 전(SESSION_TESTED False)에는: 참고 문장은
  바로 확정, 필수 문장은 초안 — 다른 판정자가 같은 판단을 내리면 그때 둘 다 확정('새 조건'이면 취소). 시험 통과 뒤에는 운영자와 같다.
- 잠정 기록은 PROVISIONAL_DUE_DAYS(7일) 안에 교차 확인이 없으면 대기열 맨 앞, PROVISIONAL_TTL_DAYS(14일)가 지나면 반영하지 않는다(보류로
  돌아감) — 교차 확인이 밀려 '먼저 반영'이 사실상 확정이 되지 않게.
- 문장 사전은 확정 기록만 옮기고, 지시어('위'·'아래'·'다음'·'해당'·'상기'·'이/본 공고')가 든 문장은 옮기지 않는다(가리키는 내용이 공고마다 다름).
- 해소 기록은 그 사업의 '독립 검증 완료' 근거가 아니다(src/verification.py와 무관). 멈춘 사업은 해소와 관계없이 판정하지 않는다(api _paused).
- 개인정보 없음 — 공고 원문 문장과 판정자 이름만.
"""
import hashlib
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import source_verify as sv  # noqa: E402

NOT_CONDITION, NEW_CONDITION = "not_condition", "new_condition"
REQUIRED, REFERENCE = "required", "reference"
PROPOSED, PROVISIONAL, ACTIVE, REVOKED = "proposed", "provisional", "active", "revoked"
APPLIED = (PROVISIONAL, ACTIVE)
SOURCES = ("registered", "operator", "session", "r2_agree", "sentence_check", "auto_position")
NORMALIZE_VERSION = 1            # sv.normalize를 바꾸면 올린다 — 문장 id가 달라져 기록을 다시 계산해야 함

# 묶음 C 시험(숨긴 새 조건을 '조건 아님'으로 보낸 경우 0)을 통과한 출처만 켠다 — 통과 전에는 초안으로만 받는다
GATED = {"sentence_check": False, "auto_position": False}
SESSION_TESTED = False           # Claude 세션 판정이 묶음 E(판정 지침·세션 독립 시험)를 통과했는가 — 통과 전에는 필수 문장에 교차 확인이 먼저
PROVISIONAL_DUE_DAYS, PROVISIONAL_TTL_DAYS = 7, 14
# 지시어 — 앞이 한글 글자가 아니고(낱말 시작) 뒤가 조사·띄어쓰기·요건류인 것만('위반'·'단위'·'위치'·'해당없음' 같은 낱말은 아님)
DEICTIC = re.compile(r"(?<![가-힣])(?:위|아래|다음|상기|해당|이\s*공고|본\s*공고)(?=\s|의|에|와|과|를|을|은|는|요건|조건|사항|표|기준|하는|하지|되는|자|각|공고|문|$)")

LABEL = {ACTIVE: "운영 검토로 조건 아님 확인", PROVISIONAL: "운영 검토로 조건 아님 판단(교차 확인 중)"}


def sentence_key(text: str) -> str:
    """정규화 문장의 지문(문장 사전 — 같은 사업의 다른 공고에서 같은 문장을 찾는다)."""
    return hashlib.sha1(sv.normalize(text).encode("utf-8")).hexdigest()[:12]


def sentence_id(sha256: str, page: int, text: str) -> str:
    """미분류 문장 id(파싱 세션 tools/sentence_check.sentence_id와 같은 정의 — 시험이 확인)."""
    return f"{sha256[:16]}:{page}:{sentence_key(text)}"


@dataclass(frozen=True)
class Resolution:
    sha256: str
    sentence_id: str
    page: int
    sentence: str
    verdict: str                 # not_condition / new_condition
    tier: str                    # required / reference
    source: str                  # SOURCES
    judge: str                   # 판정자(세션·운영자·모델 이름)
    reason: str = ""
    status: str = ACTIVE         # proposed / provisional / active / revoked
    template: str = ""
    normalize_version: int = NORMALIZE_VERSION
    id: Optional[int] = None
    created_at: Optional[str] = None


def eligibility_area(doc: Dict) -> List[Tuple[int, int]]:
    """자격 영역 — 계층마다 조건 근거가 있는 쪽 범위(grading.layer_pages와 같은 계산, 파싱 세션 clause_ledger.eligibility_area와 같은 뜻)."""
    import grading
    return list(grading.layer_pages(doc).values()) if doc else []


def tier(doc: Optional[Dict], page: int, text: str) -> str:
    """필수: 자격 영역 안이거나 제한·기준값 표현(sentence_check.guard 'c')이 있음 / 참고: 그 밖(안내·절차 문장)."""
    if any(a <= page <= b for a, b in eligibility_area(doc or {})):
        return REQUIRED
    import sentence_check as SC
    return REQUIRED if SC.guard(text, "c") else REFERENCE


def initial_status(source: str, verdict: str, tier_: str) -> str:
    """새 판정의 상태 — 시험 전 출처는 초안, '새 조건'은 확정(보류를 유지할 뿐이라 위험 없음), 참고는 확정, 필수는 잠정."""
    if source not in SOURCES:
        raise ValueError(f"모르는 출처: {source}")
    if GATED.get(source) is False:
        return PROPOSED
    if verdict == NEW_CONDITION or tier_ == REFERENCE:
        return ACTIVE
    if source == "session" and not SESSION_TESTED:
        return PROPOSED              # 시험 전 세션의 필수 문장 판정 — 다른 판정자가 같은 판단을 내려야 반영(record)
    return PROVISIONAL


def _age(r: "Resolution", now: datetime) -> Optional[timedelta]:
    if not r.created_at:
        return None
    t = datetime.fromisoformat(r.created_at)
    return now - (t if t.tzinfo else t.replace(tzinfo=timezone.utc))


def expired(r: "Resolution", now: Optional[datetime] = None) -> bool:
    """잠정 기록이 교차 확인 없이 PROVISIONAL_TTL_DAYS를 넘겼는가 — 그러면 반영하지 않는다."""
    if r.status != PROVISIONAL:
        return False
    age = _age(r, now or datetime.now(timezone.utc))
    return age is not None and age > timedelta(days=PROVISIONAL_TTL_DAYS)


def due(rows: Iterable["Resolution"], now: Optional[datetime] = None) -> List["Resolution"]:
    """교차 확인이 급한 잠정 기록 — PROVISIONAL_DUE_DAYS를 넘긴 것(만료된 것 포함), 오래된 것부터."""
    now = now or datetime.now(timezone.utc)
    out = [r for r in rows if r.status == PROVISIONAL and (_age(r, now) or timedelta(0)) >= timedelta(days=PROVISIONAL_DUE_DAYS)]
    return sorted(out, key=lambda r: r.created_at or "")


def make(d, sha256: str, page: int, sentence: str, verdict: str, source: str, judge: str, reason: str = "") -> Resolution:
    """초안의 미분류 문장 하나에 대한 새 판정 기록(상태는 initial_status)."""
    if verdict not in (NOT_CONDITION, NEW_CONDITION):
        raise ValueError(f"판정은 not_condition / new_condition: {verdict}")
    t = tier(getattr(d, "doc", None), page, sentence)
    return Resolution(sha256, sentence_id(sha256, page, sentence), page, sentence, verdict, t, source, judge, reason,
                      initial_status(source, verdict, t), getattr(d, "template", "") or "")


@dataclass(frozen=True)
class Resolved:
    page: int
    sentence: str
    status: str                  # active / provisional
    via: str                     # direct(이 공고의 기록) / dictionary(같은 사업 다른 공고의 같은 문장)

    @property
    def label(self) -> str:
        return LABEL[self.status] + (" — 같은 사업의 다른 공고에서 판정한 같은 문장" if self.via == "dictionary" else "")


def apply(d, sha256: str, rows: Iterable[Resolution], now: Optional[datetime] = None):
    """해소 기록을 초안에 반영한 복사본 — '조건 아님'(확정·잠정) 문장을 미분류에서 빼고 d.resolved에 남긴다. 기록이 없으면 그대로.
    만료된 잠정 기록은 반영하지 않는다."""
    rows = [r for r in rows if r.status in APPLIED and not expired(r, now)]
    if not rows or not getattr(d, "unclassified", None):
        return d
    template = getattr(d, "template", "") or ""
    blocked_ids = {r.sentence_id for r in rows if r.verdict == NEW_CONDITION}
    blocked_keys = {sentence_key(r.sentence) for r in rows if r.verdict == NEW_CONDITION and r.template == template}
    direct = {r.sentence_id: r for r in rows if r.verdict == NOT_CONDITION and r.sha256 == sha256}
    by_key = {}
    for r in rows:
        if (r.verdict == NOT_CONDITION and r.status == ACTIVE and r.sha256 != sha256 and template and r.template == template
                and not DEICTIC.search(r.sentence)):
            by_key[sentence_key(r.sentence)] = r
    keep, resolved = [], []
    for page, text in d.unclassified:
        sid, key = sentence_id(sha256, page, text), sentence_key(text)
        if sid in blocked_ids or key in blocked_keys:
            keep.append((page, text))
        elif sid in direct:
            resolved.append(Resolved(page, text, direct[sid].status, "direct"))
        elif key in by_key and not DEICTIC.search(text):
            resolved.append(Resolved(page, text, by_key[key].status, "dictionary"))
        else:
            keep.append((page, text))
    if not resolved:
        return d
    return replace(d, unclassified=keep, resolved=list(getattr(d, "resolved", []) or []) + resolved)


def record(store, d, sha256: str, page: int, sentence: str, verdict: str, source: str, judge: str, reason: str = ""):
    """판정 하나를 기록한다. 같은 문장에 다른 판정자의 잠정 기록(또는 시험 전 세션의 필수 문장 초안)이 있으면 교차 확인 —
    '조건 아님'이면 둘 다 확정, '새 조건'이면 그 기록을 취소한다(새 조건 기록이 남아 보류 유지). → 새 기록.
    시험 전 출처(LLM·위치 자동)의 초안은 교차 확인 대상이 아니고, 그 출처의 판정으로 교차 확인하지도 않는다."""
    r = make(d, sha256, page, sentence, verdict, source, judge, reason)
    if GATED.get(source) is not False:
        for old in store.resolutions_for(sha256, r.template):
            pending = old.status == PROVISIONAL or (old.status == PROPOSED and old.source == "session")
            if old.sentence_id != r.sentence_id or not pending or old.judge == judge or old.verdict != NOT_CONDITION:
                continue
            store.set_resolution_status(old.id, ACTIVE if verdict == NOT_CONDITION else REVOKED)
            if verdict == NOT_CONDITION:
                r = replace(r, status=ACTIVE)          # 두 판정자가 같은 판단 — 확정
    rid = store.save_resolution(r)
    return replace(r, id=rid)


# ------------------------------------------------------------------ 대기열(문장 단위, 영향 큰 순서)
@dataclass(frozen=True)
class QueueItem:
    sha256: str
    title: str
    page: int
    sentence: str
    tier: str
    layers: Tuple[str, ...]      # 이 문장이 '지원 가능'을 보류시키는 계층
    open_now: bool               # 접수 중·예정
    sentence_id: str = field(default="")

    @property
    def priority(self) -> Tuple:
        return (len(self.layers), self.open_now, self.tier == REQUIRED)


def queue(entries: Sequence[Tuple[str, str, object, bool]]) -> List[QueueItem]:
    """entries: [(sha256, 제목, 해소 반영한 초안, 접수 중·예정)] → 아직 해소 안 된 미분류 문장(같은 공고·같은 문장은 하나),
    보류시키는 계층 수 × 접수 중·예정 × 필수 먼저 순서."""
    import grading
    out, seen = [], set()
    for sha, title, d, open_now in entries:
        if getattr(d, "notice", None) is None:
            continue
        for page, text in dict.fromkeys(d.unclassified):
            sid = sentence_id(sha, page, text)
            if sid in seen:
                continue
            seen.add(sid)
            layers = tuple(lay for lay in d.notice.layers if (page, text) in grading.layer_clauses(d, lay))
            out.append(QueueItem(sha, title, page, text, tier(d.doc, page, text), layers, bool(open_now), sid))
    return sorted(out, key=lambda q: q.priority, reverse=True)


def import_proposals(items: Iterable[Dict], judge: str, source: str = "sentence_check") -> List[Resolution]:
    """파싱 세션이 넘긴 판정 후보({sha256, sentence_id, page, sentence, tier, draft_verdict, reason, template, context?} —
    sentence_check.candidates 형식, context는 읽지 않음) → 기록. draft_verdict가 None인 후보는 건너뛴다.
    시험 전 출처라 상태는 초안 — 판정에 쓰지 않는다. id가 문장과 맞지 않으면 거부(문장 자르기·정규화가 달라진 것)."""
    out = []
    for it in items:
        sha, page, text = it["sha256"], int(it["page"]), it["sentence"]
        if it.get("sentence_id") and it["sentence_id"] != sentence_id(sha, page, text):
            raise ValueError(f"문장 id가 맞지 않습니다: {it['sentence_id']} (p.{page})")
        if it.get("draft_verdict") is None:
            continue                     # 판정 없는 후보(슬롯 없이 뽑은 문장) — 대기열에 남는다
        verdict = {"조건 아님": NOT_CONDITION, "새 조건": NEW_CONDITION}.get(it["draft_verdict"], it["draft_verdict"])
        if verdict not in (NOT_CONDITION, NEW_CONDITION):
            raise ValueError(f"판정 값이 맞지 않습니다: {it['draft_verdict']!r}")
        t = it.get("tier") or REQUIRED
        t = {"필수": REQUIRED, "참고": REFERENCE}.get(t, t)
        out.append(Resolution(sha, sentence_id(sha, page, text), page, text, verdict, t, source, judge, it.get("reason", ""),
                              initial_status(source, verdict, t), it.get("template", "")))
    return out
