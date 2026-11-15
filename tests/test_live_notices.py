# -*- coding: utf-8 -*-
"""test_live_notices.py — 실시간 공고 연결 1단계(docs/12): 공공데이터포털 응답 읽기·판정과 잇기·저장·수집기.

응답 표본은 tests/fixtures/live/(2026-11-10 실제 응답 일부 — 인증키 없음). 네트워크는 쓰지 않는다(수집기는 가짜 응답).
실제 PostgreSQL 시험은 TEST_DATABASE_URL이 있을 때만.
"""
import json
import os
import sys
import uuid
from dataclasses import replace
from datetime import date
from pathlib import Path

import live_notices as L
import pytest
import store as S

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import collect_live_notices as C  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "live"
TODAY = date(2026, 11, 10)
TEST_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
needs_db = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL 없음 — 실제 DB 시험은 CI(postgres 서비스)에서")


def fx(name):
    return json.loads((FIX / f"{name}.json").read_text(encoding="utf-8"))


def lh(title, kind="국민임대", announced="2026-11-05", issuer="LH"):
    return L.LiveNotice(source=L.LH_SOURCE, external_id="X", title=title, issuer=issuer, kind=kind, region="",
                        announced=announced, window_start=None, window_end=None, status="공고중", url="")


def test_lh_list_keeps_housing_rows_with_detail_keys():
    rows = L.parse_lh_list(fx("lh_list_06"))
    assert len(rows) == 6 and all(n.issuer == "LH" and n.source == "lh" for n in rows)
    n = rows[0]
    assert n.title == "원주시지역 영구임대주택 예비입주자 모집" and n.kind == "영구임대" and n.announced == "2026-11-09"
    assert n.window_end == "2026-11-27" and n.url.startswith("https://apply.lh.or.kr/")
    assert set(n.detail_key) == {"PAN_ID", "CCR_CNNT_SYS_DS_CD", "SPL_INF_TP_CD", "UPP_AIS_TP_CD", "AIS_TP_CD"}
    land = [{"dsList": [dict(fx("lh_list_06")[1]["dsList"][0], UPP_AIS_TP_CD="01")]}]
    assert L.parse_lh_list(land) == []                                   # 토지·상가는 거른다


def test_lh_detail_gives_window_across_complexes():
    assert L.lh_windows(fx("lh_detail")) == {"window_start": "2026-11-25", "window_end": "2026-11-27"}
    assert L.lh_windows([{"dsSplScdl": []}]) is None


def test_applyhome_keeps_only_lh_and_sh():
    rows = L.parse_applyhome(fx("applyhome"), TODAY)
    assert rows and all(n.issuer == "LH" for n in rows)                  # 표본의 민간 아파트 5건은 빠진다
    n = next(n for n in rows if "시흥" in n.title)
    assert (n.window_start, n.window_end, n.status) == ("2026-11-16", "2026-11-27", "접수예정")
    assert L._issuer("서울주택도시공사") == "SH" and L._issuer("주식회사 브랜드뉴탄벌") is None


def test_link_routes_by_template_and_relaxed_titles():
    assert L.link(lh("원주시지역 영구임대주택 예비입주자 모집", "영구임대")).template == "lh.permanent_rental"
    n = L.link(lh("남원노암 공공임대 50년 예비입주자모집", "공공임대"))   # 제목에 '공공임대주택'이 없어 LH 유형 이름으로
    assert (n.program, n.template, n.route) == ("공공임대주택", "lh.public_rental", L.TEMPLATE)
    assert L.link(lh("파주시 중소기업체 기관공급(행복주택)", "영구임대")).route == L.UNSUPPORTED
    # 입주자격 완화(2026-11-15 사용자 결정): 판정 틀이 있으면 판정 안 함 대신 '확인 필요' 갈래(사유 RELAXED_NOTE)
    for t in ("김제검산 영구임대주택 입주자격완화 예비입주자 모집", "화성시동탄지역 행복주택 입주자모집[입주자격완화, 선계약후검증]"):
        n = L.link(lh(t, "영구임대" if "영구" in t else "행복주택"))
        assert n.route == L.RELAXED_ROUTE and n.template, t
    sh = L.link(lh("2026년 2차 행복주택 입주자모집", "행복주택", issuer="SH"))
    assert sh.template == "sh.happy_housing"
    assert L.link(lh("[부산] 2026년 2차 일반 매입임대주택 입주자 모집 공고", "매입임대")).route == L.UNSUPPORTED


