# -*- coding: utf-8 -*-
"""LH 공고문 자동 분석(2026-11-14 사용자 결정 A안 — 공식 API가 주는 첨부 주소로 내려받아 재판소와 같은 자동 분석)."""
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]
os.environ.setdefault("CCJ_STORE", "off")

import live_notices as L  # noqa: E402
import store as S  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "live"
TEST_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL 없음 — 실제 DB 시험은 CI(postgres 서비스)에서")
DETAIL = json.loads((FX / "lh_detail.json").read_text(encoding="utf-8"))


def lh_row(ext, title, announced="2026-11-05", program="국민임대주택", pdf=None, auto=None):
    dk = {"PAN_ID": ext}
    if pdf:
        dk["pdf"] = pdf
    if auto:
        dk["auto"] = auto
    return {"source": "lh", "external_id": ext, "title": title, "issuer": "LH", "kind": "국민임대", "region": "",
            "announced": announced, "window_start": "2026-11-20", "window_end": "2026-11-22", "status": "공고중", "url": "u",
            "program": program, "template": "lh.national_rental", "registered_id": None, "route": L.TEMPLATE, "detail_key": dk,
            "request_count": 0}


def test_pdf_url_from_detail_and_kept_in_detail_key():
    assert L.lh_pdf_url(DETAIL) == "https://apply.lh.or.kr/lhapply/lhFile.do?fileid=69288832"     # hwp가 아니라 PDF
    n = L.LiveNotice(source="lh", external_id="X", title="t", issuer="LH", kind="영구임대", region="", announced="2026-11-09",
                     window_start=None, window_end=None, status="공고중", url="", detail_key={"PAN_ID": "X"})
    got = L.with_detail(n, DETAIL)
    assert got.detail_key == {"PAN_ID": "X", "pdf": L.lh_pdf_url(DETAIL)} and got.window_start
    assert L.lh_pdf_url([]) is None


def test_match_analyzed_unique_slot_links_without_title():
    import find as F
    cand = [{"sha256": "a" * 64, "issuer": "LH", "program": "국민임대주택", "title": "입주자 모집 절차 및 일정",
             "announcement_date": date(2026, 11, 5)}]
    one = lh_row("A", "인천논현2단지 국민임대주택 예비입주자 모집")
    assert F.match_analyzed(one, cand) is None                        # 제목이 달라 — 비교 대상 없이는 잇지 않음
    assert F.match_analyzed(one, cand, [one]) == "a" * 64            # 같은 날 같은 사업 공고가 하나뿐
    two = lh_row("B", "화성동탄 국민임대주택 예비입주자 모집")
    assert F.match_analyzed(one, cand, [one, two]) is None           # 둘이면 제목이 비슷해야만
    other_day = dict(cand[0], announcement_date=date(2026, 11, 6))
    assert F.match_analyzed(one, [other_day], [one]) is None


def test_analyze_saves_title_origin_and_source(monkeypatch):
    import analysis
    import draft
    saved = {}

    class Fake(S.NullStore):
        def save_notice(self, sha, **meta):
            saved.update(meta)
            return True
    monkeypatch.setattr(draft, "make_draft", lambda data: draft.Draft(status=draft.UNSUPPORTED, program="국민임대주택"))
    analysis.analyze(b"%PDF-1.4 x", SimpleNamespace(issuer="LH", program="국민임대주택", announcement="2026-11-05"), Fake(),
                     title="인천논현2단지 국민임대주택 예비입주자 모집", origin="collect", source_url="https://x")
    assert saved["title"].startswith("인천논현2단지") and saved["origin"] == "collect" and saved["source_url"] == "https://x"


class Rec(S.NullStore):
    def __init__(self):
        self.merged = []

    def merge_live_detail(self, source, external_id, data):
        self.merged.append((external_id, data))
        return True


