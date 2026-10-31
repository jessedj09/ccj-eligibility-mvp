# -*- coding: utf-8 -*-
"""test_d4_form.py — ④-4: 입력 양식 정의(src/form_spec.py)와 판정 API GET /form · birth_date.

공개 화면(Next.js)은 /form이 주는 양식대로만 그린다 — 양식이 계층이 읽는 항목을 빠뜨리면 그 조건은 늘 '정보 부족'이 된다.
"""
from datetime import date, timedelta

import form_spec as F
import pytest
from notices_data import ALL_NOTICES
from rule_engine import HouseholdProfile

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import api.main as api  # noqa: E402

client = TestClient(api.app)
PROFILE_FIELDS = set(HouseholdProfile.__dataclass_fields__)


def test_every_layer_input_is_asked_or_derived():
    for nid, n in ALL_NOTICES.items():
        for layer, ls in n.layers.items():
            asked = {f["name"] for f in F.fields_for(ls.inputs)}
            for name in ls.inputs:
                assert name in asked or name in F.DERIVED, (nid, layer, name)


def test_fields_are_profile_fields_with_known_types():
    types = {"age", "select", "tri", "bool", "int", "amount", "car", "date", "children", "region"}
    every = set(F.REGION_LABELS) | set(F.CHOICE_FIELDS) | set(F.C4_CHOICES) | set(F.C4_BOOLS) | set(F.C4_AMOUNTS)
    for f in F.fields_for(every | {"house_head_status", "is_social_rookie", "student_status", "grad_or_dropout_date",
                                   "marriage_date", "parents_count"}):
        assert f["name"] in PROFILE_FIELDS and f["type"] in types, f
        if "show_if" in f:
            assert f["show_if"]["field"] in PROFILE_FIELDS


def test_only_layer_inputs_are_added():
    n = ALL_NOTICES["N12"]
    names = [f["name"] for f in F.fields_for(n.layers["청년"].inputs)]
    assert "school_area" not in names and "marriage_date" not in names
    assert names[:2] == ["age", "marital_status"]


def test_streamlit_screen_uses_the_same_definitions():
    src = (api.Path(api.__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    assert "from form_spec import" in src
    for const in ("REGION_LABELS = {", "CHOICE_FIELDS = {", "C4_BOOLS = {", "C4_AMOUNTS = {", "C4_CHOICES = {"):
        assert const not in src, f"app.py가 {const}를 따로 정의함 — src/form_spec.py 한 곳에"


def test_form_endpoint_has_scope_notes_and_region_options():
    nid = next(nid for nid, n in ALL_NOTICES.items() for ls in n.layers.values() if "residence_area" in ls.inputs)
    layer = next(lay for lay, ls in ALL_NOTICES[nid].layers.items() if "residence_area" in ls.inputs)
    j = client.get("/form", params={"notice_id": nid, "layer": layer}).json()
    assert j["announcement_date"] == ALL_NOTICES[nid].announcement_date.isoformat()
    region = next(f for f in j["fields"] if f["name"] == "residence_area")
    assert region["type"] == "region" and "서울특별시" in j["region_options"] and j["region_options"][0] == "해당없음"
    assert any(f.get("scope") for f in j["fields"])
    assert client.get("/form", params={"notice_id": "N12", "layer": "없음"}).status_code == 404
    assert client.get("/form", params={"layer": "청년"}).status_code == 422


def test_birth_date_becomes_age_on_announcement_day():
    ann = ALL_NOTICES["N12"].announcement_date
    turns_40 = date(ann.year - 40, ann.month, ann.day)

    def age_of(birth):
        body = {"birth_date": birth.isoformat(), "marital_status": "미혼", "home_ownership": "무주택", "household_size": 1}
        r = client.post("/evaluate", json={"notice_id": "N12", "layer": "청년", "profile": body})
        assert r.status_code == 200, r.text
        return r.json()

    on_day, day_after = age_of(turns_40), age_of(turns_40 + timedelta(days=1))
    assert on_day["verdict"] != day_after["verdict"] or on_day["failed"] != day_after["failed"]
    both = {"birth_date": "2000-01-01", "age": 25, "marital_status": "미혼", "home_ownership": "무주택", "household_size": 1}
    assert client.post("/evaluate", json={"notice_id": "N12", "layer": "청년", "profile": both}).status_code == 422
    bad = dict(both, birth_date="2000-13-01")
    bad.pop("age")
    assert client.post("/evaluate", json={"notice_id": "N12", "layer": "청년", "profile": bad}).status_code == 422