def test_lh_rental_titles_with_spaces_or_dot_variants_reach_templates():
    """2026-11-14: 띄어쓰기('청년 매입임대주택')·'ㆍ' 가운뎃점·'신생아Ⅰ매입임대' 제목이 분류표에 안 걸려 판정 안 함이던 결함."""
    for t, prog, tpl in (("[제주지역본부-제주시] 청년 매입임대주택 예비입주자 모집 공고", "청년매입임대", "lh.youth_rental"),
                         ("[정정공고]2026년 3차 대구경북지역 신혼ㆍ신생아Ⅰ매입임대 입주자 모집공고", "신혼·신생아 매입임대Ⅰ",
                          "lh.newlywed_rental"),
                         ("2026년 대구경북 신혼ㆍ신생아Ⅱ 매입임대 입주자 모집", "신혼·신생아 매입임대Ⅱ", "lh.newlywed_rental"),
                         ("[대전충남] 2026년 9월 신혼·신생아  II (전세형) 매입임대주택 예비입주자 모집 공고", "신혼·신생아 매입임대Ⅱ",
                          "lh.newlywed_rental"),
                         ("2026년 3차 대구경북지역 신혼ㆍ신생아Ⅱ(전세형) 입주자 모집공고", "신혼·신생아 매입임대Ⅱ", "lh.newlywed_rental"),
                         ("[인천]26년 7차 신혼·신생아Ⅰ 예비입주자 모집공고(인천,부천)", "신혼·신생아 매입임대Ⅰ", "lh.newlywed_rental"),
                         ("[정정공고][부산울산]신혼부부Ⅰ 매입임대주택 예비입주자 모집 공고", "신혼·신생아 매입임대Ⅰ", "lh.newlywed_rental"),
                         ("[부산울산]신혼부부Ⅱ(전세형) 매입임대주택 예비입주자 모집공고", "신혼·신생아 매입임대Ⅱ", "lh.newlywed_rental")):
        n = L.link(lh(t, "매입임대"))
        assert (n.program, n.template, n.route) == (prog, tpl, L.TEMPLATE), t
    # 선착순(자격 완화 가능)·판정 틀 없는 매입임대(기존주택·다자녀·장애인 자립특화형·자립준비청년)는 판정 안 함
    # 선착순(2026-11-15 사용자 결정): 판정 틀이 있어도 판정하지 않고 '확인 필요'(별도 갈래 — 자동 분석·확정 범위 대상 아님)
    fc = L.link(lh("[경기북부] 청년 매입임대주택 선착순 예비입주자 모집공고 (김포시, 포천시)", "매입임대"))
    assert (fc.program, fc.template, fc.route) == ("청년매입임대", "lh.youth_rental", L.FIRST_COME_ROUTE)
    assert L.link(lh("청주 다자녀 매입임대주택 선착순 모집", "매입임대")).route == L.UNSUPPORTED   # 판정 틀 없는 사업은 그대로
    for t in ("청주 다자녀 매입임대주택 입주자 모집",
              "장애인 자립특화형 매입임대 입주자 모집", "[경남] 자립준비청년 매입임대 예비입주자 모집",
              "[광주전남지역본부] 기숙사형 청년주택 예비입주자 모집공고", "[인천지역본부] 26년 2차 고령자 매입임대주택 예비입주자 모집"):
        assert L.link(lh(t, "매입임대")).route == L.UNSUPPORTED, t
    # '매입임대'가 제목·유형 어디에도 없으면 신혼·신생아 이름만으로 매입임대 틀에 넣지 않는다
    assert L.link(lh("2026년 신혼·신생아Ⅰ 전세임대 입주자 모집", "전세임대")).template is None


def test_registered_notice_is_matched_only_on_same_date_and_title():
    n = lh("SH 2026년 1차 행복주택 입주자모집", "행복주택", announced="2026-05-28", issuer="SH")
    assert L.link(n).registered_id == "N68" and L.link(n).route == L.REGISTERED
    assert L.registered_match(replace(n, issuer="LH"), program="행복주택") is None
    # 다음 날 같은 기관의 다자녀 매입임대(N65 2026.5.29.) — 제목 틀이 비슷해도 사업이 달라 같은 공고가 아니다
    assert L.registered_match(replace(n, announced="2026-05-29"), program="행복주택") is None
    assert L.registered_match(lh("SH 2026년 다자녀 매입임대주택 입주자모집", announced="2026-05-29", issuer="SH"),
                              program="다자녀 매입임대") == "N65"


