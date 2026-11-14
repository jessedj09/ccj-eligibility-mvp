# -*- coding: utf-8 -*-
"""R-⑤ 사업별 검증 상태 표시(2026-11-14 사용자 결정, 점검 세션 docs/13 2-4) — 판정은 바꾸지 않고 표시만."""
import json

import pytest
from fastapi.testclient import TestClient

import draft
import verification as V
from api import main as api

client = TestClient(api.app)
BODY = {"age": 25, "marital_status": "미혼", "home_ownership": "무주택", "household_size": 1}


def test_every_passing_program_has_a_status_and_none_is_verified_yet():
    progs = V.all_programs()
    assert [p["template"] for p in progs] == list(draft.PASSING)
    assert all(p["status"] == V.IN_PROGRESS and p["label"] == "검증 중" for p in progs)     # 채운 워크시트 사례 0건(2026-11-14)
    assert V.status_of("lh.youth_rental", demoted={"lh.youth_rental"}) == V.PAUSED
    assert V.status_of(None) is None


def test_recorded_program_is_verified_until_a_new_case_is_left_blank(monkeypatch, tmp_path):
    f = tmp_path / "status.json"
    f.write_text(json.dumps({"verified": {"lh.national_rental": {"verified_at": "2026-11-20", "cases": [25, 26]}}}), encoding="utf-8")
    monkeypatch.setattr(V, "STATUS_FILE", f)
    V._recorded.cache_clear()
    try:
        # 국민임대 JSON 사례(25·26)가 비어 있으면 기록이 있어도 '검증 중'
        assert V.status_of("lh.national_rental") == V.IN_PROGRESS
        cases = {"lh.national_rental": [{"user_verdict": "ELIGIBLE"}, {"user_verdict": "확인필요"}]}
        monkeypatch.setattr(V, "_json_cases_by_template", lambda: cases)
        assert V.status_of("lh.national_rental") == V.VERIFIED
        assert V.status_of("lh.national_rental", demoted={"lh.national_rental"}) == V.PAUSED   # 멈춤이 먼저
    finally:
        V._recorded.cache_clear()


def test_api_shows_status_without_changing_the_verdict():
    j = client.post("/evaluate", json={"notice_id": "N12", "layer": "청년", "profile": BODY}).json()
    assert j["verification"] == {"template": "lh.youth_rental", "status": "in_progress", "label": "검증 중",
                                 "note": V.NOTE[V.IN_PROGRESS]}
    v = client.get("/verification").json()["programs"]
    assert len(v) == len(draft.PASSING) and v[0]["program"]


@pytest.mark.parametrize("nid,template", [("N1", "lh.happy_housing"), ("N71", "sh.youth_rental"), ("N75", "sh.hope_housing")])
def test_registered_notices_map_to_their_program(nid, template):
    from rule_data import load_notice
    n = load_notice(nid)
    assert api._verification(n, None)["template"] == template
