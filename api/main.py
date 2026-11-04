# -*- coding: utf-8 -*-
"""판정 API (D2b, v3 ④-2) — 화면과 같은 판정(evaluate·match_all·자동 분석)을 HTTP로 제공한다.

실행: pip install -r requirements-api.txt && uvicorn api.main:app --reload   (문서: http://127.0.0.1:8000/docs)
배포: Dockerfile(Render 등) — 같은 이미지를 어느 호스팅에서나.

- GET  /health                     상태 확인
- GET  /notices?at=…               공고 목록 + 계층 + 접수 상태(at: 기준 시각, 기본 지금·한국 시간)
- POST /upload                     공고문 PDF 올리기(multipart `file`) → 식별 + (미등록이면) 자동 분석 — 판정할 수 있으면 계층 목록
- GET  /form?layer=…&notice_id=…|sha256=…   그 공고·계층에서 묻는 입력 양식(src/form_spec.py) — 화면은 이대로 그린다
- POST /evaluate                   공고·계층 하나 판정 — {"notice_id" | "sha256"(올린 공고), "layer", "profile": HouseholdProfile 항목
                                   (age 대신 birth_date를 주면 공고일 기준 만 나이로)}
- GET  /match/form                 '내 조건으로 공고 찾기' 입력 양식(src/form_spec.py master_form — 항목 이름 'master.x'는 저장 파일의 master)
- POST /match                      전 공고 판정 — {"profile": 저장 파일 형식(ccj-profile/1), "at"?, "only_open"?}
                                   (+ 화면 3상태·접수 일정·조건 하나만 부족한 공고와 금액 한도)
- POST /whatif                     시나리오(혼인신고·예비신혼·거주지 이전·세대 분리) 전후 비교 — src/whatif.py

판정 로직은 갖지 않는다(src/의 엔진·매처·자동 분석을 그대로 호출). 서버는 받은 프로필을 저장하지 않는다.
올린 PDF는 LH·SH 공고로 식별되고 후속 작업(보강·검토)이 필요할 때만 공유 저장소에 잠시 둔다(src/analysis.py).
설정(환경변수): DATABASE_URL(공유 저장소 — 없으면 저장 없이 동작), CCJ_AUTO_JUDGE_PUBLIC(미등록 공고 자동 판정 공개, 기본 꺼짐),
CCJ_CORS_ORIGINS(화면 주소, 쉼표로 여럿 — 기본 http://localhost:3000), CCJ_UPLOAD_PER_HOUR(접속자당 시간당 업로드 상한, 기본 0 = 제한 없음).
"""
import dataclasses
import hashlib
import os
import sys
import threading
from collections import OrderedDict
from functools import lru_cache
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from display_status import COMMON_NOTE, display, display_checks  # noqa: E402
from explainability import explain  # noqa: E402
from matcher import match_all, missing_fields, missing_inputs  # noqa: E402
import notice_identify as ni  # noqa: E402
from notice_identify import REGISTERED, SAME_NOTICE_OTHER_FILE, UNREGISTERED, identify_pdf  # noqa: E402
from notices_data import ALL_NOTICES  # noqa: E402
from profile_io import ProfileFormatError, household_from_dict, master_from_dict  # noqa: E402
from rule_engine import evaluate, validate_profile  # noqa: E402
from schedule import CLOSED, KST, OPEN, UPCOMING, load_schedules, now_kst, statuses  # noqa: E402
from store import UNKNOWN_DEMOTED, get_store  # noqa: E402
import whatif  # noqa: E402

app = FastAPI(title="공공임대 자격 판정 API", version="1",
              description="LH·SH 공고문 기반 결정론적 자격 판정. 신청 자격(필수요건)만 판정하며 순위·가점·당첨은 포함하지 않습니다.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.environ.get(
    "CCJ_CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()], allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"])

from api.accounts_api import router as accounts_router  # noqa: E402 — 회원가입·로그인·내 조건(2026-11-03)
app.include_router(accounts_router)

