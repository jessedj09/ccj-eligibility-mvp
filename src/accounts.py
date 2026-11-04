# -*- coding: utf-8 -*-
"""accounts.py — 회원가입·로그인과 '내 조건' 저장(2026-11-03 사용자 결정: 개인정보 서버 저장 허용).

- 가입: 이메일 + 비밀번호, 이메일 확인은 6자리 인증 코드(메일 발송은 src/mailer.py). 소셜 로그인 없음.
- 비밀번호는 scrypt 해시만, 인증 코드·세션 토큰은 SHA-256 해시만 저장한다(원문은 저장하지 않음).
- 내 조건은 ccj-profile/1(src/profile_io.py) 그대로, 사용자별로 여러 개(별칭·대표·작성 중/완료). 저장 전에 민감 항목(수급·장애·
  국가유공자 등 — SENSITIVE)을 빼고(판정 때만 입력), 나머지는 AES-GCM으로 암호화한다(키 CCJ_PROFILE_KEY, 없으면 저장 기능을 끈다).
- 동의: 이용약관·개인정보 수집·이용·국외 이전(Neon AWS 싱가포르) — 셋 다 필수, 동의 버전·일시를 남긴다.
- 파기: 탈퇴하면 즉시(계정·세션·조건·인증 코드 모두), 1년 넘게 로그인하지 않은 계정은 purge_inactive가 지운다.
- 저장소는 둘: PgRepo(DATABASE_URL — 운영) / MemoryRepo(시험). 공고 분석 저장소(src/store.py)와 테이블·코드를 섞지 않는다.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

CONSENT_VERSION = "2026-11-03"
CONSENTS = ("terms", "privacy", "overseas")      # 이용약관 · 개인정보 수집·이용 · 국외 이전 — 모두 필수
CODE_TTL = timedelta(minutes=10)
CODE_ATTEMPTS = 5
CODE_RESEND = timedelta(seconds=60)
SESSION_TTL = timedelta(days=30)
INACTIVE_DAYS = 365
MAX_PROFILES = 10
PASSWORD_MIN = 8
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
# 저장하지 않는 민감 항목(2026-11-03 사용자 결정) — 건강(장애)·수급·보훈·북한이탈·아동복지시설·한부모 지원 등 신분 정보
SENSITIVE = frozenset({"welfare_status", "parent_welfare_status", "housing_benefit_status", "housing_weak_type",
                       "disabled_spouse_qualifies", "livelihood_medical_recipient", "merit_person", "north_korean_defector",
                       "veteran_priority_notified", "child_facility_leaver", "is_supported_single_parent"})


class AccountError(Exception):
    """사용자에게 보여 줄 수 있는 오류(status: HTTP 상태)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL.match(e):
        raise AccountError(400, "이메일 주소 형식이 아닙니다.")
    return e


