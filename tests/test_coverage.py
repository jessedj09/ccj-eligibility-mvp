# -*- coding: utf-8 -*-
"""확정 판정 범위 관리(src/coverage.py — 흥신소 묶음 A, 2026-11-13): 분석 대기 공고·범위 지표·예비 판정 감시."""
import os
import sys
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "tools"), str(ROOT / "tests")]
os.environ.setdefault("CCJ_STORE", "off")

import coverage as V  # noqa: E402
import find as F  # noqa: E402
import live_judge as J  # noqa: E402
import live_notices as L  # noqa: E402
import store as S  # noqa: E402

TEST_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL 없음 — 실제 DB 시험은 CI(postgres 서비스)에서")


def row(title, kind, ext, start, req=0, announced="2026-11-05"):
    return {"source": "lh", "external_id": ext, "title": title, "issuer": "LH", "kind": kind, "region": "경기도",
            "announced": date.fromisoformat(announced), "window_start": date.fromisoformat(start),
            "window_end": date.fromisoformat(start) + timedelta(days=3), "status": "공고중", "url": f"https://x/{ext}",
            "program": None, "template": None, "registered_id": None, "route": None, "detail_key": {}, "request_count": req}


ROWS = F.relink([
    row("인천논현2단지 국민임대주택 예비입주자 모집 공고", "국민임대", "A", "2026-11-20", req=3),
    row("화성동탄 국민임대주택 예비입주자 모집", "국민임대", "B", "2026-11-15", req=0),
    row("수원광교 국민임대주택 예비입주자 모집", "국민임대", "C", "2026-11-15", req=5),
    row("과천지식정보타운 S12블록 행복주택 입주자 모집공고", "행복주택", "D", "2026-11-09", announced="2026-10-28"),   # 등록 N27
    row("○○ 공공지원 민간임대 입주자 모집", "민간임대", "E", "2026-11-16"),
])
ANALYZED = [{"sha256": "s" * 64, "issuer": "LH", "program": "국민임대주택", "title": "인천논현2단지 국민임대주택 예비입주자 모집",
             "announcement_date": date(2026, 11, 5)}]


def test_pending_sorted_by_start_then_requests_and_excludes_analyzed():
    waiting = V.pending(ROWS, ANALYZED)
    assert [r["external_id"] for r in waiting] == ["C", "B"]            # A는 분석됨, D는 등록, E는 판정 안 함
    assert [r["external_id"] for r in V.pending(ROWS, [])] == ["C", "B", "A"]


def test_coverage_counts_registered_and_analyzed():
    c = V.coverage(ROWS, ANALYZED)
    assert (c["registered"], c["analyzed"], c["pending"], c["unsupported"]) == (1, 1, 2, 1)
    assert c["target"] == 4 and c["confirmed"] == 2 and c["pct"] == 50
    assert V.coverage([], [])["pct"] == 0


def test_check_preview_against_registered_rules_has_no_miss():
    """등록 공고(N32 국민임대)를 '분석된 공고'처럼 넣으면 대표 공고(N58)로 예비 판정해 확정(N32 규칙)과 비교한다 — 되짚어 보기와 같이 놓침 0."""
    import draft
    from notices_data import ALL_NOTICES
    r = dict(ROWS[0], announced=date(2026, 9, 7), template="lh.national_rental", program="국민임대주택")
    d = draft.Draft(status=draft.OK, template="lh.national_rental", notice=ALL_NOTICES["N32"])
    import grading
    orig = grading.judge
    try:
        grading.judge = lambda dd, p, layer: (__import__("rule_engine").evaluate(p, dd.notice, layer), [])
        got = V.check_preview(r, d, limit=40)
    finally:
        grading.judge = orig
    assert got is not None
    tname, c = got
    assert tname == "lh.national_rental" and c["compared"] > 0 and c["missed"] == 0


def test_summary_markdown():
    md = V.summary_markdown(V.coverage(ROWS, ANALYZED), V.pending(ROWS, ANALYZED),
                            [("인천논현2단지", "lh.national_rental", Counter(compared=10, missed=1, likely_ok=3, likely_wrong=1))],
                            {"lh.national_rental"}, date(2026, 11, 13))
    assert "확정 판정 범위 50%" in md and "분석 대기 공고" in md and "수원광교" in md and "[링크](https://x/C)" in md
    assert "멈춘 판정 틀" in md and "--resume" in md


def test_stopped_template_turns_unlikely_into_verify(monkeypatch):
    """감시가 놓침을 기록한 판정 틀은 흥신소에서 예비 '어려움' 대신 '실제 공고문 확인필요'."""
    from profile_io import master_from_dict
    from schedule import KST
    monkeypatch.setattr(J, "preview_layer", lambda p, layer, rep, t, index, ann: J.LayerPreview(layer, J.UNLIKELY, "INELIGIBLE"))
    youth = {"schema": "ccj-profile/1", "master": {"birth_date": "1990-01-01"}, "common": {"marital_status": "미혼", "household_size": 1}}
    at = datetime(2026, 11, 10, 12, 0, tzinfo=KST)
    card = lambda out: next(x for x in out["items"] if x["external_id"] == "A")  # noqa: E731
    assert card(F.find_open(master_from_dict(youth), [ROWS[0]], at))["result"] == F.UNLIKELY
    stopped = F.find_open(master_from_dict(youth), [ROWS[0]], at, stopped=frozenset({"lh.national_rental"}))
    assert card(stopped)["result"] == F.VERIFY


def test_collector_report_writes_step_summary(tmp_path, monkeypatch, capsys):
    import collect_live_notices as C
    out = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))
    C.report_coverage(None, L.merge_duplicates(ROWS), date(2026, 11, 13))
    assert "확정 판정 범위" in capsys.readouterr().out
    assert "분석 대기 공고" in out.read_text(encoding="utf-8")


@pytest.fixture
def db():
    schema = "t_" + uuid.uuid4().hex[:10]
    s = S.Store(TEST_URL, schema=schema)
    assert s.migrate()
    yield s
    s._run(lambda c: c.execute(f'DROP SCHEMA "{schema}" CASCADE'))
    s.close()


@needs_db
def test_db_preview_checks_stop_and_resume(db):
    assert db.record_preview_check("a" * 64, "lh.national_rental", 100, 0, 30, 2)
    assert db.preview_stopped() == frozenset() and db.preview_checked(["a" * 64, "b" * 64]) == {"a" * 64}
    db.record_preview_check("b" * 64, "lh.national_rental", 80, 2, 20, 1)
    assert db.preview_stopped() == frozenset({"lh.national_rental"})
    assert db.resume_preview("lh.national_rental") and db.preview_stopped() == frozenset()
    h = {r["template"]: r for r in db.preview_health()}["lh.national_rental"]
    assert h["notices"] == 2 and h["missed"] == 2 and h["compared"] == 180
    # 다시 켠 뒤에 새 놓침이 나오면 다시 멈춘다
    db.record_preview_check("c" * 64, "lh.national_rental", 50, 1, 10, 0)
    assert db.preview_stopped() == frozenset({"lh.national_rental"})
    # 분석 요청 건수는 수집 공고 읽기에 같이 온다
    n = L.link(L.LiveNotice(source="lh", external_id="X1", title="t", issuer="LH", kind="국민임대", region="", announced="2026-11-05",
                            window_start=None, window_end=None, status="공고중", url=""))
    db.upsert_live([n.as_dict()])
    db.request_analysis("lh", "X1")
    assert db.live_notices(open_only=False)[0]["request_count"] == 1