def test_open_means_not_closed():
    n = replace(lh("x"), window_end="2026-11-10")
    assert L.is_open(n, TODAY) and not L.is_open(replace(n, window_end="2026-11-09"), TODAY)
    assert not L.is_open(replace(n, status="접수마감"), TODAY) and L.is_open(replace(n, window_end=None), TODAY)


def test_collector_dry_run_without_network(monkeypatch, capsys):
    calls = []

    def fake_get(url, key, params):
        calls.append(url)
        if url == C.LH_LIST:
            return fx("lh_list_06") if params["UPP_AIS_TP_CD"] == "06" else [{"dsList": []}]
        if url == C.LH_DETAIL:
            return fx("lh_detail")
        return fx("applyhome")
    monkeypatch.setattr(C, "_get", fake_get)
    monkeypatch.setenv(C.KEY_ENV, "dummy")
    assert C.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "LH: 6건" in out and "저장 0건" in out and "dummy" not in out
    assert calls.count(C.LH_DETAIL) == 6                                # 저장소가 없으면 공고마다 상세 조회


def test_collector_reports_failure_and_missing_key(monkeypatch, capsys):
    monkeypatch.delenv(C.KEY_ENV, raising=False)
    assert C.main(["--dry-run"]) == 2
    monkeypatch.setenv(C.KEY_ENV, "dummy")

    def broken(url, key, params):
        raise C.SourceError("접속 실패")
    monkeypatch.setattr(C, "_get", broken)
    assert C.main(["--dry-run"]) == 1
    assert "실패" in capsys.readouterr().out