def check_password(pw: str) -> None:
    if len(pw or "") < PASSWORD_MIN or not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise AccountError(400, f"비밀번호는 {PASSWORD_MIN}자 이상, 영문과 숫자를 함께 써 주세요.")


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(dk).decode()


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, dk = stored.split("$")
        got = hashlib.scrypt(pw.encode("utf-8"), salt=base64.b64decode(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got, base64.b64decode(dk))
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ 암호화(내 조건)
class Cipher:
    """AES-GCM. key는 32바이트(urlsafe base64). 사용자 id를 추가 인증 데이터로 써서 다른 사용자 행으로 옮겨도 풀리지 않게."""

    def __init__(self, key_b64: str):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = base64.urlsafe_b64decode(key_b64 + "=" * (-len(key_b64) % 4))
        if len(key) != 32:
            raise ValueError("CCJ_PROFILE_KEY는 32바이트(base64)여야 합니다")
        self._aes = AESGCM(key)

    def seal(self, data: Dict, user_id: str) -> str:
        nonce = secrets.token_bytes(12)
        ct = self._aes.encrypt(nonce, json.dumps(data, ensure_ascii=False).encode("utf-8"), user_id.encode())
        return base64.b64encode(nonce + ct).decode()

    def open(self, blob: str, user_id: str) -> Dict:
        raw = base64.b64decode(blob)
        return json.loads(self._aes.decrypt(raw[:12], raw[12:], user_id.encode()).decode("utf-8"))


def cipher_from_env() -> Optional[Cipher]:
    key = os.environ.get("CCJ_PROFILE_KEY", "").strip()
    return Cipher(key) if key else None


def strip_sensitive(profile: Dict) -> Dict:
    """ccj-profile/1에서 민감 항목을 뺀 복사본(저장용). master에는 민감 항목이 없다."""
    out = dict(profile)
    out["common"] = {k: v for k, v in (profile.get("common") or {}).items() if k not in SENSITIVE}
    return out


def completeness(profile: Dict) -> Dict[str, int]:
    """입력 양식(form_spec.master_form) 항목 중 값이 있는 수 — 민감 항목은 세지 않는다('모름'이 B1 질문으로 이어진다)."""
    import form_spec
    names = [f["name"] for f in form_spec.master_form()["fields"] if f["name"] not in SENSITIVE]
    master, common = profile.get("master") or {}, profile.get("common") or {}
    filled = sum(1 for n in names if (master.get(n[7:]) if n.startswith("master.") else common.get(n)) not in (None, "", []))
    return {"filled": filled, "total": len(names)}


# ------------------------------------------------------------------ 저장소
class MemoryRepo:
    """시험용 — 같은 메서드를 PgRepo가 SQL로 구현한다."""

    def __init__(self):
        self.users: Dict[str, Dict] = {}
        self.codes: Dict[tuple, Dict] = {}
        self.sessions: Dict[str, Dict] = {}
        self.profiles: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    def user_by_email(self, email):
        return next((dict(u) for u in self.users.values() if u["email"] == email), None)

    def user_by_id(self, uid):
        u = self.users.get(uid)
        return dict(u) if u else None

    def create_user(self, email, pw_hash, consents, now):
        uid = str(uuid.uuid4())
        self.users[uid] = {"id": uid, "email": email, "pw_hash": pw_hash, "consents": consents, "created_at": now, "last_login": now}
        return uid

    def update_user(self, uid, **kw):
        self.users[uid].update(kw)

    def delete_user(self, uid):
        with self._lock:
            self.users.pop(uid, None)
            self.sessions = {k: s for k, s in self.sessions.items() if s["user_id"] != uid}
            self.profiles = {k: p for k, p in self.profiles.items() if p["user_id"] != uid}

    def inactive_users(self, before):
        return [u["id"] for u in self.users.values() if u["last_login"] < before]

    def put_code(self, email, purpose, row):
        self.codes[(email, purpose)] = dict(row)

    def get_code(self, email, purpose):
        c = self.codes.get((email, purpose))
        return dict(c) if c else None

    def bump_code(self, email, purpose):
        self.codes[(email, purpose)]["attempts"] += 1

    def delete_code(self, email, purpose):
        self.codes.pop((email, purpose), None)

    def delete_codes_for(self, email):
        self.codes = {k: c for k, c in self.codes.items() if k[0] != email}

    def create_session(self, token_hash, uid, expires):
        self.sessions[token_hash] = {"user_id": uid, "expires": expires}

    def session_user(self, token_hash, now):
        s = self.sessions.get(token_hash)
        return s["user_id"] if s and s["expires"] > now else None

    def delete_session(self, token_hash):
        self.sessions.pop(token_hash, None)

    def delete_sessions_of(self, uid):
        self.sessions = {k: s for k, s in self.sessions.items() if s["user_id"] != uid}

    def list_profiles(self, uid):
        return sorted((dict(p) for p in self.profiles.values() if p["user_id"] == uid), key=lambda p: p["updated_at"], reverse=True)

    def get_profile(self, uid, pid):
        p = self.profiles.get(pid)
        return dict(p) if p and p["user_id"] == uid else None

    def save_profile(self, row):
        self.profiles[row["id"]] = dict(row)

    def delete_profile(self, uid, pid):
        if self.get_profile(uid, pid):
            self.profiles.pop(pid)
            return True
        return False

    def clear_main(self, uid):
        for p in self.profiles.values():
            if p["user_id"] == uid:
                p["is_main"] = False


ACCOUNT_SCHEMA = """
CREATE TABLE IF NOT EXISTS acct_users (
    id uuid PRIMARY KEY, email text NOT NULL UNIQUE, pw_hash text NOT NULL,
    consents jsonb NOT NULL, created_at timestamptz NOT NULL, last_login timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS acct_codes (
    email text NOT NULL, purpose text NOT NULL, code_hash text NOT NULL, expires timestamptz NOT NULL,
    attempts int NOT NULL DEFAULT 0, sent_at timestamptz NOT NULL, payload jsonb, PRIMARY KEY (email, purpose)
);
CREATE TABLE IF NOT EXISTS acct_sessions (
    token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES acct_users(id) ON DELETE CASCADE, expires timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS acct_profiles (
    id uuid PRIMARY KEY, user_id uuid NOT NULL REFERENCES acct_users(id) ON DELETE CASCADE,
    alias text NOT NULL, is_main boolean NOT NULL DEFAULT false, status text NOT NULL,
    data_enc text NOT NULL, filled int NOT NULL, total int NOT NULL, updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS acct_profiles_user ON acct_profiles (user_id, updated_at DESC);
"""


class PgRepo:
    """PostgreSQL(표준 SQL만 — Neon 전용 기능 없음). 연결은 요청마다 짧게 연다(트래픽이 적고 Render 무료 요금제가 잠든다)."""

    def __init__(self, url: str, schema: Optional[str] = None):
        self.url, self.schema = url, schema
        with self._conn() as c:
            if schema:
                c.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            c.execute(ACCOUNT_SCHEMA)

    def _conn(self):
        import psycopg
        conn = psycopg.connect(self.url, connect_timeout=10, autocommit=True)
        if self.schema:
            conn.execute(f'SET search_path TO "{self.schema}"')
        return conn

    def _one(self, sql, args=(), cols=None):
        with self._conn() as c:
            row = c.execute(sql, args).fetchone()
        return dict(zip(cols, row)) if row and cols else row

    def _all(self, sql, args=(), cols=None):
        with self._conn() as c:
            return [dict(zip(cols, r)) for r in c.execute(sql, args).fetchall()]

    def _do(self, sql, args=()):
        with self._conn() as c:
            return c.execute(sql, args).rowcount

    U = ("id", "email", "pw_hash", "consents", "created_at", "last_login")

    def _user(self, where, arg):
        u = self._one(f"SELECT id::text, email, pw_hash, consents, created_at, last_login FROM acct_users WHERE {where} = %s",
                      (arg,), self.U)
        return u

    def user_by_email(self, email):
        return self._user("email", email)

    def user_by_id(self, uid):
        return self._user("id", uid)

    def create_user(self, email, pw_hash, consents, now):
        from psycopg.types.json import Jsonb
        uid = str(uuid.uuid4())
        self._do("INSERT INTO acct_users VALUES (%s, %s, %s, %s, %s, %s)", (uid, email, pw_hash, Jsonb(consents), now, now))
        return uid

    def update_user(self, uid, **kw):
        for k, v in kw.items():
            assert k in ("pw_hash", "last_login")
            self._do(f"UPDATE acct_users SET {k} = %s WHERE id = %s", (v, uid))

    def delete_user(self, uid):
        self._do("DELETE FROM acct_users WHERE id = %s", (uid,))       # 세션·조건은 ON DELETE CASCADE

    def inactive_users(self, before):
        return [r["id"] for r in self._all("SELECT id::text FROM acct_users WHERE last_login < %s", (before,), ("id",))]

    C = ("code_hash", "expires", "attempts", "sent_at", "payload")

    def put_code(self, email, purpose, row):
        from psycopg.types.json import Jsonb
        self._do("INSERT INTO acct_codes VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (email, purpose) DO UPDATE SET "
                 "code_hash = EXCLUDED.code_hash, expires = EXCLUDED.expires, attempts = EXCLUDED.attempts, "
                 "sent_at = EXCLUDED.sent_at, payload = EXCLUDED.payload",
                 (email, purpose, row["code_hash"], row["expires"], row["attempts"], row["sent_at"], Jsonb(row.get("payload"))))

    def get_code(self, email, purpose):
        return self._one("SELECT code_hash, expires, attempts, sent_at, payload FROM acct_codes WHERE email = %s AND purpose = %s",
                         (email, purpose), self.C)

    def bump_code(self, email, purpose):
        self._do("UPDATE acct_codes SET attempts = attempts + 1 WHERE email = %s AND purpose = %s", (email, purpose))

    def delete_code(self, email, purpose):
        self._do("DELETE FROM acct_codes WHERE email = %s AND purpose = %s", (email, purpose))

    def delete_codes_for(self, email):
        self._do("DELETE FROM acct_codes WHERE email = %s", (email,))

    def create_session(self, token_hash, uid, expires):
        self._do("INSERT INTO acct_sessions VALUES (%s, %s, %s)", (token_hash, uid, expires))

    def session_user(self, token_hash, now):
        r = self._one("SELECT user_id::text FROM acct_sessions WHERE token_hash = %s AND expires > %s", (token_hash, now))
        return r[0] if r else None

    def delete_session(self, token_hash):
        self._do("DELETE FROM acct_sessions WHERE token_hash = %s", (token_hash,))

    def delete_sessions_of(self, uid):
        self._do("DELETE FROM acct_sessions WHERE user_id = %s", (uid,))

    P = ("id", "user_id", "alias", "is_main", "status", "data_enc", "filled", "total", "updated_at")
    _PSEL = "SELECT id::text, user_id::text, alias, is_main, status, data_enc, filled, total, updated_at FROM acct_profiles"

    def list_profiles(self, uid):
        return self._all(self._PSEL + " WHERE user_id = %s ORDER BY updated_at DESC", (uid,), self.P)

    def get_profile(self, uid, pid):
        try:
            uuid.UUID(pid)
        except ValueError:
            return None
        return self._one(self._PSEL + " WHERE user_id = %s AND id = %s", (uid, pid), self.P)

    def save_profile(self, row):
        self._do("INSERT INTO acct_profiles VALUES (%(id)s, %(user_id)s, %(alias)s, %(is_main)s, %(status)s, %(data_enc)s, "
                 "%(filled)s, %(total)s, %(updated_at)s) ON CONFLICT (id) DO UPDATE SET alias = EXCLUDED.alias, "
                 "is_main = EXCLUDED.is_main, status = EXCLUDED.status, data_enc = EXCLUDED.data_enc, filled = EXCLUDED.filled, "
                 "total = EXCLUDED.total, updated_at = EXCLUDED.updated_at", row)

    def delete_profile(self, uid, pid):
        return self.get_profile(uid, pid) is not None and \
            self._do("DELETE FROM acct_profiles WHERE user_id = %s AND id = %s", (uid, pid)) > 0

    def clear_main(self, uid):
        self._do("UPDATE acct_profiles SET is_main = false WHERE user_id = %s", (uid,))


# ------------------------------------------------------------------ 계정 서비스
@dataclass
class Session:
    token: str
    user_id: str


class Accounts:
    def __init__(self, repo, mailer, cipher: Optional[Cipher], clock=_now):
        self.repo, self.mailer, self.cipher, self.clock = repo, mailer, cipher, clock

    # --- 인증 코드
    def _send_code(self, email: str, purpose: str, payload: Optional[Dict] = None) -> None:
        now = self.clock()
        old = self.repo.get_code(email, purpose)
        if old and now - old["sent_at"] < CODE_RESEND:
            raise AccountError(429, "인증 코드를 방금 보냈습니다. 1분 뒤에 다시 요청해 주세요.")
        code = f"{secrets.randbelow(10 ** 6):06d}"
        self.repo.put_code(email, purpose, {"code_hash": _sha(f"{email}:{purpose}:{code}"), "expires": now + CODE_TTL,
                                            "attempts": 0, "sent_at": now, "payload": payload})
        what = "회원가입" if purpose == "signup" else "비밀번호 재설정"
        self.mailer.send(email, f"[청약 포청천] {what} 인증 코드 {code}",
                         f"{what} 인증 코드는 {code} 입니다. 10분 안에 화면에 입력해 주세요.\n"
                         "요청하지 않았다면 이 메일을 무시하세요.")

    def _take_code(self, email: str, purpose: str, code: str) -> Dict:
        row = self.repo.get_code(email, purpose)
        if not row or row["expires"] < self.clock():
            raise AccountError(400, "인증 코드가 없거나 만료됐습니다. 다시 요청해 주세요.")
        if row["attempts"] >= CODE_ATTEMPTS:
            self.repo.delete_code(email, purpose)
            raise AccountError(400, "인증 코드를 여러 번 틀렸습니다. 다시 요청해 주세요.")
        if not hmac.compare_digest(row["code_hash"], _sha(f"{email}:{purpose}:{(code or '').strip()}")):
            self.repo.bump_code(email, purpose)
            raise AccountError(400, "인증 코드가 맞지 않습니다.")
        self.repo.delete_code(email, purpose)
        return row

    def _session(self, uid: str) -> Session:
        token = secrets.token_urlsafe(32)
        self.repo.create_session(_sha(token), uid, self.clock() + SESSION_TTL)
        return Session(token, uid)

    # --- 가입·로그인
    def signup_start(self, email: str, password: str, consents: Dict[str, bool]) -> None:
        email = normalize_email(email)
        check_password(password)
        missing = [k for k in CONSENTS if not consents.get(k)]
        if missing:
            raise AccountError(400, "필수 동의 항목(이용약관·개인정보 수집·이용·국외 이전)에 모두 동의해 주세요.")
        if self.repo.user_by_email(email):
            raise AccountError(409, "이미 가입된 이메일입니다. 로그인하거나 비밀번호를 재설정해 주세요.")
        now = self.clock()
        self._send_code(email, "signup", {"pw_hash": hash_password(password),
                                          "consents": {k: now.isoformat() for k in CONSENTS} | {"version": CONSENT_VERSION}})

    def signup_verify(self, email: str, code: str) -> Session:
        email = normalize_email(email)
        row = self._take_code(email, "signup", code)
        if self.repo.user_by_email(email):
            raise AccountError(409, "이미 가입된 이메일입니다.")
        uid = self.repo.create_user(email, row["payload"]["pw_hash"], row["payload"]["consents"], self.clock())
        return self._session(uid)

    def login(self, email: str, password: str) -> Session:
        try:
            email = normalize_email(email)
        except AccountError:
            raise AccountError(401, "이메일 또는 비밀번호가 맞지 않습니다.") from None
        u = self.repo.user_by_email(email)
        if not u or not verify_password(password or "", u["pw_hash"]):
            raise AccountError(401, "이메일 또는 비밀번호가 맞지 않습니다.")
        self.repo.update_user(u["id"], last_login=self.clock())
        return self._session(u["id"])

    def logout(self, token: str) -> None:
        self.repo.delete_session(_sha(token))

    def reset_start(self, email: str) -> None:
        """가입 여부를 드러내지 않는다 — 가입된 이메일일 때만 메일을 보내고 응답은 같다."""
        email = normalize_email(email)
        if self.repo.user_by_email(email):
            self._send_code(email, "reset")

    def reset_verify(self, email: str, code: str, new_password: str) -> Session:
        email = normalize_email(email)
        check_password(new_password)
        self._take_code(email, "reset", code)
        u = self.repo.user_by_email(email)
        if not u:
            raise AccountError(400, "인증 코드가 없거나 만료됐습니다. 다시 요청해 주세요.")
        self.repo.update_user(u["id"], pw_hash=hash_password(new_password), last_login=self.clock())
        self.repo.delete_sessions_of(u["id"])          # 다른 기기의 로그인은 끊는다
        return self._session(u["id"])

    def user_of(self, token: Optional[str]) -> str:
        uid = self.repo.session_user(_sha(token), self.clock()) if token else None
        if not uid:
            raise AccountError(401, "로그인이 필요합니다.")
        return uid

    def me(self, uid: str) -> Dict:
        u = self.repo.user_by_id(uid)
        return {"email": u["email"], "created_at": u["created_at"].isoformat(), "consents": u["consents"]}

    def withdraw(self, uid: str) -> None:
        """탈퇴 — 계정·세션·조건·인증 코드를 즉시 지운다."""
        u = self.repo.user_by_id(uid)
        if u:
            self.repo.delete_codes_for(u["email"])
        self.repo.delete_user(uid)

    def purge_inactive(self) -> int:
        ids = self.repo.inactive_users(self.clock() - timedelta(days=INACTIVE_DAYS))
        for uid in ids:
            self.withdraw(uid)
        return len(ids)

    # --- 내 조건
    def _need_cipher(self) -> Cipher:
        if self.cipher is None:
            raise AccountError(503, "내 조건 저장 기능이 아직 설정되지 않았습니다.")
        return self.cipher

    def _summary(self, p: Dict) -> Dict:
        return {"id": p["id"], "alias": p["alias"], "is_main": p["is_main"], "status": p["status"],
                "filled": p["filled"], "total": p["total"], "updated_at": p["updated_at"].isoformat()}

    def list_profiles(self, uid: str) -> List[Dict]:
        return [self._summary(p) for p in self.repo.list_profiles(uid)]

    def get_profile(self, uid: str, pid: str) -> Dict:
        p = self.repo.get_profile(uid, pid)
        if not p:
            raise AccountError(404, "그 조건을 찾을 수 없습니다.")
        return self._summary(p) | {"profile": self._need_cipher().open(p["data_enc"], uid)}

    def save_profile(self, uid: str, alias: str, profile: Dict, status: str = "done", is_main: bool = False,
                     pid: Optional[str] = None) -> Dict:
        from profile_io import SCHEMA, ProfileFormatError, master_from_dict
        cipher = self._need_cipher()
        alias = (alias or "").strip()[:40] or "내 조건"
        if status not in ("draft", "done"):
            raise AccountError(400, "상태는 작성 중(draft) 또는 완료(done)입니다.")
        if not isinstance(profile, dict) or profile.get("schema") != SCHEMA:
            raise AccountError(400, f"조건 형식은 {SCHEMA}입니다.")
        data = strip_sensitive(profile)
        if status == "done":
            try:
                master_from_dict(data)                # 판정에 쓸 수 있는 조건인지(작성 중이면 검사하지 않음)
            except ProfileFormatError as e:
                raise AccountError(400, f"조건을 읽을 수 없습니다: {e}") from None
        if pid is None:
            if len(self.repo.list_profiles(uid)) >= MAX_PROFILES:
                raise AccountError(400, f"내 조건은 {MAX_PROFILES}개까지 저장할 수 있습니다.")
            pid = str(uuid.uuid4())
            first = not self.repo.list_profiles(uid)
        else:
            if not self.repo.get_profile(uid, pid):
                raise AccountError(404, "그 조건을 찾을 수 없습니다.")
            first = False
        if is_main or first:
            self.repo.clear_main(uid)
        c = completeness(data)
        self.repo.save_profile({"id": pid, "user_id": uid, "alias": alias, "is_main": bool(is_main or first), "status": status,
                                "data_enc": cipher.seal(data, uid), "filled": c["filled"], "total": c["total"],
                                "updated_at": self.clock()})
        return self.get_profile(uid, pid)

    def delete_profile(self, uid: str, pid: str) -> None:
        if not self.repo.delete_profile(uid, pid):
            raise AccountError(404, "그 조건을 찾을 수 없습니다.")
