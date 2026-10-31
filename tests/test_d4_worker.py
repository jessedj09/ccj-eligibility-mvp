# -*- coding: utf-8 -*-
"""test_d4_worker.py — v3 ④-3: 운영자 PC 보강 작업기(tools/worker.py).

- 작업기는 보관된 PDF를 LLM 슬롯과 함께 다시 분석해, 나아졌을 때만 새 분석으로 저장한다.
- 자동 확정이면 PDF를 지우고, 확인할 곳이 남으면 운영자 검토로 넘긴다. PDF가 없으면 실패로 기록.
- LLM 슬롯이 아무것도 못 채우면 결과는 결정론 분석과 같다(슬롯 연결이 판정을 바꾸지 않음).
- Ollama가 꺼져 있으면 작업을 가져가지 않는다.
"""
import hashlib
import os
import sys
import uuid
from pathlib import Path

import analysis
import draft
import pytest
import source_verify as sv
import store as S

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import llm_slot as L  # noqa: E402
import worker  # noqa: E402

TEST_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


class FakeSlot(L.NullSlot):
    """LLM이 아무것도 찾지 못하는 슬롯(호출 수만 센다)."""
    name = "fake"

    def __init__(self, *a, **k):
        self.calls = self.failed = 0

    def find_sentence(self, *a, **k):
        self.calls += 1
        return None

    def ask(self, *a, **k):
        self.calls += 1
        return None


class FakeStore(S.NullStore):
    def __init__(self, pdf=None, snap=None):
        self.pdf, self.snap, self.log = pdf, snap, []

    def get_pdf(self, sha): return self.pdf
    def latest_analysis(self, sha, version): return self.snap

    def save_analysis(self, *a, **k):
        self.log.append(("save", k.get("by")))
        return 1

    def delete_pdf(self, sha):
        self.log.append(("delete_pdf",))
        return True

    def enqueue(self, sha, kind, priority=0):
        self.log.append(("enqueue", kind))
        return True

    def finish(self, job_id, ok, error=""):
        self.log.append(("finish", ok, error))
        return True


@pytest.fixture(scope="module")
def n12():
    return sv.pdf_path("N12").read_bytes()


def _job(data=b"x"):
    return S.Job(1, hashlib.sha256(data).hexdigest(), "enhance", 1)


def test_slot_that_finds_nothing_keeps_the_deterministic_draft(n12):
    plain, with_slot = draft.make_draft(n12), draft.make_draft(n12, slot=FakeSlot())
    assert with_slot.doc == plain.doc and with_slot.held_conditions == plain.held_conditions


def test_new_analysis_is_saved_and_auto_confirmed_pdf_deleted(n12):
    st = FakeStore(pdf=n12)
    msg = worker.enhance(st, _job(n12), FakeSlot())
    assert st.log == [("save", "worker"), ("delete_pdf",), ("finish", True, "")] and "PDF 삭제" in msg


def test_no_improvement_is_not_saved(n12):
    sha = hashlib.sha256(n12).hexdigest()
    st = FakeStore(pdf=n12, snap=draft.to_snapshot(draft.make_draft(n12), sha))
    worker.enhance(st, _job(n12), FakeSlot())
    assert ("save", "worker") not in st.log and st.log[-1] == ("finish", True, "")


def test_partial_result_goes_to_operator_review(n12, monkeypatch):
    monkeypatch.setattr(analysis, "overall_grade", lambda d: "partial")
    st = FakeStore(pdf=n12)
    worker.enhance(st, _job(n12), FakeSlot())
    assert ("enqueue", "review") in st.log and ("delete_pdf",) not in st.log


def test_missing_pdf_is_a_failure():
    st = FakeStore(pdf=None)
    assert worker.enhance(st, _job(), FakeSlot()) == "PDF 없음" and st.log == [("finish", False, "보관된 PDF 없음(기한 지남·삭제)")]


def test_score_prefers_judgeable_and_fewer_unknowns(n12):
    ok = draft.make_draft(n12)
    blocked = draft.Draft(draft.BLOCKED, "보류", missing=["a"])
    assert worker.score(ok) > worker.score(blocked) > worker.score(None)


def test_ollama_down_means_no_claim(monkeypatch):
    assert worker.ollama_ready("http://127.0.0.1:1", "ministral-3:3b") is False

    class Never(S.Store):
        def claim(self, kind):
            raise AssertionError("Ollama가 꺼져 있는데 작업을 가져감")

        def purge_expired(self): return 0

    monkeypatch.setattr(worker, "get_store", lambda: Never("postgresql://unused"))
    monkeypatch.setattr(worker, "ollama_ready", lambda h, m: False)
    monkeypatch.setattr(worker, "status", lambda s: "현황")
    assert worker.main(["--once"]) == 0


def test_no_database_exits(monkeypatch):
    monkeypatch.setattr(worker, "get_store", lambda: S.NullStore())
    assert worker.main(["--once"]) == 2


@pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL 없음")
def test_db_worker_end_to_end(n12, monkeypatch):
    schema = "t_" + uuid.uuid4().hex[:10]
    db = S.Store(TEST_URL, schema=schema)
    try:
        assert db.migrate()
        sha = hashlib.sha256(n12).hexdigest()
        db.save_notice(sha, issuer="LH")
        assert db.put_pdf(sha, n12) and db.enqueue(sha, "enhance")
        monkeypatch.setattr(worker, "get_store", lambda: db)
        monkeypatch.setattr(worker, "ollama_ready", lambda h, m: True)
        monkeypatch.setattr(L, "OllamaSlot", FakeSlot)
        assert worker.main(["--once"]) == 0
        jobs = db._run(lambda c: c.execute("SELECT kind, status FROM jobs ORDER BY id").fetchall())
        assert jobs == [("enhance", "done")]
        assert db._run(lambda c: c.execute("SELECT created_by FROM analyses").fetchall()) == [("worker",)]
        assert db.get_pdf(sha) is None                                    # 자동 확정 → 삭제
        assert draft.from_snapshot(db.latest_analysis(sha, analysis.analysis_version())).doc == draft.make_draft(n12).doc
    finally:
        db._run(lambda c: c.execute(f'DROP SCHEMA "{schema}" CASCADE'))
        db.close()