PUBLIC_ENV = "CCJ_AUTO_JUDGE_PUBLIC"
MAX_UPLOAD = 20 * 1024 * 1024
# 업로드 횟수 제한(C9) — 같은 접속자(IP) 기준 한 시간에 UPLOAD_PER_HOUR건. **기본 0 = 제한 없음**(2026-11-01 사용자 결정 — 필요해지면
# 환경변수로 켠다). IP는 이 프로세스 메모리에만 잠깐 두고(해시) 저장하지 않는다 — 재시작하면 사라진다.
UPLOAD_PER_HOUR = int(os.environ.get("CCJ_UPLOAD_PER_HOUR", "0"))
_uploads: Dict[str, list] = {}
_uploads_lock = threading.Lock()
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


SCENARIOS = {"marry": "혼인신고를 하면", "prenuptial": "예비신혼부부로 신청하면", "move": "거주지를 옮기면",
             "separate": "세대를 분리하면"}


class WhatIfRequest(MatchRequest):
    scenario: str                              # SCENARIOS의 키
    marriage_date: Optional[date] = None       # marry — 없으면 오늘(한국 시간)
    spouse_income: Optional[int] = None        # marry·prenuptial — 배우자 소득·자산·자동차(모르면 null)
    spouse_assets: Optional[int] = None
    spouse_car: Optional[int] = None
    spouse_has_home: bool = False
    dual_income: bool = False
    region: Optional[str] = None               # move — 옮길 거주지(지역 표준 이름)


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
            "similar": ident.similar, "corrects": ident.corrects}


def _correction(ident, filename: Optional[str]):
    """정정 공고(피드백 B3): LH·SH 정정 공고는 본문에 '정정' 표시가 없고 내려받은 파일 이름에만 붙는다. 등록 공고와 공고일·사업·단지가
    같은 다른 파일인데 파일 이름에 '정정'이 있고 등록 원문은 정정본이 아니면, 옛 등록 규칙으로 판정하자고 묻지 않고 이 파일(최신 판)을
    새로 분석한다. 파일 이름이 없거나 바뀌었으면 지금처럼 경고와 함께 사용자 확인을 받는다."""
    if ident.status != SAME_NOTICE_OTHER_FILE or "정정" not in (filename or ""):
        return ident
    n = ALL_NOTICES[ident.notice_id]
    if "정정" in n.meta.get("source", {}).get("document", ""):
        return ident
    return dataclasses.replace(ident, status=UNREGISTERED, notice_id=None, corrects=ident.notice_id, reason=(
        f"등록 공고 {ident.notice_id}({n.title})의 정정 공고로 보입니다(파일 이름). 정정으로 조건이 바뀌었을 수 있어 "
        "등록된 규칙 대신 이 파일을 새로 읽어 판정합니다."))


def _identify(data: bytes, store):
    """식별 — 같은 파일을 전에 식별했으면(공유 저장소, 같은 식별 판) PDF를 다시 읽지 않는다. 큰 공고는 읽는 데 수십 초라
    여러 사용자가 같은 공고를 올릴 때 처음 한 번만 기다리게(A2). 등록 공고 원문은 지문만으로 알아보므로 저장하지 않는다."""
    sha, version = hashlib.sha256(data).hexdigest(), ni.ident_version()
    hit = store.get_ident(sha, version)
    if hit is not None:
        try:
            return ni.from_dict(hit)
        except TypeError:
            pass                          # 형식이 다른 저장본은 무시하고 다시 식별
    ident = identify_pdf(data)
    if ident.status != REGISTERED:
        store.save_ident(sha, version, ni.to_dict(ident))
    return ident


def _paused(d, store) -> Optional[str]:
    """그 사업(템플릿)의 자동 판정을 멈췄으면 그 이유 — 비교에서 위험이 나와 자동 강등됐거나 운영자가 멈춤(A3, program_health).
    멈춘 사업 목록을 읽지 못하면(DB 장애) 모든 사업을 멈춘 것으로 본다(피드백 A4) — 등록 공고 판정은 계속된다."""
    if d is None or not d.template:
        return None
    demoted = store.demoted_programs()
    if demoted is UNKNOWN_DEMOTED:
        return STORE_DOWN
    return PAUSED.format(d.program) if d.template in demoted else None