def test_get_retries_once_on_timeout_then_reports(monkeypatch):
    calls = []

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'[{"dsList": []}]'

    def flaky(req, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise TimeoutError("handshake timed out")
        return Resp()
    monkeypatch.setattr(C.urllib.request, "urlopen", flaky)
    monkeypatch.setattr(C, "RETRY_WAIT", 0)
    monkeypatch.setattr(C, "PAUSE", 0)
    assert C._get(C.LH_LIST, "secret-key", {}) == [{"dsList": []}] and len(calls) == 2

    def down(req, timeout):
        raise C.urllib.error.URLError("secret-key 접속 실패")
    monkeypatch.setattr(C.urllib.request, "urlopen", down)
    with pytest.raises(C.SourceError) as e:
        C._get(C.LH_LIST, "secret-key", {})
    assert "secret-key" not in str(e.value)                              # 인증키는 오류 문장에도 남기지 않는다


def row(source, title, status="공고중", announced="2026-11-05", end="2026-11-17", start=None, route="template", reg=None,
        issuer="LH", ext=None):
    return dict(source=source, external_id=ext or title, title=title, issuer=issuer, status=status, announced=announced,
                window_start=start, window_end=end, route=route, registered_id=reg, program=None, template=None, url="u")


def test_corrections_and_cross_source_duplicates_are_grouped():
    """2026-11-10 운영 DB에서 본 형태: LH 정정공고 짝(원 공고는 '정정공고중'), LH와 청약홈의 같은 신혼희망타운."""
    rows = [row("lh", "인천논현2단지 국임임대주택 예비입주자 모집 공고", status="정정공고중", start="2026-11-18", end="2026-11-20"),
            row("lh", "[정정공고]인천논현2단지 국임임대주택 예비입주자 모집 공고", announced="2026-11-05", end="2026-11-20"),
            row("lh", "안산신길2 A-6블록 신혼희망타운(공공분양) 입주자모집공고", announced="2026-10-30", end="2026-11-24", reg="N48",
                route="registered"),
            row("applyhome", "안산신길2 A-6블록 신혼희망타운(공공분양)(본청약)", announced="2026-10-30", start="2026-11-16",
                end="2026-11-24", status="접수예정"),
            # 묶으면 안 되는 것: 괄호 안이 다른 공고, 마감일이 다른 청약홈 공고
            row("lh", "평창장평 통합공공임대주택(일반형) 입주자 모집"),
            row("lh", "평창장평 통합공공임대주택(고령자복지형) 입주자 모집"),
            row("applyhome", "안산신길2 A-6블록 신혼희망타운(공공분양)(사전청약)", announced="2026-10-30", end="2026-12-01",
                ext="other")]
    g = L.merge_duplicates(rows)
    assert len(g) == 5
    inc = g[0]
    assert inc["title"].startswith("[정정공고]") and inc["window_start"] == "2026-11-18"        # 정정공고가 대표, 접수 시작은 채움
    assert [x["status"] for x in inc["related"]] == ["정정공고중"]
    ansan = g[1]
    assert ansan["source"] == "lh" and ansan["window_start"] == "2026-11-16" and ansan["registered_id"] == "N48"
    assert [x["source"] for x in ansan["related"]] == ["applyhome"]
    assert [r["related"] for r in g[2:]] == [[], [], []]


def test_null_store_live_methods():
    s = S.NullStore()
    assert s.upsert_live([]) == 0 and s.live_notices() == [] and s.live_detail_needed({("lh", "1")}) == {("lh", "1")}


@pytest.fixture
def db():
    schema = "t_" + uuid.uuid4().hex[:10]
    s = S.Store(TEST_URL, schema=schema)
    assert s.migrate()
    yield s
    s._run(lambda c: c.execute(f'DROP SCHEMA "{schema}" CASCADE'))
    s.close()


@needs_db
def test_db_live_round_trip_keeps_window_and_detail_time(db):
    rows = [L.link(n) for n in L.parse_lh_list(fx("lh_list_06"))]
    first = L.with_detail(rows[0], fx("lh_detail"))
    key = (first.source, first.external_id)
    assert db.live_detail_needed([key]) == {key}
    assert db.upsert_live([first.as_dict()] + [n.as_dict() for n in rows[1:]], {key}) == 6
    assert db.live_detail_needed([key]) == set()                         # 하루 안에는 다시 부르지 않는다
    db.upsert_live([rows[0].as_dict()])                                  # 상세 없이 다시 — 접수 시작일은 남는다
    got = {r["external_id"]: r for r in db.live_notices(open_only=False)}
    assert str(got[first.external_id]["window_start"]) == "2026-11-25" and len(got) == 6


@needs_db
def test_db_request_analysis_counts_and_analyzed_notices(db):
    n = L.link(L.parse_lh_list(fx("lh_list_06"))[0])
    db.upsert_live([n.as_dict()])
    assert db.request_analysis(n.source, n.external_id) and db.request_analysis(n.source, n.external_id)
    assert not db.request_analysis("lh", "없는공고")
    cnt = db._run(lambda c: c.execute("SELECT request_count FROM live_notices WHERE external_id = %s",
                                      (n.external_id,)).fetchone())[0]
    assert cnt == 2
    db.upsert_live([n.as_dict()])                                        # 다시 수집해도 요청 건수는 남는다
    assert db._run(lambda c: c.execute("SELECT request_count FROM live_notices").fetchone())[0] == 2
    assert db.analyzed_notices() == []
    from datetime import date as _date, timedelta as _td
    ann = _date.today() - _td(days=3)
    db.save_notice("a" * 64, issuer="LH", program="국민임대주택", title="인천논현2단지 국민임대주택", announcement_date=ann)
    db.save_notice("b" * 64, issuer="LH", program="국민임대주택", title="분석 실패 공고", announcement_date=ann)
    db.save_analysis("a" * 64, "v", {"status": "ok"})
    db.save_analysis("b" * 64, "v", {"status": "unsupported"})
    got = db.analyzed_notices()
    assert [g["sha256"] for g in got] == ["a" * 64] and got[0]["announcement_date"] == ann


@needs_db
def test_db_detail_key_merges_and_is_read_back(db):
    """주택포털 SH 공고의 주택관리번호(상세에서 한 번 읽음)는 상세를 다시 열지 않는 수집에서도 남는다."""
    row = {"type": "주택분양", "title": "[정정] 고덕강일지구 3단지 토지임대부 분양주택 입주자모집공고", "posted": "2026-10-16",
           "winners": "2026-11-26", "status": "", "view": "/v?seq=4", "kind": "분양"}
    n = L.seoul_notice(row)
    db.upsert_live([dict(n.as_dict(), detail_key=dict(n.detail_key, house_no="2026000373"))])
    db.upsert_live([n.as_dict()])                                          # 다음 수집 — 상세 없이
    got = [r for r in db.live_notices(open_only=False) if r["source"] == L.SEOUL_SOURCE][0]
    assert got["detail_key"]["house_no"] == "2026000373" and got["detail_key"]["view"] == "/v?seq=4"


def test_first_come_card_is_verify_with_reason_and_upload_is_held():
    """선착순 모집 — 흥신소 카드는 '실제 공고문 확인필요'와 사유, 재판소(올린 공고문)는 어떤 결론도 확정하지 않고 같은 사유(2026-11-15)."""
    import dataclasses
    from datetime import date as _date
    import find as F
    import grading
    from display_status import HOLD_GROUP, display_result
    from matcher import MasterProfile
    row = dict(L.link(lh("[경기북부] 청년 매입임대주택 선착순 예비입주자 모집공고", "매입임대")).as_dict(), related=[])
    card, matches = F.judge_row(MasterProfile(), row, _date(2026, 11, 15))
    assert card["result"] == F.VERIFY and card["basis_note"] == L.FIRST_COME_NOTE and matches == []
    # 재판소: 표지에 '선착순'이 있는 초안은 엔진 결론과 관계없이 확인 필요
    import source_verify as sv
    import draft
    assert draft._first_come(["2026년 청년 매입임대주택 선착순 예비입주자 모집공고 ..."])
    assert not draft._first_come(["(단, 청약미달로 인해 선착순의 방법으로 공급한 주택을 최초로 취득한 경우)"])
    d = draft.from_snapshot(draft.to_snapshot(dataclasses.replace(_n12_draft(), first_come=True), "x" * 64))
    from rule_engine import HouseholdProfile
    p = HouseholdProfile(profile_id="T", age=45, marital_status="미혼", household_size=1, monthly_income=1, total_assets=1,
                         car_value=0, home_ownership="무주택")
    r, checks = grading.judge(d, p, "청년")
    assert r.verdict == "MANUAL_REVIEW" and [c.kind for c in checks] == ["first_come"]
    shown = display_result(r.verdict, r.review_reasons, len(checks), {c.kind for c in checks})
    assert shown.group == HOLD_GROUP and "선착순" in shown.title and shown.todo == L.FIRST_COME_NOTE


def _n12_draft():
    import draft
    import source_verify as sv
    return draft.make_draft(sv.pdf_path("N12").read_bytes(), pages=sv.pdf_pages("N12"), exclude="N12")


def test_relaxed_title_card_and_relaxed_upload_are_verify_with_reason():
    """입주자격 완화 — 흥신소 카드는 '실제 공고문 확인필요'와 사유, 공고문의 완화 문구는 어떤 결론도 확정하지 않고 같은 사유(2026-11-15)."""
    import dataclasses
    from datetime import date as _date
    import coverage as V
    import find as F
    import grading
    from display_status import HOLD_GROUP, display_result
    from matcher import MasterProfile
    from rule_engine import HouseholdProfile
    row = dict(L.link(lh("김제검산 영구임대주택 입주자격완화 예비입주자 모집", "영구임대")).as_dict(), related=[])
    card, _ = F.judge_row(MasterProfile(), row, _date(2026, 11, 15))
    assert card["result"] == F.VERIFY and card["basis_note"] == L.RELAXED_NOTE
    assert V.verify_rows([row]) == [(row["title"], "제목: 입주자격 완화·선계약 후 검증")]
    d = dataclasses.replace(_n12_draft(), relaxed=L.RELAXED_NOTE + " — p.1 '소득요건적용배제'")
    p = HouseholdProfile(profile_id="T", age=45, marital_status="미혼", household_size=1, monthly_income=1, total_assets=1,
                         car_value=0, home_ownership="무주택")
    r, checks = grading.judge(d, p, "청년")
    assert r.verdict == "MANUAL_REVIEW" and [(c.kind, c.page) for c in checks] == [("relaxed", 1)]
    shown = display_result(r.verdict, r.review_reasons, len(checks), {c.kind for c in checks})
    assert shown.group == HOLD_GROUP and "완화" in shown.title and shown.todo == L.RELAXED_NOTE
