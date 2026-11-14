# -*- coding: utf-8 -*-
"""SH — 서울시 주택포털 목록·상세 요약 읽기(실시간 공고 ②-5, 2026-11-12). 네트워크 없이 표본으로.

표본: tests/fixtures/live/seoul_lease_list.html·seoul_sale_list.html(목록 첫 쪽), seoul_bodies.json(2026-11-12 주택포털 SH 공고 86건의
상세 요약 — 공고명·청약유형·게시일·발표일·모집상태·본문).
"""
import json
import re
import sys
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

import live_notices as L  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "live"
BODIES = json.loads((FX / "seoul_bodies.json").read_text(encoding="utf-8"))


def test_parse_lists_and_format_guard():
    lease = L.parse_seoul_list((FX / "seoul_lease_list.html").read_text(encoding="utf-8"), "임대")
    assert len(lease) == 10
    r = lease[1]
    assert r["type"] == "희망하우징" and r["status"] == "모집중" and r["posted"] == "2026-10-28" and r["winners"] == "2027-01-26"
    assert r["view"].startswith("/site/main/sh/publicLease/view?") and not r["title"].startswith("-->")
    sale = L.parse_seoul_list((FX / "seoul_sale_list.html").read_text(encoding="utf-8"), "분양")
    assert sale[0]["type"] == "주택분양" and sale[0]["status"] == ""
    # 화면 구조가 바뀌면 조용히 0건이 아니라 실패로
    with pytest.raises(L.SeoulFormatError):
        L.parse_seoul_list("<table><tr><th>번호</th><th>제목</th></tr></table>", "임대")
    with pytest.raises(L.SeoulFormatError):
        L.parse_seoul_list("<div>점검 중</div>", "임대")


def test_notice_rows_skip_non_notices_and_keep_stable_id():
    row = {"type": "행복주택", "title": "2026년 2차 행복주택 입주자 모집공고", "posted": "2026-08-28", "winners": "2026-12-01",
           "status": "모집중", "view": "/site/main/sh/publicLease/view?seq=3&cp=1", "kind": "임대"}
    n = L.seoul_notice(row)
    assert n.source == L.SEOUL_SOURCE and n.issuer == "SH" and n.url.startswith(L.SEOUL_BASE)
    # seq(목록 순서)가 바뀌어도 같은 ID
    assert L.seoul_notice(dict(row, view="/site/main/sh/publicLease/view?seq=9&cp=2")).external_id == n.external_id
    for t in ("2025년 1차 행복주택 입주자 모집(2025.04.25.공고) 최종 청약 경쟁률 게시", "제48차 장기전세주택 당첨자 및 예비자 발표",
              "2026년 재개발임대주택 입주자 모집 일정 연기 안내", "2025년 미리내집 연계형 공공한옥 입주자 모집공고 예비 3차"):
        assert L.seoul_notice(dict(row, title=t)) is None


def _recruitments():
    return [x for x in BODIES if not L.SEOUL_NOT_NOTICE.search(x["title"])]


def _window(x):
    w = L.seoul_window(x["body"], L.seoul_announced(x["body"]) or x["posted"], x["winners"])
    return (w["window_start"], w["window_end"]) if w else None


def test_window_read_rate_on_sample():
    """모집공고 70건 중 67건 이상 읽는다(못 읽는 공고는 요약에 날짜가 없거나 표 형식이 특이) — 규칙을 바꿀 때 떨어지면 안 된다."""
    rec = _recruitments()
    got = [x for x in rec if _window(x)]
    assert len(rec) == 70 and len(got) >= 67