PAUSED = "이 사업({})은 정확도 점검 중이라 자동 판정을 잠시 멈췄습니다. 점검이 끝나면 다시 판정합니다."
STORE_DOWN = ("서버 점검 중이라 새 공고 자동 판정을 잠시 멈췄습니다. 등록된 공고는 목록에서 그대로 판정할 수 있습니다. "
              "잠시 뒤 다시 올려 주세요.")


def _client(request: Request) -> str:
    """접속자 구분(해시) — 호스팅의 프록시 뒤에서는 X-Forwarded-For의 첫 주소."""
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else ""))
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def _rate_limit(request: Request) -> None:
    if UPLOAD_PER_HOUR <= 0:
        return
    import time
    now, key = time.time(), _client(request)
    with _uploads_lock:
        recent = [t for t in _uploads.get(key, []) if now - t < 3600]
        if len(recent) >= UPLOAD_PER_HOUR:
            wait = int(3600 - (now - recent[0])) // 60 + 1
            raise HTTPException(429, f"한 시간에 {UPLOAD_PER_HOUR}건까지 올릴 수 있습니다. 약 {wait}분 뒤에 다시 올려 주세요. "
                                     "등록된 공고는 '목록에서 고르기'로 바로 판정할 수 있습니다.")
        recent.append(now)
        _uploads[key] = recent
        if len(_uploads) > 10_000:                      # 오래된 접속자 정리(메모리 상한)
            for k in [k for k, v in _uploads.items() if now - v[-1] >= 3600]:
                del _uploads[k]


@app.post("/upload")
def upload(request: Request, file: UploadFile = File(...)):
    """공고문 PDF → 식별 → 등록 공고면 그 공고의 검증된 규칙, 미등록이면 자동 분석(공개했을 때)으로 판정할 수 있는지.
    판정은 /evaluate(notice_id 또는 sha256). judge.by: registered / confirm(같은 공고의 다른 파일 — 사용자가 확인한 뒤 notice_id로) /
    analysis / none(판정할 수 없음 — reason)."""
    data = file.file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "파일이 너무 큽니다(20MB까지).")
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "PDF 파일이 아닙니다. 공고문 PDF를 올려 주세요.")
    _rate_limit(request)                 # 형식 오류는 세지 않는다 — 실제로 읽는 업로드만
    store = get_store()
    ident = _correction(_identify(data, store), file.filename)
    store.count("uploads")
    body = {"sha256": ident.sha256, "identification": _ident_json(ident)}
    if ident.status in (REGISTERED, SAME_NOTICE_OTHER_FILE):
        n = ALL_NOTICES[ident.notice_id]
        body["judge"] = {"by": "registered" if ident.status == REGISTERED else "confirm", "notice_id": ident.notice_id,
                         "title": n.title, "layers": list(n.layers),
                         "unsupported_layers": [{"name": u["name"], "note": u["note"], "page": u.get("page")}
                                                for u in n.meta.get("unsupported_layers", [])]}
        return body
    d = None
    if ident.status == UNREGISTERED and auto_public():
        import analysis
        d = analysis.analyze(data, ident, store)
    paused = _paused(d, store)
    if d is None or d.notice is None or paused:
        import draft
        store.count("unjudged")
        if paused:
            reason = paused
        elif d is not None:
            reason = d.reason
        elif ident.status == UNREGISTERED:
            reason = "새 공고 자동 판정은 아직 공개 전입니다."
        else:
            reason = ident.reason
        # 무엇을 할 수 있는지 함께 알린다: 자동 판정하는 사업, 등록 공고는 목록에서 판정
        body["judge"] = {"by": "none", "reason": reason, "auto_public": auto_public(),
                         "supported_programs": draft.passing_programs(), "registered": len(ALL_NOTICES)}
        return body
    import grading
    _remember(ident.sha256, d)
    body["judge"] = {"by": "analysis", "program": d.program, "announcement_date": d.announcement_date,
                     "layers": list(d.notice.layers),
                     "grades": {k: g.grade for k, g in grading.grades(d).items()}}
    return body


