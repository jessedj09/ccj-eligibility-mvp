# -*- coding: utf-8 -*-
"""흥신소 주 흐름 ②-2 — 기본 조건 → 지금 모집 중인 공고 목록(src/find.py, POST /find)."""
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "tools")]
os.environ.setdefault("CCJ_STORE", "off")

import find as F  # noqa: E402
import live_notices as L  # noqa: E402
from profile_io import master_from_dict  # noqa: E402
from schedule import KST  # noqa: E402

AT = datetime(2026, 11, 10, 12, 0, tzinfo=KST)
YOUTH = {"schema": "ccj-profile/1",
         "master": {"birth_date": "1998-03-01", "home_self": "무주택", "home_household": "무주택",
                    "income_household": 3_000_000, "assets_household": 50_000_000, "car_household": 0},
         "common": {"marital_status": "미혼", "household_size": 1, "house_head_status": "세대주", "residence_area": "서울특별시"}}


def row(title, kind, ext, announced="2026-11-05", start="2026-11-15", end="2026-11-20", issuer="LH", region="경기도",
        source="lh", status="공고중"):
    return {"source": source, "external_id": ext, "title": title, "issuer": issuer, "kind": kind, "region": region,
            "announced": date.fromisoformat(announced), "window_start": start and date.fromisoformat(start),
            "window_end": end and date.fromisoformat(end), "status": status, "url": f"https://example.test/{ext}",
            "program": None, "template": None, "registered_id": None, "route": None, "detail_key": {},
            "last_seen": AT - timedelta(hours=2)}


ROWS = [
    row("인천논현2단지 국민임대주택 예비입주자 모집 공고", "국민임대", "A1", region="인천광역시"),
    row("과천지식정보타운 S12블록 행복주택 입주자 모집공고", "행복주택", "A2", announced="2026-10-28", start="2026-11-09",
        end="2026-11-11"),                                                      # 등록 공고 N27
    row("○○ 공공지원 민간임대 입주자 모집", "민간임대", "A3"),                     # 판정하지 않는 사업
    row("△△ 공공분양주택 입주자 모집", "공공분양", "A4", end="2026-11-01"),       # 마감 — 빠짐
]


def run(rows=ROWS, **kw):
    return F.find_open(master_from_dict(YOUTH), F.relink(rows), AT, **kw)


def card(out, ext):
    return next(c for c in out["items"] if c["external_id"] == ext)


def test_three_bases_and_labels():
    out = run()
    keys = {c["external_id"] for c in out["items"]}
    assert "A4" not in keys                                            # 마감한 공고는 빼고
    a1, a2, a3 = card(out, "A1"), card(out, "A2"), card(out, "A3")
    assert a2["basis"] == F.CONFIRMED and a2["registered_id"] == "N27"
    assert a1["basis"] == F.PREVIEW and a1["preview_from"]["notice_id"].startswith("N")
    assert "같은 사업 최근 공고" in a1["basis_note"]
    assert a3["basis"] == F.NONE and a3["result"] == F.UNJUDGED and a3["url"]
    # 예비 판정의 '지원 가능'은 늘 단서와 함께(2026-11-10 사용자 결정)
    assert out["labels"][F.LIKELY] == "지원 가능 (단, 공고문 내 지원자격 상세 확인 필요)"
    assert all(c["label"] == F.LABELS[c["result"]] for c in out["items"])
    assert out["notice"] is None and not out["stale"]


def test_order_groups_then_open_then_deadline():
    out = run()
    ranks = [(F.GROUPS.index(c["result"]), {"open": 0, "upcoming": 1}.get(c["schedule"]["code"], 2)) for c in out["items"]]
    assert ranks == sorted(ranks)
    a2 = card(out, "A2")
    assert a2["schedule"]["code"] == "open" and a2["schedule"]["days"] == 1


def test_filters_kind_and_region():
    out = run(kind=F.SALE)
    assert all(c["kind"] == F.SALE for c in out["items"])
    out = run(regions=["인천광역시"])
    assert "A1" in {c["external_id"] for c in out["items"]}
    assert "A3" not in {c["external_id"] for c in out["items"]}       # 경기도 공고는 빠짐


def test_store_down_and_stale():
    out = F.find_open(master_from_dict(YOUTH), [], AT, live_ok=False)
    assert "불러오지 못했습니다" in out["notice"]
    assert all(c["source"] == "registered" for c in out["items"])
    old = [dict(r, last_seen=AT - timedelta(hours=30)) for r in ROWS]
    out = run(old)
    assert out["stale"] and "갱신되지 않았습니다" in out["notice"]


