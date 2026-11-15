# -*- coding: utf-8 -*-
"""test_t13_stop_resume.py — 멈춤·복구 리허설(2026-11-09 피드백 1순위 '잘못된 확정 판정 차단·복구 동작', docs/13 1-3절).

장치는 하나씩 시험돼 있다(B2 기록 test_b2_compare, 저장소 강등 test_d4_store, API 멈춤 test_d4_api_upload, 검증 상태 test_verification).
여기서는 **한 흐름으로** 이어서 돌린다:

  ① 판정해 오던 사업 → ② 처음 보는 공고 비교에서 위험 발견(draft_compare --record) → ③ 그 사업 자동 판정 멈춤
  → ④ 재판소 업로드는 '정확도 점검 중'으로 판정하지 않고 /evaluate도 거절, 검증 상태도 '정확도 점검 중'
  → ⑤ 원인을 고치고 다시 비교해 위험 0이어도 저절로 풀리지 않음 → ⑥ 운영자가 다시 켬(tools/program_health.py --resume)
  → ⑦ 다시 판정, 검증 상태 '검증 중'.

저장소: 메모리 대역(Store.record_comparison·set_demoted의 SQL 규칙을 그대로 옮김)으로 늘 돌리고, TEST_DATABASE_URL이 있으면(CI postgres)
실제 PostgreSQL 저장소로 같은 흐름을 한 번 더 돌린다.
"""
import copy
import os
import sys
import uuid
from pathlib import Path

import pytest

import draft
import golden_cases as gc
import source_verify as sv
import store as S

pytest.importorskip("fastapi")
pytest.importorskip("multipart")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import draft_compare as dc  # noqa: E402
import program_health as PH  # noqa: E402

import test_d4_api_upload as U  # noqa: E402  (업로드 시험의 client·도우미를 그대로 쓴다)
from test_d4_api_upload import n12, unregistered  # noqa: E402,F401  (fixture)

api = U.api
PROGRAM = "lh.youth_rental"          # N12(청년 매입임대)의 판정 틀
LIMIT = 200
TEST_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


class HealthMemory(U.Memory):
    """식별 캐시(U.Memory) + 사업별 정확도·멈춤. 규칙은 store.Store와 같다: 위험이 1건이라도 기록되면 멈추고,
    다시 켜는 것은 set_demoted(False)뿐(위험 0 기록으로는 풀리지 않음)."""

    def __init__(self):
        super().__init__()
        self.health = {}

    def record_comparison(self, program, same=0, cautious=0, danger=0):
        h = self.health.setdefault(program, dict(program=program, compared=0, same=0, cautious=0, danger=0, demoted_at=None))
        h["compared"] += same + cautious + danger
        h["same"] += same
        h["cautious"] += cautious
        h["danger"] += danger
        if danger > 0 and h["demoted_at"] is None:
            h["demoted_at"] = "now"
        return True

    def set_demoted(self, program, demoted):
        h = self.health.setdefault(program, dict(program=program, compared=0, same=0, cautious=0, danger=0, demoted_at=None))
        h["demoted_at"] = (h["demoted_at"] or "now") if demoted else None
        return True

    def demoted_programs(self):
        return frozenset(p for p, h in self.health.items() if h["demoted_at"])

    def program_health(self):
        return list(self.health.values())


@pytest.fixture(scope="module")
def n12_snapshot():
    path = sv.pdf_path("N12")
    d = draft.make_draft(path.read_bytes(), only=None, pages=sv.pdf_pages("N12"))
    return draft.to_snapshot(d, sv.notice_doc("N12")["source"]["sha256"], source=path.name, created="2026-10-28")


def _status(program):
    return next(p["status"] for p in U.client.get("/verification").json()["programs"] if p["template"] == program)


def _evaluate(sha):
    p = next(p for _, _, p in gc.cases(only=[("N12", "청년")]))
    return U.client.post("/evaluate", json={"sha256": sha, "layer": "청년", "profile": U._body(p)})


def rehearse(store, snapshot, data, monkeypatch, capsys):
    monkeypatch.setenv(api.PUBLIC_ENV, "1")
    monkeypatch.setattr(api, "get_store", lambda: store)
    monkeypatch.setattr(PH, "get_store", lambda: store)

    # ① 판정해 오던 사업
    j = U._post(data).json()
    assert j["judge"]["by"] == "analysis" and _status(PROGRAM) == "in_progress"
    assert _evaluate(j["sha256"]).status_code == 200

    # ② 처음 보는 공고 비교에서 위험 발견 — 초안이 나이 조건을 놓친 경우(틀린 지원 가능)
    bad = copy.deepcopy(snapshot)
    conds = bad["doc"]["layers"]["청년"]["conditions"]
    conds.remove(next(c for c in conds if c["id"].endswith("-age")))
    res = dc.compare(bad, limit=LIMIT)
    assert dc.danger_count(res) > 0
    assert dc.record(res, store) == PROGRAM

    # ③ 그 사업 자동 판정 멈춤
    assert store.demoted_programs() == {PROGRAM}

    # ④ 재판소: 판정하지 않고 이유 표시, /evaluate 거절, 검증 상태 '정확도 점검 중'
    j = U._post(data).json()
    assert j["judge"]["by"] == "none" and "정확도 점검 중" in j["judge"]["reason"]
    r = _evaluate(j["sha256"])
    assert r.status_code == 403 and "정확도 점검 중" in r.json()["detail"]
    assert _status(PROGRAM) == "paused"
    assert all(p["status"] != "paused" for p in U.client.get("/verification").json()["programs"] if p["template"] != PROGRAM)

    # ⑤ 원인을 고치고 다시 비교 — 위험 0이어도 저절로 풀리지 않는다
    ok = dc.compare(snapshot, limit=LIMIT)
    assert dc.danger_count(ok) == 0
    dc.record(ok, store)
    assert store.demoted_programs() == {PROGRAM}
    assert U._post(data).json()["judge"]["by"] == "none"

    # ⑥ 운영자가 다시 켬 — 운영 도구 그대로
    assert PH.main(["--resume", PROGRAM]) == 0
    assert "다시 켬" in capsys.readouterr().out
    assert store.demoted_programs() == frozenset()

    # ⑦ 다시 판정, 검증 상태 '검증 중'
    j = U._post(data).json()
    assert j["judge"]["by"] == "analysis" and _status(PROGRAM) == "in_progress"
    assert _evaluate(j["sha256"]).status_code == 200


def test_stop_and_resume_rehearsal_memory(n12, n12_snapshot, unregistered, monkeypatch, capsys):
    rehearse(HealthMemory(), n12_snapshot, n12, monkeypatch, capsys)


@pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL 없음 — 실제 DB 리허설은 CI(postgres 서비스)에서")
def test_stop_and_resume_rehearsal_postgres(n12, n12_snapshot, unregistered, monkeypatch, capsys):
    schema = "t_" + uuid.uuid4().hex[:10]
    s = S.Store(TEST_URL, schema=schema)
    assert s.migrate()
    try:
        rehearse(s, n12_snapshot, n12, monkeypatch, capsys)
    finally:
        s._run(lambda c: c.execute(f'DROP SCHEMA "{schema}" CASCADE'))
        s.close()