def _profile(raw: Dict[str, Any], notice=None):
    """요청의 profile → HouseholdProfile. birth_date(YYYY-MM-DD)를 주면 공고일 기준 만 나이로 바꾼다(생일 경계 하루 차이까지 —
    화면이 나이를 계산하지 않게). age와 함께 주면 422."""
    raw = dict(raw)
    if "birth_date" in raw:
        if "age" in raw or notice is None:
            raise HTTPException(422, "birth_date와 age 중 하나만 주세요.")
        try:
            b = date.fromisoformat(raw.pop("birth_date"))
        except (TypeError, ValueError):
            raise HTTPException(422, "birth_date는 'YYYY-MM-DD' 형식이어야 합니다.")
        ann = notice.announcement_date
        raw["age"] = ann.year - b.year - ((ann.month, ann.day) < (b.month, b.day))
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


def _target(notice_id: Optional[str], sha256: Optional[str], layer: str):
    """판정 대상 → (공고 규칙, 자동 분석 초안 또는 None). 등록 공고(notice_id) 또는 올린 공고(sha256) 하나."""
    if (notice_id is None) == (sha256 is None):
        raise HTTPException(422, "notice_id와 sha256 중 하나만 주세요.")
    if sha256 is not None:
        if not auto_public():
            raise HTTPException(403, "미등록 공고 자동 판정은 아직 공개되지 않았습니다.")
        d = _draft_for(sha256)
        if d is None or d.notice is None:
            raise HTTPException(404, "이 공고의 분석 결과가 없습니다. 공고문을 다시 올려 주세요(/upload).")
        paused = _paused(d, get_store())
        if paused:
            raise HTTPException(403, paused)
        notice, where = d.notice, "이 공고"
    else:
        d, notice, where = None, ALL_NOTICES.get(notice_id), notice_id
        if notice is None:
            raise HTTPException(404, f"공고가 없습니다: {notice_id}")
    if layer not in notice.layers:
        unsupported = {u["name"]: u for u in notice.meta.get("unsupported_layers", [])}
        if layer in unsupported:
            raise HTTPException(404, f"'{layer}' 계층은 이 공고에 있지만 아직 판정을 지원하지 않습니다. {unsupported[layer]['note']}")
        raise HTTPException(404, f"{where}에 '{layer}' 계층이 없습니다 (있는 계층: {list(notice.layers)})")
    return notice, d


@app.get("/form")
def form(layer: str, notice_id: Optional[str] = None, sha256: Optional[str] = None):
    """공고·계층 하나를 판정할 때 묻는 입력 양식(src/form_spec.py) — 화면은 이대로 그린다."""
    import form_spec
    notice, _ = _target(notice_id, sha256, layer)
    return form_spec.form_for(notice, layer)


ROOT = Path(__file__).resolve().parent.parent
ENGINE_FILES = ("src/rule_engine.py", "src/rule_data.py", "src/explainability.py", "src/display_status.py")


def _digest(paths) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:12]


@lru_cache(maxsize=1)
def engine_version() -> str:
    """판정 엔진·기준표의 판 — 엔진 코드나 소득 기준표가 바뀌면 달라진다(결과 보관·재현성, 피드백 B2)."""
    return "e-" + _digest([ROOT / f for f in ENGINE_FILES] + sorted((ROOT / "rules" / "reference").glob("*.json")))


@lru_cache(maxsize=None)
def rule_version(nid: str) -> str:
    """등록 공고 규칙의 판 — 규칙 파일이 바뀌면 달라진다."""
    return "r-" + _digest([ROOT / "rules" / "notices" / f"{nid}.json"])


