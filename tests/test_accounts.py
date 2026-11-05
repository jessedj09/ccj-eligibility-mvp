# -*- coding: utf-8 -*-
"""test_accounts.py — 회원가입·로그인·내 조건 저장(src/accounts.py, api/accounts_api.py, 2026-11-03 사용자 결정).

- 가입은 이메일 + 비밀번호 + 6자리 인증 코드(메일), 필수 동의 3개(이용약관·개인정보·국외 이전). 비밀번호·코드·토큰은 해시만 저장.
- 내 조건은 ccj-profile/1을 민감 항목을 뺀 뒤 암호화해 저장, 다른 사용자는 볼 수 없고, 탈퇴하면 즉시 지운다.
- 저장한 조건으로 판정한 결과는 같은 조건을 /match에 직접 보낸 결과와 같다(민감 항목이 없는 조건).
- 실제 PostgreSQL 시험은 TEST_DATABASE_URL이 있을 때만(CI postgres 서비스) — 임시 스키마를 만들고 지운다.
"""
import base64
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import accounts as A
import pytest
from fastapi.testclient import TestClient
from mailer import MemoryMailer

import api.accounts_api as AA
import api.main as api

KEY = base64.urlsafe_b64encode(b"k" * 32).decode()
CONSENTS = {"terms": True, "privacy": True, "overseas": True}
PROFILE = {"schema": "ccj-profile/1",
           "master": {"birth_date": "1995-03-01", "home_self": "무주택", "home_household": "무주택",
                      "income_household": 3_000_000, "income_self": 3_000_000, "assets_household": 50_000_000,
                      "assets_self": 50_000_000, "car_household": 0, "car_self": 0},
           "common": {"marital_status": "미혼", "household_size": 1, "residence_area": "서울특별시",
                      "welfare_status": "해당없음", "housing_weak_type": "장애인"}}


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t


@pytest.fixture
def env():
    clock, mail = Clock(), MemoryMailer()
    acc = A.Accounts(A.MemoryRepo(), mail, A.Cipher(KEY), clock)
    AA.reset_accounts(acc)
    yield acc, mail, clock, TestClient(api.app)
    AA.reset_accounts(None)


def code_of(mail, n=-1):
    return re.search(r"코드는 (\d{6})", mail.outbox[n][2]).group(1)


def signup(client, mail, clock, email="a@example.com", pw="abcd1234"):
    assert client.post("/auth/signup/start", json={"email": email, "password": pw, "consents": CONSENTS}).status_code == 200
    r = client.post("/auth/signup/verify", json={"email": email, "code": code_of(mail)})
    assert r.status_code == 200, r.text
    clock.t += timedelta(minutes=2)
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_signup_needs_code_consents_and_strong_password(env):
    acc, mail, clock, c = env
    assert c.post("/auth/signup/start", json={"email": "a@example.com", "password": "abcd1234",
                                               "consents": {"terms": True, "privacy": True}}).status_code == 400
    assert c.post("/auth/signup/start", json={"email": "a@example.com", "password": "short1", "consents": CONSENTS}).status_code == 400
    assert c.post("/auth/signup/start", json={"email": "not-an-email", "password": "abcd1234", "consents": CONSENTS}).status_code == 400
    assert c.post("/auth/signup/start", json={"email": "A@Example.com", "password": "abcd1234", "consents": CONSENTS}).status_code == 200
    assert c.post("/auth/signup/start", json={"email": "a@example.com", "password": "abcd1234",
                                               "consents": CONSENTS}).status_code == 429     # 1분 안에 다시 요청
    code = code_of(mail)
    wrong = "000000" if code != "000000" else "111111"
    assert c.post("/auth/signup/verify", json={"email": "a@example.com", "code": wrong}).status_code == 400
    r = c.post("/auth/signup/verify", json={"email": "a@example.com", "code": code})
    assert r.status_code == 200 and r.json()["token"]
    user = acc.repo.user_by_email("a@example.com")
    assert user["pw_hash"].startswith("scrypt$") and "abcd1234" not in str(user)
    assert set(A.CONSENTS) <= set(user["consents"]) and user["consents"]["version"] == A.CONSENT_VERSION
    assert c.post("/auth/signup/start", json={"email": "a@example.com", "password": "abcd1234",
                                               "consents": CONSENTS}).status_code == 409


