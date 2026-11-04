# -*- coding: utf-8 -*-
"""회원가입·로그인·내 조건 API(src/accounts.py). 로그인 토큰은 Authorization: Bearer — 화면(Next.js)은 httpOnly 쿠키에 두고 중계한다.

    POST /auth/signup/start   {email, password, consents{terms,privacy,overseas}}  → 인증 코드 메일
    POST /auth/signup/verify  {email, code}                                     → {token}
    POST /auth/login          {email, password}                                 → {token}
    POST /auth/logout
    POST /auth/password/start {email}  ·  POST /auth/password/verify {email, code, new_password} → {token}
    GET /me · DELETE /me(탈퇴 — 즉시 파기)
    GET/POST /me/profiles · GET/PUT/DELETE /me/profiles/{id} · POST /me/profiles/{id}/match(저장한 조건으로 전 공고 판정)
요청 본문(이메일·조건)은 로그에 쓰지 않는다. 계정 저장소가 없으면(DATABASE_URL 없음·CCJ_STORE=off) 503.
"""
import threading
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import accounts as A
from mailer import MailUnavailable, mailer_from_env

router = APIRouter()
_accounts: Optional[A.Accounts] = None
_lock = threading.Lock()
_fails: Dict[str, list] = {}          # 이메일별 로그인 실패 시각(프로세스 메모리) — 15분에 10번이면 잠시 막는다
FAIL_WINDOW, FAIL_MAX = 15 * 60, 10


def get_accounts() -> Optional[A.Accounts]:
    global _accounts
    with _lock:
        if _accounts is None:
            # 공유 저장소와 같은 DB·같은 스위치를 따른다 — 저장소가 없으면(NullStore: DATABASE_URL 없음·CCJ_STORE=off·시험) 계정 기능도 없다.
            # 시험(conftest가 NullStore로 바꿔 둔다)이 운영 DB에 닿지 않게.
            from store import NullStore, get_store
            st = get_store()
            if type(st) is NullStore:
                return None
            try:
                _accounts = A.Accounts(A.PgRepo(st.url), mailer_from_env(), A.cipher_from_env())
            except Exception:      # noqa: BLE001 — DB에 닿지 않으면 계정 기능만 멈춘다(판정은 그대로)
                return None
        return _accounts


def reset_accounts(acc: Optional[A.Accounts] = None) -> None:
    """시험용 — MemoryRepo·MemoryMailer로 바꿔 끼운다."""
    global _accounts
    with _lock:
        _accounts = acc
        _fails.clear()


def _acc() -> A.Accounts:
    acc = get_accounts()
    if acc is None:
        raise HTTPException(503, "회원 기능을 지금 쓸 수 없습니다.")
    return acc


def _call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except A.AccountError as e:
        raise HTTPException(e.status, e.message) from None
    except MailUnavailable:
        raise HTTPException(503, "인증 메일을 보낼 수 없습니다. 잠시 뒤 다시 시도해 주세요.") from None


def _token(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _uid(authorization: Optional[str]) -> str:
    return _call(_acc().user_of, _token(authorization))


class SignupStart(BaseModel):
    email: str
    password: str
    consents: Dict[str, bool] = {}


class CodeBody(BaseModel):
    email: str
    code: str


class Login(BaseModel):
    email: str
    password: str


class ResetStart(BaseModel):
    email: str


class ResetVerify(BaseModel):
    email: str
    code: str
    new_password: str


class ProfileBody(BaseModel):
    alias: str = "내 조건"
    profile: Dict[str, Any]
    status: str = "done"
    is_main: bool = False


class MatchBody(BaseModel):
    at: Optional[str] = None
    only_open: bool = False


@router.post("/auth/signup/start")
def signup_start(req: SignupStart):
    _call(_acc().signup_start, req.email, req.password, req.consents)
    return {"sent": True}


@router.post("/auth/signup/verify")
def signup_verify(req: CodeBody):
    s = _call(_acc().signup_verify, req.email, req.code)
    return {"token": s.token}


@router.post("/auth/login")
def login(req: Login):
    key, now = (req.email or "").strip().lower(), time.time()
    recent = [t for t in _fails.get(key, []) if now - t < FAIL_WINDOW]
    if len(recent) >= FAIL_MAX:
        raise HTTPException(429, "로그인 시도가 너무 많습니다. 15분 뒤 다시 시도하거나 비밀번호를 재설정해 주세요.")
    try:
        s = _acc().login(req.email, req.password)
    except A.AccountError as e:
        _fails[key] = recent + [now]
        raise HTTPException(e.status, e.message) from None
    _fails.pop(key, None)
    return {"token": s.token}


@router.post("/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    tok = _token(authorization)
    if tok:
        _acc().logout(tok)
    return {"ok": True}


@router.post("/auth/password/start")
def reset_start(req: ResetStart):
    _call(_acc().reset_start, req.email)
    return {"sent": True}          # 가입 여부와 관계없이 같은 응답


@router.post("/auth/password/verify")
def reset_verify(req: ResetVerify):
    s = _call(_acc().reset_verify, req.email, req.code, req.new_password)
    return {"token": s.token}


@router.get("/me")
def me(authorization: Optional[str] = Header(None)):
    uid = _uid(authorization)
    return _acc().me(uid) | {"profiles": _acc().list_profiles(uid), "profile_saving": _acc().cipher is not None,
                             "not_saved": sorted(A.SENSITIVE)}


@router.delete("/me")
def withdraw(authorization: Optional[str] = Header(None)):
    _acc().withdraw(_uid(authorization))
    return {"deleted": True}


@router.get("/me/profiles")
def list_profiles(authorization: Optional[str] = Header(None)):
    return {"profiles": _acc().list_profiles(_uid(authorization))}


@router.post("/me/profiles")
def create_profile(req: ProfileBody, authorization: Optional[str] = Header(None)):
    uid = _uid(authorization)
    return _call(_acc().save_profile, uid, req.alias, req.profile, req.status, req.is_main)


@router.get("/me/profiles/{pid}")
def get_profile(pid: str, authorization: Optional[str] = Header(None)):
    return _call(_acc().get_profile, _uid(authorization), pid)


@router.put("/me/profiles/{pid}")
def update_profile(pid: str, req: ProfileBody, authorization: Optional[str] = Header(None)):
    uid = _uid(authorization)
    return _call(_acc().save_profile, uid, req.alias, req.profile, req.status, req.is_main, pid)


@router.delete("/me/profiles/{pid}")
def delete_profile(pid: str, authorization: Optional[str] = Header(None)):
    _call(_acc().delete_profile, _uid(authorization), pid)
    return {"deleted": True}


@router.post("/me/profiles/{pid}/match")
def match_profile(pid: str, req: MatchBody, authorization: Optional[str] = Header(None)):
    """저장한 조건으로 전 공고 판정 — /match와 같은 판정(민감 항목은 저장하지 않으므로 그 항목이 필요한 계층은 '추가 정보 필요')."""
    from api import main
    p = _call(_acc().get_profile, _uid(authorization), pid)
    if p["status"] != "done":
        raise HTTPException(400, "작성 중인 조건입니다. 완료한 뒤 판정할 수 있습니다.")
    return main.match(main.MatchRequest(profile=p["profile"], at=req.at, only_open=req.only_open))
