# -*- coding: utf-8 -*-
"""판정 API (D2b, v3 ④-2) — 화면과 같은 판정(evaluate·match_all·자동 분석)을 HTTP로 제공한다.

실행: pip install -r requirements-api.txt && uvicorn api.main:app --reload   (문서: http://127.0.0.1:8000/docs)
배포: Dockerfile(Render 등) — 같은 이미지를 어느 호스팅에서나.

- GET  /health                     상태 확인
- GET  /notices?at=…               공고 목록 + 계층 + 접수 상태(at: 기준 시각, 기본 지금·한국 시간)
- POST /upload                     공고문 PDF 올리기(multipart `file`) → 식별 + (미등록이면) 자동 분석 — 판정할 수 있으면 계층 목록
- POST /evaluate                   공고·계층 하나 판정 — {"notice_id" | "sha256"(올린 공고), "layer", "profile": HouseholdProfile 항목}
- POST /match                      전 공고 판정 — {"profile": 저장 파일 형식(ccj-profile/1), "at"?, "only_open"?}

판정 로직은 갖지 않는다(src/의 엔진·매처·자동 분석을 그대로 호출). 서버는 받은 프로필을 저장하지 않는다.
올린 PDF는 LH·SH 공고로 식별되고 후속 작업(보강·검토)이 필요할 때만 공유 저장소에 잠시 둔다(src/analysis.py).
설정(환경변수): DATABASE_URL(공유 저장소 — 없으면 저장 없이 동작), CCJ_AUTO_JUDGE_PUBLIC(미등록 공고 자동 판정 공개, 기본 꺼짐),
CCJ_CORS_ORIGINS(화면 주소, 쉼표로 여럿 — 기본 http://localhost:3000).
"""
import dataclasses
import os
import sys
import threading
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from display_status import COMMON_NOTE, display, display_checks  # noqa: E402
from explainability import explain  # noqa: E402
from matcher import match_all, missing_inputs  # noqa: E402
from notice_identify import REGISTERED, SAME_NOTICE_OTHER_FILE, UNREGISTERED, identify_pdf  # noqa: E402
from notices_data import ALL_NOTICES  # noqa: E402
from profile_io import ProfileFormatError, household_from_dict, master_from_dict  # noqa: E402
from rule_engine import evaluate, validate_profile  # noqa: E402
from schedule import KST, load_schedules, now_kst, statuses  # noqa: E402
from store import get_store  # noqa: E402

