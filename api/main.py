# -*- coding: utf-8 -*-
"""판정 API (D2b) — 화면과 같은 판정(evaluate·match_all)을 HTTP로 제공한다.

실행: pip install -r requirements-api.txt && uvicorn api.main:app --reload   (문서: http://127.0.0.1:8000/docs)

- GET  /health                     상태 확인
- GET  /notices?at=…               공고 목록 + 계층 + 접수 상태(at: 기준 시각, 기본 지금·한국 시간)
- POST /evaluate                   공고·계층 하나 판정 — {"notice_id", "layer", "profile": HouseholdProfile 항목}
- POST /match                      전 공고 판정 — {"profile": 저장 파일 형식(ccj-profile/1), "at"?, "only_open"?}

판정 로직은 갖지 않는다(src/의 엔진·매처를 그대로 호출). 서버는 받은 프로필을 저장하지 않는다.
"""
import dataclasses
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from explainability import explain  # noqa: E402
from matcher import match_all, missing_inputs  # noqa: E402
from notices_data import ALL_NOTICES  # noqa: E402
from profile_io import ProfileFormatError, household_from_dict, master_from_dict  # noqa: E402
from rule_engine import evaluate, validate_profile  # noqa: E402
from schedule import KST, load_schedules, now_kst, statuses  # noqa: E402

app = FastAPI(title="공공임대 자격 판정 API", version="1",
              description="LH·SH 공고문 기반 결정론적 자격 판정. 신청 자격(필수요건)만 판정하며 순위·가점·당첨은 포함하지 않습니다.")


class EvaluateRequest(BaseModel):
    notice_id: str
    layer: str
    profile: Dict[str, Any]


class MatchRequest(BaseModel):
    profile: Dict[str, Any]
    at: Optional[datetime] = None
    only_open: bool = False


def _at(at: Optional[datetime]) -> datetime:
    if at is None:
        return now_kst()
    return at if at.tzinfo else at.replace(tzinfo=KST)


def _status_json(s) -> Dict[str, Any]:
    w = s.window
    return {"code": s.code, "text": s.text, "applicable": s.applicable,
            "window": None if w is None else {"label": w.label, "start": w.start.isoformat(), "end": w.end.isoformat()}}


def _explanation_json(exp) -> Dict[str, Any]:
    return dataclasses.asdict(exp)


@app.get("/health")
def health():
    return {"status": "ok", "notices": len(ALL_NOTICES)}


@app.get("/notices")
def notices(at: Optional[datetime] = None):
    at = _at(at)
    stat = statuses(list(ALL_NOTICES), at)
    sched = load_schedules()
    return {"at": at.isoformat(), "notices": [
        {"notice_id": nid, "title": n.title, "issuer": n.meta.get("issuer"), "program": n.meta.get("program"),
         "announcement_date": n.announcement_date.isoformat(), "layers": list(n.layers),
         "schedule": _status_json(stat[nid]), "schedule_note": sched[nid].note if nid in sched else None}
        for nid, n in ALL_NOTICES.items()]}


@app.post("/evaluate")
def evaluate_one(req: EvaluateRequest):
    notice = ALL_NOTICES.get(req.notice_id)
    if notice is None:
        raise HTTPException(404, f"공고가 없습니다: {req.notice_id}")
    if req.layer not in notice.layers:
        raise HTTPException(404, f"{req.notice_id}에 '{req.layer}' 계층이 없습니다 (있는 계층: {list(notice.layers)})")
    try:
        profile = household_from_dict(req.profile)
    except ProfileFormatError as e:
        raise HTTPException(422, str(e))
    errors = validate_profile(profile)
    if errors:
        raise HTTPException(422, " / ".join(errors))
    return _explanation_json(explain(evaluate(profile, notice, req.layer), notice))


@app.post("/match")
def match(req: MatchRequest):
    try:
        master = master_from_dict(req.profile)
    except ProfileFormatError as e:
        raise HTTPException(422, str(e))
    at = _at(req.at)
    stat = statuses(list(ALL_NOTICES), at)
    try:
        matches = match_all(master, ALL_NOTICES)
    except (TypeError, ValueError) as e:      # 항목 값의 형식 오류(예: 가구원수에 문자열)
        raise HTTPException(422, f"프로필 값 오류: {e}")
    if req.only_open:
        matches = [x for x in matches if stat[x.notice.notice_id].applicable]
    counts: Dict[str, int] = {}
    for x in matches:
        counts[x.verdict] = counts.get(x.verdict, 0) + 1
    return {"at": at.isoformat(), "only_open": req.only_open, "counts": counts,
            "missing_inputs": missing_inputs(matches),
            "matches": [{"notice_id": x.notice.notice_id, "title": x.notice.title, "layer": x.layer,
                         "verdict": x.verdict, "eligible_tracks": list(x.result.eligible_tracks),
                         "schedule": _status_json(stat[x.notice.notice_id]),
                         "explanation": _explanation_json(explain(x.result, x.notice))} for x in matches]}