def test_questions_skip_given_fields():
    out = run()
    asked = {q["field"] for q in out["questions"]}
    assert not asked & {"age", "home_ownership", "monthly_income", "total_assets", "car_value", "household_size"}


def test_relink_fixes_happy_housing_kind_and_subtypes():
    r = F.relink([row("구리갈매역세권 A-1BL 신혼희망타운 행복주택 최초 입주자 모집공고('26.10.27)", "행복주택(신혼희망)", "B1",
                      announced="2026-10-27")])[0]
    assert r["program"] == "행복주택(신혼희망타운)" and r["registered_id"] == "N28" and r["route"] == L.REGISTERED
    r = F.relink([row("평창장평 통합공공임대주택(고령자복지형) 입주자 모집", "통합공공임대", "B2", announced="2026-10-30")])[0]
    assert r["registered_id"] is None and r["route"] == L.UNSUPPORTED     # 일반형(N35)과 잇지 않고, 일반형 틀로 판정하지 않음
    r = F.relink([row("평창장평 통합공공임대주택(일반형) 입주자 모집", "통합공공임대", "B3", announced="2026-10-30")])[0]
    assert r["registered_id"] == "N35"


def test_match_analyzed_upload():
    r = F.relink([ROWS[0]])[0]
    cands = [{"sha256": "x" * 64, "issuer": "LH", "program": "국민임대주택", "title": "인천논현2단지 국민임대주택 예비입주자 모집",
              "announcement_date": date(2026, 11, 5)},
             {"sha256": "y" * 64, "issuer": "LH", "program": "국민임대주택", "title": "인천논현2단지 국민임대주택 예비입주자 모집",
              "announcement_date": date(2026, 11, 6)}]
    assert F.match_analyzed(r, cands) == "x" * 64
    assert F.match_analyzed(r, cands[1:]) is None                       # 공고일이 다르면 다른 공고


def test_kind_and_sido():
    assert F.kind_of({"template": "lh.public_sale"}) == F.SALE
    assert F.kind_of({"template": "lh.select_rental"}) == F.RENT          # 분양전환 임대는 임대
    assert F.kind_of({"kind": "분양주택", "title": "잔여세대 분양"}) == F.SALE
    assert F.sido_of("수원시") == "경기도" and F.sido_of("서울특별시") == "서울특별시"


# ------------------------------------------------------------------ API
def _client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)


def test_api_form_and_find_without_store():
    c = _client()
    form = c.get("/find/form").json()
    names = {f["name"] for f in form["fields"]}
    assert {"master.birth_date", "marital_status", "household_size", "master.home_household", "residence_area"} <= names
    assert "student_status" not in names and form["filters"]["kind"]["options"] == ["둘 다", "임대", "분양"]
    r = c.post("/find", json={"profile": YOUTH, "at": AT.isoformat()})
    assert r.status_code == 200
    j = r.json()
    assert set(j["counts"]) == set(F.GROUPS) and j["notice"]               # 저장소 없음 — 등록 공고만
    assert c.post("/find", json={"profile": {"schema": "x"}}).status_code == 422


class _Spy:
    """저장소 대역 — 흥신소가 읽기만 하는지(조건을 쓰지 않는지) 본다."""
    available = True

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def f(*a, **k):
            self.calls.append(name)
            if name == "live_notices":
                return list(ROWS)
            if name == "demoted_programs":
                return frozenset()
            return [] if name in ("analyzed_notices",) else None
        return f


def test_api_find_reads_only_and_request_analysis_once(monkeypatch):
    import api.main as M
    spy = _Spy()
    monkeypatch.setattr(M, "get_store", lambda: spy)
    monkeypatch.setitem(M._live, "t", 0.0)
    c = _client()
    j = c.post("/find", json={"profile": YOUTH, "at": AT.isoformat()}).json()
    assert j["notice"] is None and any(x["basis"] == F.PREVIEW for x in j["items"])
    assert set(spy.calls) <= {"live_notices", "analyzed_notices", "demoted_programs"}      # 조건을 저장하지 않는다
    spy.calls.clear()
    first = c.post("/find/request-analysis", json={"source": "lh", "external_id": "A1"}).json()
    again = c.post("/find/request-analysis", json={"source": "lh", "external_id": "A1"}).json()
    assert first["ok"] and again == {"ok": True, "counted": False}
    assert spy.calls == ["request_analysis"]