# 등록 공고(사람이 공고문 원문으로 옮긴 접수기간)와 같은 공고의 주택포털 요약 — 2026-11-12 표본에서 짝지은 것
KNOWN = {
    "2026년 하반기 신혼·신생아 매입임대주택Ⅰ": ("2026-10-13", "2026-10-15"),       # N18
    "2026년 하반기 신혼·신생아 매입임대주택Ⅱ": ("2026-10-13", "2026-10-15"),       # N19
    "2026년 일반주택형 미리내집(공공한옥) 잔여세대": ("2026-09-03", "2026-09-04"),   # N21
    "(수정) 2026년 2차 장기미임대": ("2026-09-28", "2026-09-30"),                  # N22
    "제7차 장기전세주택2": ("2026-05-06", "2026-05-08"),                           # N23
    "제8차 장기전세주택2": ("2026-09-07", "2026-09-09"),                           # N24
    "제49차 장기전세주택 입주자 모집공고": ("2026-01-08", "2026-01-19"),            # N25 — 12월 공고, 1월 접수(해를 넘김)
    "제50차 장기전세주택 입주자 모집공고": ("2026-05-13", "2026-05-18"),            # N26
    "2025년 제1차 국민임대주택": ("2025-09-02", "2025-09-17"),                      # N60
    "2026년 다자녀 매입임대주택": ("2026-06-09", "2026-06-11"),                     # N65
    "2026년 1차 서울주택도시개발공사 행복주택": ("2026-06-15", "2026-06-17"),        # N68
    "[정정] 2025년 1차 행복주택": ("2025-05-07", "2025-05-09"),                     # N69
    "[정정]2025년 3차 행복주택": ("2026-01-16", "2026-01-20"),                      # N70
    # 후순위·2순위 접수일까지 — 등록 일정은 선순위만이라 범위가 더 넓다(틀린 값 아님)
    "2026년 국민임대주택 입주자 모집공고(2026.08.20": ("2026-08-31", "2026-09-16"),  # N53
    # 사전청약 당첨자 접수(10.26~27)·포기 신청(10.30)은 빼고 특별공급부터 — 분양은 운영에서 청약홈 값을 쓴다
    "[정정] 고덕강일지구 3단지": ("2026-11-02", "2026-11-06"),                       # N52
}


@pytest.mark.parametrize("head,want", list(KNOWN.items()))
def test_window_matches_registered_schedule(head, want):
    x = next(b for b in BODIES if b["title"].startswith(head) and not L.SEOUL_NOT_NOTICE.search(b["title"]))
    assert _window(x) == want


def test_window_rejects_out_of_range_and_other_dates():
    body = ("■ 모집공고일: 2026.10.01. ■ 서류제출기간: 2026.10.20 ~ 10.22 ■ 당첨자발표: 2026.12.01 "
            "■ 계약: 2026.12.10 ~ 12.12")
    assert L.seoul_window(body, "2026-10-01", "2026-12-01") is None          # 접수 아닌 날짜만 있음
    body = "■ 접수기간: 2027.05.01 ~ 2027.05.03"
    assert L.seoul_window(body, "2026-10-01", "2026-12-01") is None          # 당첨자 발표보다 늦음 — 버림
    body = "■ 접수일 ○ 인터넷접수: 2026. 11. 9.(월) 10:00 ~ 2026. 11. 11.(수) 17:00 ■ 서류심사대상자 발표: 2026. 11. 13."
    assert L.seoul_window(body, "2026-10-28", "-") == {"window_start": "2026-11-09", "window_end": "2026-11-11"}


def test_house_no_and_announced():
    x = next(b for b in BODIES if b["title"].startswith("[정정] 고덕강일지구 3단지"))
    assert L.seoul_house_no(x["body"]) == "2026000373" and L.seoul_announced(x["body"]) == "2026-10-16"
    y = next(b for b in BODIES if b["title"].startswith("2026년 국민임대주택 입주자 모집공고(2026.08.20"))
    assert L.seoul_house_no(y["body"]) == "2026000379"


def test_title_program_links_to_templates_and_registered():
    def link(title, kind, posted):
        return L.link(L.LiveNotice(source=L.SEOUL_SOURCE, external_id="x", title=title, issuer="SH", kind=kind,
                                   region="서울특별시", announced=posted, window_start=None, window_end=None, status="모집중", url=""))
    assert link("2026년 하반기 신혼·신생아 매입임대주택Ⅰ 입주자 모집공고(2026.09.30.)", "매입임대주택", "2026-09-30").registered_id == "N18"
    assert link("2026년 하반기 신혼·신생아 매입임대주택Ⅱ 입주자 모집공고(2026.09.30.)", "매입임대주택", "2026-09-30").registered_id == "N19"
    assert link("2027년 1차 일반주택형 미리내집(신혼신생아매입임대주택Ⅱ) 입주자 모집공고", "매입임대주택", "2027-03-01").template == "sh.newlywed"
    assert link("2027년 다자녀 매입임대주택 입주자 모집공고", "매입임대주택", "2027-05-01").template == "sh.multichild_rental"
    assert link("[정정] 고덕강일지구 3단지 토지임대부 분양주택 입주자모집공고", "주택분양", "2026-10-16").registered_id == "N52"
    assert link("2027년 1차 행복주택 입주자 모집공고", "행복주택", "2027-05-01").template == "sh.happy_housing"
    assert link("2027년 1차 청년 매입임대주택 입주자모집공고", "매입임대주택", "2027-05-01").template == "sh.youth_rental"
    assert link("2026년 1차 청년 매입임대주택 입주자 모집공고", "매입임대주택", "2026-06-26").registered_id == "N71"
    assert link("2027년 1차 청년안심주택(공공임대) 입주자 모집공고", "청년안심주택", "2027-03-31").template == "sh.youth_safe"
    assert link("2026년 1차 청년안심주택(공공임대) 입주자모집 공고", "청년안심주택", "2026-03-31").registered_id == "N73"
    assert link("2027년 청년안심주택(민간임대) 입주자 모집공고", "청년안심주택", "2027-03-31").template is None
    assert link("2027년 1차 희망하우징(공공기숙사) 입주자 모집공고", "희망하우징", "2027-05-01").template == "sh.hope_housing"
    # 판정 틀이 없는 SH 사업은 판정하지 않는다(청년 매입임대의 변형 사업 포함)
    for t, k in (("2027년 자립준비청년 매입임대주택 입주자모집공고", "매입임대주택"), ("2027년 1차 기숙사형 청년주택 입주자모집 공고", "매입임대주택"),
                 ("2027년 위국헌신 청년 매입임대주택 입주자모집", "매입임대주택")):
        assert link(t, k, "2027-05-01").route == L.UNSUPPORTED