def _basis(req: "EvaluateRequest", notice, d) -> Dict[str, Any]:
    """무엇으로 판정했는가 — '같은 공고·같은 입력·같은 규칙(또는 분석)·같은 엔진 판이면 같은 결과'를 확인할 수 있게(피드백 B2)."""
    out = {"judged_at": now_kst().isoformat(timespec="seconds"), "layer": req.layer,
           "announcement_date": str(notice.announcement_date), "engine_version": engine_version()}
    if d is None:
        out.update(by="registered", notice_id=req.notice_id, title=notice.title, rule_version=rule_version(req.notice_id),
                   source_sha256=notice.meta.get("source", {}).get("sha256"))
    else:
        import analysis
        out.update(by="analysis", sha256=req.sha256, program=d.program, analysis_version=analysis.analysis_version())
    return out


# 엔진이 자녀 생년월일에서 계산하는 항목 — 질문은 원래 입력란(자녀 생년월일)으로 한다
DERIVED_INPUT = {"has_children": "children_birth_dates", "youngest_child_birth_date": "children_birth_dates"}


def _questions(result, notice, layer: str) -> list:
    """피드백 B1: '정보 부족' 조건마다 그 조건이 읽는 입력 항목 — 화면은 이 항목만 다시 물어 바로 다시 판정한다.
    '수동 확인'(해석이 필요한 조건·원문을 찾지 못한 조건)은 질문으로 풀 수 없어 넣지 않는다(기관 문의·원문 확인)."""
    conds = {}

    def walk(cs):
        for c in cs:
            conds[c.rule_id] = c
            for t in c.tracks or []:
                walk(t.conditions)
    walk(notice.layers[layer].conditions)
    ids = list(dict.fromkeys(list(result.unknown) + [u for t in result.tracks.values() for u in t.unknown]))
    out = []
    for rid in ids:
        c = conds.get(rid)
        if c is None or c.tracks:          # 순위 묶음 자체가 아니라 그 안의 조건을 묻는다
            continue
        fields = sorted({DERIVED_INPUT.get(f, f) for f in c.inputs})
        if fields:
            out.append({"rule_id": rid, "description": c.note, "source_ref": c.source_ref, "fields": fields})
    return out


@app.post("/evaluate")
def evaluate_one(req: EvaluateRequest):
    notice, d = _target(req.notice_id, req.sha256, req.layer)
    profile = _profile(req.profile, notice)
    if d is not None:
        import grading
        result, checks = grading.judge(d, profile, req.layer)
    else:
        result, checks = evaluate(profile, notice, req.layer), []
    get_store().count("judged")
    return dict(_result_json(result, notice, checks), basis=_basis(req, notice, d),
                questions=_questions(result, notice, req.layer))


@app.get("/match/form")
def match_form():
    """'내 조건으로 공고 찾기' 입력 양식(src/form_spec.py) — 화면은 이대로 그리고, 'master.' 항목은 저장 파일의 master에 넣는다."""
    import form_spec
    return form_spec.master_form()


def _master(raw: Dict[str, Any]):
    try:
        return master_from_dict(raw)
    except ProfileFormatError as e:
        raise HTTPException(422, str(e))


def _match_all(master):
    try:
        return match_all(master, ALL_NOTICES)
    except (TypeError, ValueError) as e:      # 항목 값의 형식 오류(예: 가구원수에 문자열)
        raise HTTPException(422, f"프로필 값 오류: {e}")


def _window_json(w) -> Dict[str, Any]:
    return {"label": w.label, "start": w.start.isoformat(), "end": w.end.isoformat()}


def _match_json(x, stat, sched) -> Dict[str, Any]:
    n, nid = x.notice, x.notice.notice_id
    shown = display(x.verdict)
    s = sched.get(nid)
    return {"notice_id": nid, "title": n.title, "layer": x.layer, "verdict": x.verdict,
            "issuer": n.meta.get("issuer"), "program": n.meta.get("program"),
            "announcement_date": n.announcement_date.isoformat(),
            "display": {"group": shown.group, "title": shown.title, "icon": shown.icon, "todo": shown.todo},
            "eligible_tracks": list(x.result.eligible_tracks), "schedule": _status_json(stat[nid]),
            "windows": [_window_json(w) for w in s.windows] if s else [], "schedule_note": s.note if s else None,
            "explanation": _explanation_json(explain(x.result, n))}


