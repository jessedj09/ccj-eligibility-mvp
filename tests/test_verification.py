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


def test_answers_come_from_the_answers_file_not_the_cases_file(monkeypatch, tmp_path):
    """사람 답은 답 파일에만(점검 세션 four_class.py와 같은 형식) — 사례 파일의 user_verdict는 비어 있어야 워크시트 시험이 통과한다."""
    f = tmp_path / "answers.json"
    f.write_text(json.dumps({"answers": {"25": {"verdict": "ELIGIBLE", "page": "p.4", "note": ""}}}), encoding="utf-8")
    monkeypatch.setattr(V, "ANSWERS_FILE", f)
    got = V.with_answers([{"id": 25, "notice": "N30", "user_verdict": ""}, {"id": 26, "notice": "N30", "user_verdict": ""}])
    assert [c["user_verdict"] for c in got] == ["ELIGIBLE", ""] and got[0]["user_page"] == "p.4"
    monkeypatch.setattr(V, "ANSWERS_FILE", tmp_path / "없음.json")
    assert V.answers() == {}


def test_recorded_verified_programs_still_agree_with_the_engine():
    """'독립 검증 완료'가 저절로 유지되지 않게: 기록 파일의 사업마다 답을 합친 사례를 엔진으로 다시 대조해 모두 같아야 한다
    (기록 뒤에 규칙을 바꿔 불일치가 생기면 CI가 깨진다 — 점검 세션 권고, 2026-11-14)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import worksheet_check as W
    for template in V._recorded():
        cases = V._json_cases_by_template().get(template, [])
        assert cases and all(c["user_verdict"] for c in cases), f"{template}: 답이 빈 사례가 있는데 완료로 기록됨"
        bad = [c["id"] for c in cases if not W.same(c["user_verdict"], W.engine_verdict(c))]
        assert not bad, f"{template}: 엔진과 다른 사례 {bad} — 검증 기록을 지우거나 규칙을 확인"
