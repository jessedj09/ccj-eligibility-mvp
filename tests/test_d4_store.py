# -*- coding: utf-8 -*-
"""test_d4_store.py — v3 ④-1: 공유 저장소(src/store.py)와 분석 입구(src/analysis.py).

- DB가 없거나 멈춰도 분석·판정 결과는 같다(NullStore, 닿지 않는 주소).
- 같은 원문은 저장된 분석을 다시 쓴다(엔진 판이 같을 때만). 작업은 LH·SH 공고에만, PDF는 작업을 넣을 때만.
- 실제 PostgreSQL 시험은 TEST_DATABASE_URL이 있을 때만(CI는 postgres 서비스, 로컬은 임시 스키마를 만들고 지운다).
"""
import hashlib
import os
import time
import uuid

import analysis
import draft
import grading
import pytest
import source_verify as sv
import store as S

TEST_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
needs_db = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL 없음 — 실제 DB 시험은 CI(postgres 서비스)에서")


class Ident:
    def __init__(self, issuer="LH", program="청년매입임대", announcement=None):
        self.issuer, self.program, self.announcement = issuer, program, announcement


class Recorder(S.NullStore):
    """저장소 호출을 기록하는 가짜 — 어떤 값을 언제 넣는지 본다."""
    available = True

    def __init__(self, snap=None):
        self.calls, self.snap = [], snap

    def __getattribute__(self, name):
        attr = object.__getattribute__(self, name)
        if name in ("save_notice", "save_analysis", "put_pdf", "enqueue", "latest_analysis"):
            def rec(*a, **k):
                self.calls.append((name, a, k))
                if name == "latest_analysis":
                    return self.snap
                return True
            return rec
        return attr


@pytest.fixture(scope="module")
def n12_bytes():
    return sv.pdf_path("N12").read_bytes()


def test_no_database_means_null_store(monkeypatch, tmp_path):
    monkeypatch.delenv(S.ENV, raising=False)
    monkeypatch.setattr(S, "SECRETS", tmp_path / "none.toml")
    S.reset_store(None)
    assert isinstance(S.get_store(), S.NullStore) and not S.get_store().available


def test_secrets_file_is_read_when_env_missing(monkeypatch, tmp_path):
    f = tmp_path / "secrets.toml"
    f.write_text('DATABASE_URL = "postgresql://u:p@example.invalid/db?sslmode=require"\n', encoding="utf-8")
    monkeypatch.delenv(S.ENV, raising=False)
    monkeypatch.setattr(S, "SECRETS", f)
    assert S.database_url().startswith("postgresql://u:p@example.invalid")
    monkeypatch.setenv(S.ENV, "postgresql://env/db")
    assert S.database_url() == "postgresql://env/db"


def test_unreachable_database_fails_fast_and_judging_still_works(monkeypatch):
    monkeypatch.setattr(S, "CONNECT_TIMEOUT", 2)
    s = S.Store("postgresql://nobody:x@127.0.0.1:1/none")
    assert s.latest_analysis("x", "v") is None and not s.available     # 실패 → 잠시 사용 안 함
    t = time.monotonic()
    assert s.enqueue("x", "enhance") is False and time.monotonic() - t < 0.5   # 장애 중에는 접속을 다시 시도하지 않는다


def test_analyze_without_store_equals_make_draft(n12_bytes):
    d = analysis.analyze(n12_bytes, Ident(), store=S.NullStore())
    ref = draft.make_draft(n12_bytes)
    assert d.status == ref.status and d.doc == ref.doc and d.held_conditions == ref.held_conditions


def test_analyze_saves_then_reuses_snapshot(n12_bytes):
    rec = Recorder()
    d = analysis.analyze(n12_bytes, Ident(), store=rec)
    names = [c[0] for c in rec.calls]
    assert names[:3] == ["latest_analysis", "save_notice", "save_analysis"]
    sha = hashlib.sha256(n12_bytes).hexdigest()
    _, (s_sha, version, snap, grade), _ = rec.calls[2]
    assert s_sha == sha and version == analysis.analysis_version() and snap["status"] == d.status
    # 저장본이 있으면 분석하지 않고 그대로 — 판정이 같다
    again = analysis.analyze(n12_bytes, Ident(), store=Recorder(snap=snap))
    assert again.doc == d.doc and grading.grades(again) == grading.grades(d)