def _near_json(nm) -> Dict[str, Any]:
    x = nm.match
    return {"notice_id": x.notice.notice_id, "title": x.notice.title, "layer": x.layer, "condition": nm.description,
            "after": nm.after, "thresholds": [{"field": t.field, "label": t.label, "scope": t.scope, "current": t.current,
                                               "limit": t.limit, "review_limit": t.review_limit, "gap": t.gap}
                                              for t in nm.thresholds]}


@app.post("/match")
def match(req: MatchRequest):
    """전 공고 판정. matches는 판정 순서(충족 → 수동 확인 → 정보 부족 → 불충족)·공고일 늦은 순 — 화면이 접수 상태로 다시 묶는다.
    near_misses: 지원 불가 중 걸린 조건이 하나뿐인 것(금액 한도가 있으면 그 한도, src/whatif.py)."""
    master = _master(req.profile)
    at = _at(req.at)
    stat = statuses(list(ALL_NOTICES), at)
    matches = _match_all(master)
    if req.only_open:
        matches = [x for x in matches if stat[x.notice.notice_id].applicable]
    counts: Dict[str, int] = {}
    for x in matches:
        counts[x.verdict] = counts.get(x.verdict, 0) + 1
    sched = load_schedules()
    return {"at": at.isoformat(), "only_open": req.only_open, "counts": counts, "notices_total": len(ALL_NOTICES),
            "schedule_counts": {c: sum(1 for s in stat.values() if s.code == c) for c in (OPEN, UPCOMING, CLOSED)},
            "missing_inputs": missing_inputs(matches), "missing_fields": missing_fields(matches), "common_note": COMMON_NOTE, "whatif_caveat": whatif.CAVEAT,
            "matches": [_match_json(x, stat, sched) for x in matches],
            "near_misses": [_near_json(nm) for nm in whatif.near_misses(master, matches)]}


@app.post("/whatif")
def what_if(req: WhatIfRequest):
    """시나리오로 바꿔 전 공고를 다시 판정하고 전후를 비교한다(화면 3상태별 개수, 새로 지원 가능·빠지는 공고). 판정은 같은 엔진."""
    import form_spec
    master = _master(req.profile)
    if req.scenario in ("marry", "prenuptial"):
        prenuptial = req.scenario == "prenuptial"
        when = None if prenuptial else (req.marriage_date or now_kst().date())
        change = lambda m: whatif.marry(m, when, req.spouse_income, req.spouse_assets, req.spouse_car,  # noqa: E731
                                        req.spouse_has_home, req.dual_income, prenuptial=prenuptial)
    elif req.scenario == "move":
        if req.region not in form_spec.region_options()[1:]:
            raise HTTPException(422, f"옮길 거주지를 지역 표준 이름으로 주세요: {req.region!r}")
        change = lambda m: whatif.move(m, req.region)  # noqa: E731
    elif req.scenario == "separate":
        change = whatif.separate_household
    else:
        raise HTTPException(422, f"알 수 없는 시나리오: {req.scenario!r} (가능: {list(SCENARIOS)})")
    _match_all(master)                          # 형식 오류는 422로
    at = _at(req.at)
    stat = statuses(list(ALL_NOTICES), at)
    keep = (lambda x: stat[x.notice.notice_id].applicable) if req.only_open else None
    res = whatif.run_scenario(SCENARIOS[req.scenario], master, change, ALL_NOTICES, keep=keep)
    after = {(y.notice.notice_id, y.layer): y for y in match_all(change(master), ALL_NOTICES)}

    def lost(x):
        y = after[(x.notice.notice_id, x.layer)]
        why = explain(y.result, y.notice)
        return {"notice_id": x.notice.notice_id, "title": x.notice.title, "layer": x.layer,
                "reason": why.failed[0].description if why.failed else why.headline}

    return {"scenario": req.scenario, "name": res.name, "at": at.isoformat(), "only_open": req.only_open,
            "caveat": whatif.CAVEAT, "before": res.before, "after": res.after,
            "gained": [{"notice_id": x.notice.notice_id, "title": x.notice.title, "layer": x.layer} for x in res.gained],
            "lost": [lost(x) for x in res.lost]}
