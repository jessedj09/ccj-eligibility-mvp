# -*- coding: utf-8 -*-
"""test_d2b_profile_api.py — 프로필 저장 파일(ccj-profile/1)과 판정 API(D2b).

저장 → 불러오기를 거쳐도 판정이 같아야 하고, API는 화면과 같은 엔진·매처를 그대로 부른 결과를 돌려줘야 한다.
"""
import ast
import json
from datetime import date
from pathlib import Path

import pytest
from matcher import MasterProfile, match_all
from notices_data import ALL_NOTICES
from profile_form import WIDGETS, widget_state
from profile_io import ProfileFormatError, household_from_dict, master_from_dict, master_to_dict
from rule_engine import HouseholdProfile, evaluate

PAGE = Path(__file__).resolve().parent.parent / "pages" / "1_내_조건으로_공고_찾기.py"

NEWLYWED = MasterProfile(
    home_self="무주택", home_household="무주택", income_self=2_500_000, income_household=5_000_000,
    assets_self=30_000_000, assets_household=120_000_000, car_self=0, car_household=15_000_000,
    birth_date=date(1994, 5, 17),
    common=dict(marital_status="혼인중", marriage_date=date(2023, 3, 2), household_size=3, house_head_status="세대주",
                dual_income=True, children_birth_dates=[date(2025, 1, 9)], residence_area="서울특별시",
                income_base_area="서울특별시", spouse_residence_area="서울특별시", owned_home_in_5y=False,
                student_status=None, grad_or_dropout_date=None, is_social_rookie=None, housing_weak_type="해당없음"))
YOUTH = MasterProfile(
    home_self="무주택", home_household="주택보유", income_self=2_800_000, income_household=9_000_000,
    assets_self=20_000_000, assets_household=600_000_000, car_self=0, car_household=20_000_000,
    birth_date=date(2001, 3, 1),
    common=dict(marital_status="미혼", household_size=3, house_head_status="세대원", dual_income=False,
                children_birth_dates=[], residence_area="서울특별시", student_status="취업준비생",
                grad_or_dropout_date=date(2025, 2, 20), parents_count=2, parents_monthly_income=6_000_000,
                is_employed=False, registered_with_parents=True))
UNKNOWNS = MasterProfile(common=dict(marital_status="미혼", household_size=None, children_birth_dates=None))


def roundtrip(m):
    return master_from_dict(json.loads(json.dumps(master_to_dict(m), ensure_ascii=False)))


@pytest.mark.parametrize("m", [NEWLYWED, YOUTH, UNKNOWNS], ids=["newlywed", "youth", "unknowns"])
def test_saved_profile_roundtrip_is_identical_and_judges_the_same(m):
    back = roundtrip(m)
    assert back == m
    before = [(x.notice.notice_id, x.layer, x.verdict) for x in match_all(m, ALL_NOTICES)]
    after = [(x.notice.notice_id, x.layer, x.verdict) for x in match_all(back, ALL_NOTICES)]
    assert before == after


def test_unknown_household_size_stays_unknown():
    """common의 null(모름)은 그대로 — 빠뜨리면 HouseholdProfile 기본값(가구원수 1)이 돼 판정이 바뀐다."""
    d = master_to_dict(UNKNOWNS)
    assert d["common"]["household_size"] is None
    assert roundtrip(UNKNOWNS).common["household_size"] is None


@pytest.mark.parametrize("doc,msg", [
    ({"schema": "other"}, "schema"),
    ({"schema": "ccj-profile/1", "extra": 1}, "알 수 없는 항목"),
    ({"schema": "ccj-profile/1", "master": {"salary": 1}}, "master에 알 수 없는"),
    ({"schema": "ccj-profile/1", "common": {"favorite": 1}}, "common에 알 수 없는"),
    ({"schema": "ccj-profile/1", "common": {"monthly_income": 1}}, "master의 본인·세대 항목"),
    ({"schema": "ccj-profile/1", "master": {"birth_date": "1990/01/01"}}, "YYYY-MM-DD"),
    ({"schema": "ccj-profile/1", "common": {"children_birth_dates": "2020-01-01"}}, "YYYY-MM-DD"),
])
def test_bad_profile_files_are_rejected(doc, msg):
    with pytest.raises(ProfileFormatError, match=msg):
        master_from_dict(doc)


def test_household_from_dict():
    p = household_from_dict({"age": 30, "marital_status": "미혼", "home_ownership": "무주택", "marriage_date": "2020-01-02"})
    assert p.marriage_date == date(2020, 1, 2) and p.profile_id == "api"
    with pytest.raises(ProfileFormatError, match="필수 항목"):
        household_from_dict({"age": 30})


def _page_master_call():
    tree = ast.parse(PAGE.read_text(encoding="utf-8"))
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "MasterProfile")
    master = {k.arg for k in call.keywords if k.arg != "common"}
    common_call = next(k.value for k in call.keywords if k.arg == "common")
    return master, {k.arg for k in common_call.keywords}