app = FastAPI(title="공공임대 자격 판정 API", version="1",
              description="LH·SH 공고문 기반 결정론적 자격 판정. 신청 자격(필수요건)만 판정하며 순위·가점·당첨은 포함하지 않습니다.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.environ.get(
    "CCJ_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()], allow_methods=["GET", "POST"], allow_headers=["*"])

PUBLIC_ENV = "CCJ_AUTO_JUDGE_PUBLIC"
MAX_UPLOAD = 20 * 1024 * 1024
KEEP_DRAFTS = 64          # 올린 공고의 분석 결과를 프로세스에 둘 개수(저장소가 없어도 올린 뒤 판정할 수 있게)
_drafts: "OrderedDict[str, object]" = OrderedDict()
_drafts_lock = threading.Lock()


class EvaluateRequest(BaseModel):
    notice_id: Optional[str] = None
    sha256: Optional[str] = None       # /upload로 올려 자동 분석한 공고
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


def auto_public() -> bool:
    """미등록 공고 자동 판정(v3)을 공개했는가 — 화면(operator_mode.auto_judge_public)과 같은 환경변수, 기본 꺼짐."""
    return os.environ.get(PUBLIC_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _remember(sha: str, d) -> None:
    with _drafts_lock:
        _drafts[sha] = d
        _drafts.move_to_end(sha)
        while len(_drafts) > KEEP_DRAFTS:
            _drafts.popitem(last=False)


def _draft_for(sha: str):
    """올린 공고의 분석 결과 — 이 프로세스에 있으면 그것, 없으면 공유 저장소(같은 엔진 판)."""
    with _drafts_lock:
        if sha in _drafts:
            return _drafts[sha]
    import analysis
    import draft
    snap = get_store().latest_analysis(sha, analysis.analysis_version())
    if snap is None:
        return None
    d = draft.from_snapshot(snap)
    _remember(sha, d)
    return d


def _ident_json(ident) -> Dict[str, Any]:
    return {"status": ident.status, "notice_id": ident.notice_id, "reason": ident.reason, "issuer": ident.issuer,
            "program": ident.program, "announcement": ident.announcement, "pages": ident.pages,
            "windows": [{"start": w["start"], "end": w["end"], "page": w["page"]} for w in ident.windows[:3]],
            "similar": ident.similar}


@app.post("/upload")
def upload(file: UploadFile = File(...)):
    """공고문 PDF → 식별 → 등록 공고면 그 공고의 검증된 규칙, 미등록이면 자동 분석(공개했을 때)으로 판정할 수 있는지.
    판정은 /evaluate(notice_id 또는 sha256). judge.by: registered / confirm(같은 공고의 다른 파일 — 사용자가 확인한 뒤 notice_id로) /
    analysis / none(판정할 수 없음 — reason)."""
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "파일이 너무 큽니다(20MB까지).")
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "PDF 파일이 아닙니다. 공고문 PDF를 올려 주세요.")
    ident = identify_pdf(data)
    store = get_store()
    store.count("uploads")
    body = {"sha256": ident.sha256, "identification": _ident_json(ident)}
    if ident.status in (REGISTERED, SAME_NOTICE_OTHER_FILE):
        n = ALL_NOTICES[ident.notice_id]
        body["judge"] = {"by": "registered" if ident.status == REGISTERED else "confirm", "notice_id": ident.notice_id,
                         "title": n.title, "layers": list(n.layers)}
        return body
    d = None
    if ident.status == UNREGISTERED and auto_public():
        import analysis
        d = analysis.analyze(data, ident, store)
    if d is None or d.notice is None:
        store.count("unjudged")
        body["judge"] = {"by": "none", "reason": d.reason if d is not None else ident.reason}
        return body
    import grading
    _remember(ident.sha256, d)
    body["judge"] = {"by": "analysis", "program": d.program, "announcement_date": d.announcement_date,
                     "layers": list(d.notice.layers),
                     "grades": {k: g.grade for k, g in grading.grades(d).items()}}
    return body


def _profile(raw: Dict[str, Any]):
    try:
        profile = household_from_dict(raw)
    except ProfileFormatError as e:
        raise HTTPException(422, str(e))
    errors = validate_profile(profile)
    if errors:
        raise HTTPException(422, " / ".join(errors))
    return profile


def _result_json(result, notice, checks=()) -> Dict[str, Any]:
    """엔진 설명(5상태) + 화면 3상태 표시 + 원문에서 확인할 곳 + 공통 문구."""
    shown = display_checks(len(checks)) if checks else display(result.verdict)
    out = _explanation_json(explain(result, notice))
    out.update(display={"group": shown.group, "title": shown.title, "icon": shown.icon, "todo": shown.todo},
               checks=[{"kind": c.kind, "page": c.page, "text": c.text} for c in checks], common_note=COMMON_NOTE)
    return out


@app.post("/evaluate")
def evaluate_one(req: EvaluateRequest):
    if (req.notice_id is None) == (req.sha256 is None):
        raise HTTPException(422, "notice_id와 sha256 중 하나만 주세요.")
    if req.sha256 is not None:
        if not auto_public():
            raise HTTPException(403, "미등록 공고 자동 판정은 아직 공개되지 않았습니다.")
        d = _draft_for(req.sha256)
        if d is None or d.notice is None:
            raise HTTPException(404, "이 공고의 분석 결과가 없습니다. 공고문을 다시 올려 주세요(/upload).")
        if req.layer not in d.notice.layers:
            raise HTTPException(404, f"이 공고에 '{req.layer}' 계층이 없습니다 (있는 계층: {list(d.notice.layers)})")
        import grading
        result, checks = grading.judge(d, _profile(req.profile), req.layer)
        get_store().count("judged")
        return _result_json(result, d.notice, checks)
    notice = ALL_NOTICES.get(req.notice_id)
    if notice is None:
        raise HTTPException(404, f"공고가 없습니다: {req.notice_id}")
    if req.layer not in notice.layers:
        raise HTTPException(404, f"{req.notice_id}에 '{req.layer}' 계층이 없습니다 (있는 계층: {list(notice.layers)})")
    result = evaluate(_profile(req.profile), notice, req.layer)
    get_store().count("judged")
    return _result_json(result, notice)


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
