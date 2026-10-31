# -*- coding: utf-8 -*-
"""test_d4_match.py — ④-4 2차: '내 조건으로 공고 찾기' 양식(form_spec.master_form)과 판정 API /match·/whatif.

공개 화면(Next.js /find)은 양식대로 그리고 결과를 보여 주기만 한다 — 양식이 Streamlit 찾기 화면과 같은 항목을 묻는지,
API의 What-if가 src/whatif.py를 직접 부른 결과와 같은지 확인한다.
"""
from datetime import date

import form_spec as F
import pytest
import whatif
from matcher import MasterProfile, match_all
from notices_data import ALL_NOTICES
from profile_form import WIDGETS
from profile_io import HOUSEHOLD_FIELDS, MASTER_FIELDS, master_to_dict

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import api.main as api  # noqa: E402

client = TestClient(api.app)
AT = "2026-10-14T12:00:00"
SINGLE = MasterProfile(home_self="무주택", home_household="무주택", income_self=4_000_000, income_household=4_000_000,
                       assets_self=50_000_000, assets_household=50_000_000, car_self=0, car_household=0,
                       birth_date=date(1996, 1, 1),
                       common={"marital_status": "미혼", "household_size": 1, "residence_area": "서울특별시"})


def test_master_form_asks_what_the_streamlit_find_page_asks():
    names = [f["name"] for f in F.master_form()["fields"]]
    assert len(names) == len(set(names))
    assert set(names) == {n for _, n, _ in WIDGETS} | {"children_birth_dates"}
    for n in names:
        if n.startswith(F.MASTER):
            assert n[len(F.MASTER):] in MASTER_FIELDS, n
        else:
            assert n in HOUSEHOLD_FIELDS, n


def test_master_form_endpoint():
    form = client.get("/match/form").json()
    assert form == F.master_form()
    assert set(form["collapsed"]) <= set(form["sections"])
    assert {f["section"] for f in form["fields"]} <= set(form["sections"])


def test_match_adds_display_schedule_and_near_misses():
    j = client.post("/match", json={"profile": master_to_dict(SINGLE), "at": AT}).json()
    matches = match_all(SINGLE, ALL_NOTICES)
    assert [(m["notice_id"], m["layer"]) for m in j["matches"]] == [(x.notice.notice_id, x.layer) for x in matches]
    groups = {"ELIGIBLE": "지원 가능", "INELIGIBLE": "지원 불가", "NEEDS_INFO": "보류", "MANUAL_REVIEW": "보류"}
    assert all(m["display"]["group"] == groups[m["verdict"]] for m in j["matches"])
    assert sum(j["schedule_counts"].values()) == j["notices_total"] == len(ALL_NOTICES)
    assert j["schedule_counts"]["OPEN"] == 5         # 2026.10.14. 정오에 접수 중인 공고(test_d2b와 같은 날)
    assert all(m["windows"] for m in j["matches"] if m["schedule"]["window"])
    want = whatif.near_misses(SINGLE, matches)
    assert [(n["notice_id"], n["layer"]) for n in j["near_misses"]] == [(n.match.notice.notice_id, n.match.layer)
                                                                         for n in want]
    t = next(t for n in j["near_misses"] for t in n["thresholds"])
    assert t["gap"] == t["current"] - t["limit"] > 0


def test_near_misses_follow_only_open():
    j = client.post("/match", json={"profile": master_to_dict(SINGLE), "at": AT, "only_open": True}).json()
    open_ids = {m["notice_id"] for m in j["matches"]}
    assert {n["notice_id"] for n in j["near_misses"]} <= open_ids


@pytest.mark.parametrize("scenario,extra,change", [
    ("marry", {"marriage_date": "2026-10-01", "spouse_income": 3_000_000, "spouse_assets": 10_000_000, "spouse_car": 0},
     lambda m: whatif.marry(m, date(2026, 10, 1), 3_000_000, 10_000_000, 0, False, False)),
    ("prenuptial", {}, lambda m: whatif.marry(m, None, None, None, None, False, False, prenuptial=True)),
    ("move", {"region": "서울특별시"}, lambda m: whatif.move(m, "서울특별시")),
    ("separate", {}, whatif.separate_household),
])
def test_whatif_equals_module(scenario, extra, change):
    j = client.post("/whatif", json={"profile": master_to_dict(SINGLE), "scenario": scenario, **extra}).json()
    res = whatif.run_scenario(api.SCENARIOS[scenario], SINGLE, change, ALL_NOTICES)
    assert (j["before"], j["after"]) == (res.before, res.after)
    assert [(g["notice_id"], g["layer"]) for g in j["gained"]] == [(x.notice.notice_id, x.layer) for x in res.gained]
    assert [(g["notice_id"], g["layer"]) for g in j["lost"]] == [(x.notice.notice_id, x.layer) for x in res.lost]
    assert all(g["reason"] for g in j["lost"])


def test_whatif_errors():
    body = master_to_dict(SINGLE)
    assert client.post("/whatif", json={"profile": body, "scenario": "bogus"}).status_code == 422
    assert client.post("/whatif", json={"profile": body, "scenario": "move", "region": "없는지역"}).status_code == 422
    assert client.post("/whatif", json={"profile": {"schema": "x"}, "scenario": "separate"}).status_code == 422
