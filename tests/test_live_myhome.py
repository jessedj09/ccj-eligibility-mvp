# -*- coding: utf-8 -*-
"""마이홈 보조 정보(묶음 C, 2026-11-14) — 국토교통부 마이홈포털 공공주택 모집공고 조회. 네트워크 없이 표본으로.

표본: tests/fixtures/live/myhome_rent.json·myhome_sale.json(2026-11-14 응답 첫 쪽, 인증키 없음).
"""
import json
import os
import sys
import uuid
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]
os.environ.setdefault("CCJ_STORE", "off")

import live_notices as L  # noqa: E402
import store as S  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "live"
RENT = json.loads((FX / "myhome_rent.json").read_text(encoding="utf-8"))
SALE = json.loads((FX / "myhome_sale.json").read_text(encoding="utf-8"))
TEST_URL = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL 없음 — 실제 DB 시험은 CI(postgres 서비스)에서")


def test_info_keyed_by_lh_pan_id():
    info = L.myhome_info(L.parse_myhome(RENT) + L.parse_myhome(SALE))
    assert L.myhome_total(RENT) >= 100 and len(info) > 50
    d = info["2015122300021012"]                    # 대전문화1단지 50년공공임대 — 공식 링크의 panId = LH 공고 ID
    assert d["address"] == "대전광역시 중구 보문산로161번길 55" and d["complexes"] == ["대전문화1"]
    assert d["deposit"] == [14461000, 14461000] and d["supply"] == 130 and d["window"] == ["2026-11-26", "2026-11-26"]
    assert all(k.isdigit() for k in info)           # 지방공사 공고(LH 링크 없음)는 빠진다


def test_address_dedupe_and_money_range():
    assert L._address("경기도 남양주시 별내동 816-1 경기도 남양주시 별내동 816-1") == "경기도 남양주시 별내동 816-1"
    assert L._address(" 서울  중구 ") == "서울 중구"
    assert L._money_range([0, 3000000, 1000000, None, "x"]) == [1000000, 3000000] and L._money_range([0]) is None


def test_with_myhome_fills_missing_window_only():
    n = L.LiveNotice(source="lh", external_id="1", title="t", issuer="LH", kind="국민임대", region="", announced="2026-11-05",
                     window_start=None, window_end="2026-11-30", status="공고중", url="")
    got = L.with_myhome(n, {"window": ["2026-11-20", "2026-11-22"]})
    assert (got.window_start, got.window_end) == ("2026-11-20", "2026-11-30")      # 목록의 마감일은 그대로
    done = L.with_myhome(got, {"window": ["2026-12-01", "2026-12-02"]})
    assert done.window_start == "2026-11-20"                                        # LH 상세 값이 있으면 바꾸지 않는다
    assert L.with_myhome(n, None) is n


def test_collect_myhome_pages(monkeypatch):
    import collect_live_notices as C
    calls = []

    def fake(url, key, params):
        calls.append((url, params["pageNo"]))
        return RENT if url == L.MYHOME_RENT and params["pageNo"] == 1 else SALE if url == L.MYHOME_SALE else \
            {"response": {"body": {"totalCount": L.myhome_total(RENT), "item": []}}}
    monkeypatch.setattr(C, "_get", fake)
    info = C.collect_myhome("k")
    assert "2015122300021012" in info and (L.MYHOME_SALE, 1) in calls and (L.MYHOME_RENT, 2) in calls


def test_find_card_shows_info():
    import find as F
    row = {"source": "lh", "external_id": "2015122300021012", "title": "대전문화1단지 50년공공임대주택 예비입주자 모집공고",
           "issuer": "LH", "kind": "공공임대", "region": "대전광역시", "announced": "2026-11-12", "window_start": "2026-11-26",
           "window_end": "2026-11-26", "status": "공고중", "url": "u", "program": None, "template": None, "registered_id": None,
           "route": "unsupported", "related": [],
           "extra": {"address": "대전광역시 중구", "addresses": 3, "deposit": [1, 2], "rent": None, "supply": 130}}
    from profile_io import master_from_dict
    m = master_from_dict({"schema": "ccj-profile/1", "master": {"birth_date": "1998-03-01"}, "common": {}})
    card, _ = F.judge_row(m, row, date(2026, 11, 14))
    assert card["info"] == {"address": "대전광역시 중구", "deposit": [1, 2], "supply": 130, "more_addresses": 2}
    card, _ = F.judge_row(m, dict(row, extra=None), date(2026, 11, 14))
    assert card["info"] is None


@pytest.fixture
def db():
    schema = "t_" + uuid.uuid4().hex[:10]
    s = S.Store(TEST_URL, schema=schema)
    assert s.migrate()
    yield s
    s._run(lambda c: c.execute(f'DROP SCHEMA "{schema}" CASCADE'))
    s.close()


@needs_db
def test_db_extra_kept_when_myhome_fails(db):
    n = L.LiveNotice(source="lh", external_id="2015122300021012", title="t", issuer="LH", kind="공공임대", region="",
                     announced="2026-11-12", window_start=None, window_end=None, status="공고중", url="")
    db.upsert_live([dict(n.as_dict(), extra={"address": "대전광역시 중구", "supply": 130})])
    db.upsert_live([dict(n.as_dict(), extra=None)])                      # 다음 수집에서 마이홈 실패
    assert db.live_notices(open_only=False)[0]["extra"] == {"address": "대전광역시 중구", "supply": 130}