def test_auto_analyze_once_per_pdf_and_records(monkeypatch):
    import analysis
    import collect_live_notices as C
    import draft
    import notice_identify as ni
    monkeypatch.setattr(C, "AUTO_PAUSE", 0)
    got = {}
    monkeypatch.setattr(C, "_get_bytes", lambda url: b"%PDF-1.4 " + url.encode())
    monkeypatch.setattr(ni, "identify_pdf", lambda data: SimpleNamespace(status=ni.UNREGISTERED, issuer="LH", program="국민임대주택",
                                                                         announcement="2026-11-05"))

    def fake_analyze(data, ident, store, title=None, origin="upload", source_url=None):
        got[title] = origin
        return draft.Draft(status=draft.OK, template="lh.national_rental")
    monkeypatch.setattr(analysis, "analyze", fake_analyze)
    monkeypatch.setattr(analysis, "overall_grade", lambda d: "auto")
    rows = [lh_row("A", "인천논현2단지 국민임대주택", pdf="https://apply.lh.or.kr/lhapply/lhFile.do?fileid=1"),
            lh_row("B", "화성동탄 국민임대주택", pdf="https://apply.lh.or.kr/lhapply/lhFile.do?fileid=2",
                   auto={"pdf": "https://apply.lh.or.kr/lhapply/lhFile.do?fileid=2", "result": "ok",
                         "ver": analysis.analysis_version()}),     # 같은 엔진 판에서 이미 시도 — 건너뜀
            lh_row("C", "수원광교 국민임대주택"),                                                          # PDF 주소 없음
            dict(lh_row("D", "SH 행복주택", pdf="https://x/pdf"), source="seoul_housing")]               # LH만
    store = Rec()
    out = C.auto_analyze(store, rows, [], date(2026, 11, 14))
    assert [r["external_id"] for r, _ in out] == ["A"] and got == {"인천논현2단지 국민임대주택": "collect"}
    ext, rec = store.merged[0]
    assert ext == "A" and rec["auto"]["result"] == draft.OK and rec["auto"]["pdf"].endswith("fileid=1") and len(rec["auto"]["sha"]) == 64
    assert rec["auto"]["ver"] == analysis.analysis_version()
    # 엔진 판이 바뀌면(판정 코드·추출기 수정) 같은 공고문이어도 다시 분석 — 흥신소는 지금 판의 분석만 읽는다(2026-11-15)
    rows[1]["detail_key"]["auto"]["ver"] = "v3-옛판"
    assert {r["external_id"] for r, _ in C.auto_analyze(Rec(), rows[:2], [], date(2026, 11, 15))} == {"A", "B"}
    rows[1]["detail_key"]["auto"]["ver"] = analysis.analysis_version()
    # 정정공고로 주소가 바뀌면 다시 시도
    rows[1]["detail_key"]["pdf"] = "https://apply.lh.or.kr/lhapply/lhFile.do?fileid=3"
    out = C.auto_analyze(Rec(), rows, [], date(2026, 11, 14), limit=8)
    assert {r["external_id"] for r, _ in out} == {"A", "B"}


def test_auto_analyze_download_error_is_recorded(monkeypatch):
    import collect_live_notices as C
    monkeypatch.setattr(C, "AUTO_PAUSE", 0)

    def boom(url):
        raise C.SourceError("시간 초과")
    monkeypatch.setattr(C, "_get_bytes", boom)
    store = Rec()
    out = C.auto_analyze(store, [lh_row("A", "t", pdf="https://p")], [], date(2026, 11, 14))
    assert out[0][1]["result"] == "download_error" and "시간 초과" in out[0][1]["error"]
    assert store.merged[0][1]["auto"]["result"] == "download_error"      # 같은 주소는 다시 받지 않는다(실패도 기록)


def test_summary_lists_autos_and_pdf_links():
    import coverage as V
    from collections import Counter
    rows = [lh_row("A", "인천논현2단지 국민임대주택", pdf="https://p/1", auto={"pdf": "https://p/1", "result": "blocked"})]
    md = V.summary_markdown(V.coverage(rows, []), V.pending(rows, []), [], set(), date(2026, 11, 14),
                            [(rows[0], {"result": "ok", "grade": "auto", "kb": 800, "seconds": 3.1})])
    assert "LH 공고문 자동 분석" in md and "[PDF](https://p/1) (blocked)" in md and "800KB" in md
    assert Counter()["x"] == 0


@pytest.fixture
def db():
    schema = "t_" + uuid.uuid4().hex[:10]
    s = S.Store(TEST_URL, schema=schema)
    assert s.migrate()
    yield s
    s._run(lambda c: c.execute(f'DROP SCHEMA "{schema}" CASCADE'))
    s.close()