def test_merge_seoul_with_applyhome_by_house_no_uses_applyhome_window():
    seoul = {"source": L.SEOUL_SOURCE, "external_id": "abc", "title": "[정정] 고덕강일지구 3단지 토지임대부 분양주택 입주자모집공고",
             "issuer": "SH", "announced": "2026-10-16", "window_start": "2026-11-02", "window_end": "2026-11-06", "status": "",
             "route": L.REGISTERED, "registered_id": "N52", "detail_key": {"house_no": "2026000373"}, "url": "u1"}
    ah = {"source": L.APPLYHOME_SOURCE, "external_id": "2026000373", "title": "고덕강일지구 3단지 토지임대부(본청약)", "issuer": "SH",
          "announced": "2026-10-16", "window_start": "2026-11-02", "window_end": "2026-11-07", "status": "접수중",
          "route": L.TEMPLATE, "registered_id": None, "url": "u2"}
    out = L.merge_duplicates([ah, seoul])
    assert len(out) == 1
    m = out[0]
    assert m["source"] == L.SEOUL_SOURCE and m["window_end"] == "2026-11-07" and m["registered_id"] == "N52"
    assert m["related"][0]["source"] == L.APPLYHOME_SOURCE


def test_closed_status_and_unknown_schedule_text():
    n = L.seoul_notice({"type": "행복주택", "title": "2026년 2차 행복주택 입주자 모집공고", "posted": "2026-08-28", "winners": "-",
                        "status": "모집마감", "view": "/v?seq=1", "kind": "임대"})
    assert not L.is_open(n, date(2026, 9, 1))
    import find as F
    s = F.schedule_of({"status": "모집중", "window_start": None, "window_end": None}, date(2026, 11, 12))
    assert s["code"] == "unknown" and s["text"] == "모집중 · 접수 일정은 공고문 확인"


def test_collector_seoul_pages_and_details(monkeypatch):
    """수집기: 목록을 읽어 최근 2개월만, 모집 중인 공고만 상세를 열어 접수기간을 채운다(네트워크 대신 표본)."""
    import collect_live_notices as C
    lease = (FX / "seoul_lease_list.html").read_text(encoding="utf-8")
    sale = (FX / "seoul_sale_list.html").read_text(encoding="utf-8")
    body = next(b for b in BODIES if b["title"].startswith("2026년 3차 희망하우징"))["body"]
    opened = []

    def fake(url):
        opened.append(url)
        if "publicLease/list" in url:
            return lease if "cp=1" in url else "<table><tr><th>번호</th><th>청약유형</th><th>공고명</th><th>공고게시일</th><th>발표일</th></tr></table>"
        if "publicSale/01/list" in url:
            return sale
        return f"<div>{body} 목록 #content_wrap</div>"
    monkeypatch.setattr(C, "_get_html", fake)
    today = date(2026, 11, 2)
    rows = C.collect_seoul("", today)
    assert rows and all(r.announced >= "2026-09-01" for r in rows) and all(r.source == L.SEOUL_SOURCE for r in rows)
    needed = {(r.source, r.external_id) for r in rows}
    out, fetched = C.add_details("", rows, needed, today)
    views = [u for u in opened if "/view" in u]
    assert len(views) == sum(1 for r in rows if C._seoul_wants_detail(r, today)) and fetched
    hope = next(r for r in out if r.title.startswith("2026년 3차 희망하우징"))
    assert (hope.window_start, hope.window_end) == ("2026-11-09", "2026-11-11")