def test_code_expires_and_locks_after_attempts(env):
    acc, mail, clock, c = env
    c.post("/auth/signup/start", json={"email": "b@example.com", "password": "abcd1234", "consents": CONSENTS})
    code = code_of(mail)
    for _ in range(A.CODE_ATTEMPTS):
        c.post("/auth/signup/verify", json={"email": "b@example.com", "code": "999999" if code != "999999" else "888888"})
    assert c.post("/auth/signup/verify", json={"email": "b@example.com", "code": code}).status_code == 400   # 잠김
    clock.t += timedelta(minutes=2)
    c.post("/auth/signup/start", json={"email": "b@example.com", "password": "abcd1234", "consents": CONSENTS})
    clock.t += A.CODE_TTL + timedelta(seconds=1)
    assert c.post("/auth/signup/verify", json={"email": "b@example.com", "code": code_of(mail)}).status_code == 400  # 만료


def test_login_logout_and_password_reset(env):
    acc, mail, clock, c = env
    h = signup(c, mail, clock)
    assert c.get("/me", headers=h).json()["email"] == "a@example.com"
    assert c.post("/auth/login", json={"email": "a@example.com", "password": "wrong999"}).status_code == 401
    assert c.post("/auth/login", json={"email": "nobody@example.com", "password": "abcd1234"}).status_code == 401
    tok = c.post("/auth/login", json={"email": "a@example.com", "password": "abcd1234"}).json()["token"]
    c.post("/auth/logout", headers={"Authorization": f"Bearer {tok}"})
    assert c.get("/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    # 재설정: 가입 안 한 주소에도 같은 응답(메일은 보내지 않음)
    n = len(mail.outbox)
    assert c.post("/auth/password/start", json={"email": "nobody@example.com"}).status_code == 200 and len(mail.outbox) == n
    assert c.post("/auth/password/start", json={"email": "a@example.com"}).status_code == 200
    r = c.post("/auth/password/verify", json={"email": "a@example.com", "code": code_of(mail), "new_password": "newpass99"})
    assert r.status_code == 200
    assert c.get("/me", headers=h).status_code == 401                     # 다른 로그인은 끊긴다
    assert c.post("/auth/login", json={"email": "a@example.com", "password": "newpass99"}).status_code == 200


def test_login_rate_limit(env):
    acc, mail, clock, c = env
    signup(c, mail, clock)
    for _ in range(AA.FAIL_MAX):
        c.post("/auth/login", json={"email": "a@example.com", "password": "wrong999"})
    assert c.post("/auth/login", json={"email": "a@example.com", "password": "abcd1234"}).status_code == 429


def test_profiles_are_encrypted_without_sensitive_fields_and_private(env):
    acc, mail, clock, c = env
    h = signup(c, mail, clock)
    r = c.post("/me/profiles", json={"alias": "나", "profile": PROFILE}, headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["is_main"] and p["status"] == "done" and 0 < p["filled"] < p["total"]
    assert "housing_weak_type" not in p["profile"]["common"] and "welfare_status" not in p["profile"]["common"]
    row = acc.repo.profiles[p["id"]]
    assert "서울특별시" not in row["data_enc"] and "1995" not in row["data_enc"]          # 암호문
    # 다른 사용자는 볼 수 없다
    h2 = signup(c, mail, clock, email="other@example.com")
    assert c.get(f"/me/profiles/{p['id']}", headers=h2).status_code == 404
    assert c.delete(f"/me/profiles/{p['id']}", headers=h2).status_code == 404
    assert c.get("/me/profiles", headers=h2).json()["profiles"] == []
    # 두 번째 조건을 대표로
    q = c.post("/me/profiles", json={"alias": "배우자와 함께", "profile": PROFILE, "is_main": True}, headers=h).json()
    mains = {x["alias"]: x["is_main"] for x in c.get("/me/profiles", headers=h).json()["profiles"]}
    assert mains == {"나": False, "배우자와 함께": True}
    # 작성 중은 형식만 보고 저장, 판정은 완료한 뒤
    d = c.post("/me/profiles", json={"alias": "작성 중", "profile": {"schema": "ccj-profile/1", "master": {}, "common": {}},
                                      "status": "draft"}, headers=h).json()
    assert c.post(f"/me/profiles/{d['id']}/match", json={}, headers=h).status_code == 400
    assert c.put(f"/me/profiles/{q['id']}", json={"alias": "수정", "profile": PROFILE}, headers=h).json()["alias"] == "수정"


def test_stored_profile_match_equals_direct_match(env):
    acc, mail, clock, c = env
    h = signup(c, mail, clock)
    pid = c.post("/me/profiles", json={"alias": "나", "profile": PROFILE}, headers=h).json()["id"]
    stored = c.post(f"/me/profiles/{pid}/match", json={"at": "2026-10-14T00:00:00"}, headers=h).json()
    direct = c.post("/match", json={"profile": A.strip_sensitive(PROFILE), "at": "2026-10-14T00:00:00"}).json()
    assert stored["counts"] == direct["counts"] and len(stored["matches"]) == len(direct["matches"])


def test_withdraw_deletes_everything_and_inactive_purge(env):
    acc, mail, clock, c = env
    h = signup(c, mail, clock)
    c.post("/me/profiles", json={"alias": "나", "profile": PROFILE}, headers=h)
    assert c.delete("/me", headers=h).json() == {"deleted": True}
    assert not acc.repo.users and not acc.repo.profiles and not acc.repo.sessions
    assert c.get("/me", headers=h).status_code == 401
    # 1년 넘게 로그인하지 않은 계정은 지운다
    signup(c, mail, clock, email="old@example.com")
    clock.t += timedelta(days=A.INACTIVE_DAYS + 1)
    signup(c, mail, clock, email="new@example.com")
    assert acc.purge_inactive() == 1
    assert {u["email"] for u in acc.repo.users.values()} == {"new@example.com"}


def test_no_store_or_key_means_503():
    """공유 저장소가 없으면(conftest가 NullStore) 계정 기능은 503 — 시험이 운영 DB에 닿지 않는다."""
    AA.reset_accounts(None)
    c = TestClient(api.app)
    assert c.post("/auth/login", json={"email": "a@example.com", "password": "abcd1234"}).status_code == 503
    assert AA.get_accounts() is None
    acc = A.Accounts(A.MemoryRepo(), MemoryMailer(), None, Clock())
    with pytest.raises(A.AccountError) as e:
        acc.save_profile("u", "x", PROFILE)
    assert e.value.status == 503


def test_cipher_binds_user_id():
    ci = A.Cipher(KEY)
    blob = ci.seal({"a": 1}, "user-1")
    assert ci.open(blob, "user-1") == {"a": 1}
    with pytest.raises(Exception):
        ci.open(blob, "user-2")


TEST_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


@pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL 없음(실제 PostgreSQL 시험은 CI에서)")
def test_postgres_repo_round_trip():
    import psycopg
    schema = f"acct_test_{uuid.uuid4().hex[:8]}"
    try:
        clock, mail = Clock(), MemoryMailer()
        acc = A.Accounts(A.PgRepo(TEST_URL, schema=schema), mail, A.Cipher(KEY), clock)
        acc.signup_start("pg@example.com", "abcd1234", CONSENTS)
        s = acc.signup_verify("pg@example.com", code_of(mail))
        uid = acc.user_of(s.token)
        p = acc.save_profile(uid, "나", PROFILE)
        assert acc.get_profile(uid, p["id"])["profile"]["master"]["birth_date"] == "1995-03-01"
        assert [x["alias"] for x in acc.list_profiles(uid)] == ["나"]
        acc.withdraw(uid)
        assert acc.repo.user_by_id(uid) is None and acc.repo.list_profiles(uid) == []
    finally:
        with psycopg.connect(TEST_URL, autocommit=True) as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_e2e_switches_file_mailer_and_memory_accounts(monkeypatch, tmp_path):
    """화면 점검 전용 스위치 — 저장소가 없을 때만 메모리 회원 저장소, 메일은 파일(인증 코드를 꺼내는 HTTP 경로는 없다)."""
    import mailer
    path = tmp_path / "sub" / "mail.txt"
    monkeypatch.setenv("CCJ_MAIL_BACKEND", "file")
    monkeypatch.setenv("CCJ_MAIL_FILE", str(path))
    m = mailer.mailer_from_env()
    m.send("a@example.com", "s", "코드는 123456 입니다")
    assert path.read_text(encoding="utf-8").startswith("to=a@example.com\n")
    monkeypatch.setenv("CCJ_ACCOUNTS_MEMORY", "1")
    monkeypatch.setenv("CCJ_PROFILE_KEY", KEY)
    AA.reset_accounts(None)
    try:
        acc = AA.get_accounts()
        assert isinstance(acc.repo, A.MemoryRepo) and acc.cipher is not None
    finally:
        AA.reset_accounts(None)
    monkeypatch.delenv("CCJ_ACCOUNTS_MEMORY")
    assert AA.get_accounts() is None