@needs_db
def test_db_collect_origin_is_analyzed_and_detail_merge(db):
    from datetime import timedelta
    ann = date.today() - timedelta(days=2)
    db.save_notice("c" * 64, issuer="LH", program="국민임대주택", title="인천논현2단지 국민임대주택", announcement_date=ann,
                   origin="collect", source_url="https://apply.lh.or.kr/x")
    db.save_analysis("c" * 64, "v", {"status": "ok"})
    assert [r["sha256"] for r in db.analyzed_notices()] == ["c" * 64]
    n = L.LiveNotice(source="lh", external_id="A1", title="t", issuer="LH", kind="국민임대", region="", announced=ann.isoformat(),
                     window_start=None, window_end=None, status="공고중", url="", detail_key={"PAN_ID": "A1", "pdf": "https://p/1"})
    db.upsert_live([n.as_dict()])
    assert db.merge_live_detail("lh", "A1", {"auto": {"pdf": "https://p/1", "result": "ok"}})
    db.upsert_live([L.LiveNotice(**dict(n.as_dict(), detail_key={"PAN_ID": "A1"}, program=None, template=None,
                                        registered_id=None, route=None)).as_dict()])     # 상세 없이 다시 수집
    dk = db.live_notices(open_only=False)[0]["detail_key"]
    assert dk["pdf"] == "https://p/1" and dk["auto"]["result"] == "ok"


def test_auto_analyzed_notice_links_by_pdf_fingerprint_even_if_dates_differ():
    """수집 작업이 내려받아 분석한 공고문은 지문(detail_key.auto.sha)으로 잇는다 — 목록 공고일·사업 이름이 공고문과 달라도(2026-11-15)."""
    import find as F
    sha = "d" * 64
    cand = [{"sha256": sha, "issuer": "LH", "program": "공공분양주택", "title": "입주자모집공고",
             "announcement_date": date(2026, 10, 30)}]
    row = lh_row("S1", "시흥거모 S-1블록 공공분양주택 입주자모집공고", announced="2026-11-02", program="공공분양주택",
                 pdf="https://p/s1", auto={"pdf": "https://p/s1", "result": "ok", "sha": sha})
    assert F.match_analyzed(row, cand) == sha
    other = lh_row("S2", "다른 공고", pdf="https://p/s2", auto={"pdf": "https://p/s2", "result": "ok", "sha": "e" * 64})
    assert F.match_analyzed(other, cand) is None              # 분석 목록에 없는 지문이면 잇지 않음(예전 규칙대로)


@needs_db
def test_db_collect_analysis_without_announcement_date_is_still_listed(db):
    """수집 작업이 분석한 공고는 공고문에서 공고일을 못 읽었어도 잇기 후보에 든다(2026-11-15). 업로드는 최근 120일만."""
    db.save_notice("f" * 64, issuer="LH", program="공공분양주택", title="시흥거모 S-1", announcement_date=None, origin="collect")
    db.save_analysis("f" * 64, "v", {"status": "ok"})
    db.save_notice("0" * 64, issuer="LH", program="국민임대주택", title="옛 업로드", announcement_date=date(2020, 1, 1), origin="upload")
    db.save_analysis("0" * 64, "v", {"status": "ok"})
    assert [r["sha256"] for r in db.analyzed_notices()] == ["f" * 64]


@needs_db
def test_db_analyzed_notices_can_be_limited_to_the_current_engine_version(db):
    """흥신소는 지금 판의 분석만 읽으므로 잇기·확정 범위도 지금 판 기준 — 판이 바뀐 공고는 '분석 대기'로 돌아가 다시 분석된다."""
    db.save_notice("a" * 64, issuer="LH", program="국민임대주택", title="옛 판 분석", announcement_date=None, origin="collect")
    db.save_analysis("a" * 64, "v3-old", {"status": "ok"})
    db.save_notice("b" * 64, issuer="LH", program="국민임대주택", title="지금 판 분석", announcement_date=None, origin="collect")
    db.save_analysis("b" * 64, "v3-new", {"status": "ok"})
    assert {r["sha256"] for r in db.analyzed_notices()} == {"a" * 64, "b" * 64}
    assert [r["sha256"] for r in db.analyzed_notices(version="v3-new")] == ["b" * 64]