def test_version_changes_with_code(monkeypatch, tmp_path):
    v = analysis.analysis_version()
    assert v.startswith("v3-") and v == analysis.analysis_version()
    fake = tmp_path / "src"
    fake.mkdir()
    for f in analysis.CODE:
        p = tmp_path / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes((analysis.ROOT / f).read_bytes())
    (tmp_path / "src" / "grading.py").write_bytes(b"# changed\n")
    monkeypatch.setattr(analysis, "ROOT", tmp_path)
    analysis.analysis_version.cache_clear()
    try:
        assert analysis.analysis_version() != v
    finally:
        analysis.analysis_version.cache_clear()


def test_follow_up_only_for_lh_sh_and_pdf_only_with_a_job(n12_bytes):
    d = draft.make_draft(n12_bytes)
    assert analysis.follow_up(d, None) is None and analysis.follow_up(d, "기타") is None
    blocked = draft.Draft(draft.BLOCKED, "핵심 값 보류", program="청년매입임대")
    assert analysis.follow_up(blocked, "LH") == ("enhance", 10)
    unsupported = draft.Draft(draft.UNSUPPORTED, "대상 아님", program="국민임대")
    assert analysis.follow_up(unsupported, "SH") == ("review", 1)
    assert analysis.follow_up(draft.Draft(draft.UNREADABLE, "스캔"), "LH") is None
    rec = Recorder()
    analysis.analyze(n12_bytes, Ident(issuer=None), store=rec)        # 기관을 모르는 파일 — PDF를 두지 않는다
    assert "put_pdf" not in [c[0] for c in rec.calls]


# ------------------------------------------------------------------ 실제 PostgreSQL
@pytest.fixture
def db():
    schema = "t_" + uuid.uuid4().hex[:10]
    s = S.Store(TEST_URL, schema=schema)
    assert s.migrate()
    yield s
    s._run(lambda c: c.execute(f'DROP SCHEMA "{schema}" CASCADE'))
    s.close()


@needs_db
def test_db_analysis_round_trip(db, n12_bytes):
    d = analysis.analyze(n12_bytes, Ident(), store=db)
    sha = hashlib.sha256(n12_bytes).hexdigest()
    snap = db.latest_analysis(sha, analysis.analysis_version())
    assert snap and snap["sha256"] == sha and draft.from_snapshot(snap).doc == d.doc
    assert db.latest_analysis(sha, "다른 판") is None
    assert db.migrate()                                                  # 두 번 불러도 그대로


@needs_db
def test_db_queue_claims_each_job_once(db):
    for sha in ("a", "b"):
        db.save_notice(sha, issuer="LH")
    assert db.enqueue("a", "enhance", priority=1) and db.enqueue("b", "enhance", priority=9)
    assert db.enqueue("a", "enhance") is False                           # 이미 대기 중
    first, second = db.claim("enhance"), db.claim("enhance")
    assert (first.sha256, second.sha256) == ("b", "a") and db.claim("enhance") is None
    for _ in range(S.MAX_ATTEMPTS - 1):                                  # 실패 → 다시 대기 → 상한이면 failed
        db.finish(second.id, False, "LLM 응답 없음")
        second = db.claim("enhance")
        assert second is not None
    db.finish(second.id, False, "LLM 응답 없음")
    assert db.claim("enhance") is None
    db.finish(first.id, True)
    assert db.enqueue("b", "enhance")                                     # 끝난 뒤에는 다시 넣을 수 있다


@needs_db
def test_db_pdf_limits(db, monkeypatch):
    db.save_notice("p1")
    assert db.put_pdf("p1", b"%PDF-1" * 10) and db.get_pdf("p1") == b"%PDF-1" * 10
    monkeypatch.setattr(S, "MAX_PDF", 5)
    assert db.put_pdf("p2", b"123456") is False
    monkeypatch.setattr(S, "MAX_PDF", 1000)
    monkeypatch.setattr(S, "MAX_PDF_TOTAL", 70)
    assert db.put_pdf("p3", b"x" * 20) is False                          # 합계 상한(60 + 20 > 70)
    assert db.delete_pdf("p1") and db.get_pdf("p1") is None and db.put_pdf("p3", b"x" * 20)
    db._run(lambda c: c.execute("UPDATE pdf_blobs SET expires_at = now() - interval '1 day'"))
    assert db.purge_expired() == 1


@needs_db
def test_db_usage_counts_without_personal_data(db):
    assert db.count("uploads") and db.count("uploads", 2)
    row = db._run(lambda c: c.execute("SELECT uploads, judged FROM usage_daily").fetchone())
    assert row == (3, 0)
    cols = db._run(lambda c: c.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema()").fetchall())
    assert not {"ip", "profile", "name", "birth"} & {c[0] for c in cols}
