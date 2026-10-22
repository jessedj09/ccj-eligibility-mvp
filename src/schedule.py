# -*- coding: utf-8 -*-
"""schedule.py — 공고별 청약 접수기간과 "지금 신청할 수 있는가"(D2).

자격 판정(rule_engine)과 별개다. 접수기간은 rules/schedules.json에 원문 인용과 함께 두고(공고 규칙 파일은 생성 스크립트가
다시 쓰므로 분리), 이 모듈은 기준 시각에 각 공고가 접수 예정·접수 중·마감인지만 계산한다. 시각은 모두 한국 시간이다.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCHEDULES_PATH = Path(__file__).resolve().parent.parent / "rules" / "schedules.json"
KST = timezone(timedelta(hours=9))

UPCOMING, OPEN, CLOSED, UNKNOWN = "UPCOMING", "OPEN", "CLOSED", "UNKNOWN"
STATUS_LABEL = {UPCOMING: "🗓️ 접수 예정", OPEN: "🟢 접수 중", CLOSED: "⚫ 접수 마감", UNKNOWN: "❔ 접수기간 정보 없음"}


class ScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class Window:
    label: str
    start: datetime
    end: datetime
    page: int


@dataclass(frozen=True)
class Schedule:
    notice_id: str
    windows: Tuple[Window, ...]
    note: Optional[str] = None


@dataclass(frozen=True)
class Status:
    code: str
    window: Optional[Window] = None   # 접수 중이면 그 기간, 예정이면 다음 기간, 마감이면 마지막 기간

    @property
    def text(self) -> str:
        w = self.window
        if w is None:
            return STATUS_LABEL[self.code]
        span = f"{_fmt(w.start)} ~ {_fmt(w.end)}"
        if self.code == OPEN:
            return f"{STATUS_LABEL[OPEN]} — {w.label} {span} 마감"
        if self.code == UPCOMING:
            return f"{STATUS_LABEL[UPCOMING]} — {w.label} {span}"
        return f"{STATUS_LABEL[CLOSED]} — {w.label} {span}"

    @property
    def applicable(self) -> bool:
        """지금 신청할 수 있거나 앞으로 신청할 수 있는 공고."""
        return self.code in (OPEN, UPCOMING)


def _fmt(t: datetime) -> str:
    return f"{t:%Y.%m.%d.} {t:%H:%M}"


def _parse(s: str, where: str) -> datetime:
    try:
        return datetime.fromisoformat(s).replace(tzinfo=KST)
    except ValueError as e:
        raise ScheduleError(f"{where}: 날짜·시각 형식 오류 {s!r} (YYYY-MM-DDTHH:MM)") from e


@lru_cache(maxsize=None)
def load_schedules() -> Dict[str, Schedule]:
    doc = json.loads(SCHEDULES_PATH.read_text(encoding="utf-8"))
    out = {}
    for nid, e in doc["notices"].items():
        wins = []
        for i, w in enumerate(e["windows"]):
            where = f"{nid}.windows[{i}]"
            start, end = _parse(w["start"], where), _parse(w["end"], where)
            if not start < end:
                raise ScheduleError(f"{where}: 시작이 끝보다 늦거나 같습니다")
            if wins and start < wins[-1].end:
                raise ScheduleError(f"{where}: 기간이 시간 순서가 아니거나 앞 기간과 겹칩니다")
            wins.append(Window(w["label"], start, end, w["source"]["page"]))
        if not wins:
            raise ScheduleError(f"{nid}: 접수기간이 없습니다")
        out[nid] = Schedule(nid, tuple(wins), e.get("note"))
    return out


def now_kst() -> datetime:
    return datetime.now(KST)


def status(notice_id: str, at: Optional[datetime] = None) -> Status:
    """기준 시각(기본: 지금, 한국 시간)에 공고의 접수 상태. 시작·마감 시각 당일은 그 시각까지 포함한다."""
    sched = load_schedules().get(notice_id)
    if sched is None:
        return Status(UNKNOWN)
    at = at or now_kst()
    if at.tzinfo is None:
        at = at.replace(tzinfo=KST)
    for w in sched.windows:
        if w.start <= at <= w.end:
            return Status(OPEN, w)
        if at < w.start:
            return Status(UPCOMING, w)
    return Status(CLOSED, sched.windows[-1])


def statuses(notice_ids: List[str], at: Optional[datetime] = None) -> Dict[str, Status]:
    at = at or now_kst()
    return {nid: status(nid, at) for nid in notice_ids}