def test_load_mapping_covers_everything_the_page_saves():
    """화면이 저장하는 항목(MasterProfile에 넘기는 항목)과 불러오기 표(WIDGETS)가 정확히 같아야 한다 — 새 질문을 화면에 추가하고
    표에 빠뜨리면 저장은 되는데 불러오기에서 사라진다."""
    master, common = _page_master_call()
    table_master = {n[7:] for _, n, _ in WIDGETS if n.startswith("master.")}
    table_common = {n for _, n, _ in WIDGETS if not n.startswith("master.")} | {"children_birth_dates"}
    assert master == table_master
    assert common == table_common
    assert len({k for k, _, _ in WIDGETS}) == len(WIDGETS)


def test_widget_state_values():
    s = widget_state(YOUTH)
    assert s["m_birth"] == date(2001, 3, 1) and s["m_inc_self_known"] and s["m_inc_self"] == 2_800_000
    assert s["m_employed"] == "아니오" and s["m_regpar"] == "예" and s["m_spdis"] == "모름"
    assert s["m_pcount"] == 2 and s["m_kids"] == 0 and s["m_head"] == "세대원"
    s = widget_state(NEWLYWED)
    assert s["m_kids"] == 1 and s["m_kid_0"] == date(2025, 1, 9) and s["m_marriage"] == date(2023, 3, 2)
    assert s["m_pinc_known"] is False and "m_pinc" not in s and s["m_grad"] is None


# ---- 판정 API ----
fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402

client = TestClient(app)


def test_health_and_notices():
    assert client.get("/health").json() == {"status": "ok", "notices": len(ALL_NOTICES)}
    r = client.get("/notices", params={"at": "2026-10-14T12:00:00"}).json()
    assert len(r["notices"]) == len(ALL_NOTICES) and r["at"].startswith("2026-10-14T12:00:00+09:00")
    assert {n["notice_id"] for n in r["notices"] if n["schedule"]["code"] == "OPEN"} == {"N4", "N8", "N17", "N18", "N19"}
    n25 = next(n for n in r["notices"] if n["notice_id"] == "N25")
    assert "일반(우선공급·장애인)" in n25["layers"] and n25["schedule_note"]


@pytest.mark.parametrize("nid,layer,kw", [
    ("N1", "신혼부부", dict(age=30, marital_status="혼인중", home_ownership="무주택", household_size=2,
                       monthly_income=3_000_000, total_assets=10_000_000, car_value=0, marriage_date=date(2023, 1, 1),
                       children_birth_dates=[])),
    ("N1", "신혼부부", dict(age=30, marital_status="혼인중", home_ownership="무주택", household_size=2,
                       monthly_income=99_000_000, total_assets=10_000_000, car_value=0, marriage_date=date(2023, 1, 1),
                       children_birth_dates=[])),
    ("N12", "청년", dict(age=25, marital_status="미혼", home_ownership="무주택", household_size=1)),
])
def test_evaluate_matches_engine(nid, layer, kw):
    body = {k: v.isoformat() if isinstance(v, date) else [x.isoformat() for x in v] if isinstance(v, list) else v
            for k, v in kw.items()}
    r = client.post("/evaluate", json={"notice_id": nid, "layer": layer, "profile": body})
    assert r.status_code == 200, r.text
    direct = evaluate(HouseholdProfile(profile_id="api", **kw), ALL_NOTICES[nid], layer)
    assert r.json()["verdict"] == direct.verdict
    assert {i["rule_id"] for i in r.json()["failed"]} == set(direct.failed)


def test_evaluate_errors():
    assert client.post("/evaluate", json={"notice_id": "N999", "layer": "청년", "profile": {}}).status_code == 404
    assert client.post("/evaluate", json={"notice_id": "N1", "layer": "없음", "profile": {}}).status_code == 404
    assert client.post("/evaluate", json={"notice_id": "N1", "layer": "신혼부부",
                                          "profile": {"age": 30, "bogus": 1}}).status_code == 422
    r = client.post("/evaluate", json={"notice_id": "N1", "layer": "신혼부부",
                                       "profile": {"age": 300, "marital_status": "미혼", "home_ownership": "무주택"}})
    assert r.status_code == 422 and "나이" in r.json()["detail"]


def test_match_equals_matcher_and_filters_by_schedule():
    body = master_to_dict(NEWLYWED)
    r = client.post("/match", json={"profile": body, "at": "2026-10-22T12:00:00"})
    assert r.status_code == 200
    got = [(m["notice_id"], m["layer"], m["verdict"]) for m in r.json()["matches"]]
    assert got == [(x.notice.notice_id, x.layer, x.verdict) for x in match_all(NEWLYWED, ALL_NOTICES)]
    assert sum(r.json()["counts"].values()) == len(got)
    # 2026.10.22.에는 전부 마감, 10.14.에는 그날 접수 중인 공고만
    assert client.post("/match", json={"profile": body, "at": "2026-10-22T12:00:00", "only_open": True}).json()["matches"] == []
    open_ids = {m["notice_id"] for m in client.post("/match", json={"profile": body, "at": "2026-10-14T12:00:00",
                                                                   "only_open": True}).json()["matches"]}
    assert open_ids == {"N4", "N8", "N17", "N18", "N19"}
    assert client.post("/match", json={"profile": {"schema": "x"}}).status_code == 422
