# -*- coding: utf-8 -*-
"""test_d4_api_upload.py — v3 ④-2: 판정 API의 공고 업로드 판정(api/main.py /upload, /evaluate sha256).

API는 화면과 같은 판정이어야 한다: 등록 공고는 검증된 규칙, 미등록 공고는 자동 분석(공개 스위치가 켜졌을 때만) +
사용자 단위 확정(grading.judge). 결과에는 화면 3상태·원문 확인할 곳·공통 문구가 함께 온다.
"""
import dataclasses
import hashlib

import golden_cases as gc
import grading
import notice_identify as ni
import pytest
import source_verify as sv
from display_status import COMMON_NOTE
from profile_io import HOUSEHOLD_FIELDS, _dump
from rule_data import load_notice
from rule_engine import evaluate

pytest.importorskip("fastapi")
pytest.importorskip("multipart")
from fastapi.testclient import TestClient  # noqa: E402

import api.main as api  # noqa: E402

client = TestClient(api.app)


@pytest.fixture(scope="module")
def n12():
    return sv.pdf_path("N12").read_bytes()


def _unregistered(data):
    """등록 공고 원문을 처음 보는 공고처럼(화면 점검 tools/ui_fixture_draft.py와 같은 방법)."""
    got = ni.identify_pages(hashlib.sha256(data).hexdigest(), sv.extract_pages_bytes(data, label="<시험>", cache=False))
    return dataclasses.replace(got, status=ni.UNREGISTERED, notice_id=None, ambiguous=[], reason="(시험) 미등록 공고")


def _body(p):
    return {k: _dump(getattr(p, k)) for k in HOUSEHOLD_FIELDS if k != "profile_id"}


def _post(data, name="notice.pdf"):
    return client.post("/upload", files={"file": (name, data, "application/pdf")})


@pytest.fixture
def unregistered(monkeypatch):
    monkeypatch.setattr(api, "identify_pdf", _unregistered)
    api._drafts.clear()
    yield
    api._drafts.clear()


def test_registered_upload_points_to_verified_rules(n12):
    r = _post(n12)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["identification"]["status"] == ni.REGISTERED
    assert j["judge"] == {"by": "registered", "notice_id": "N12", "title": load_notice("N12").title,
                          "layers": list(load_notice("N12").layers)}


def test_rejects_non_pdf_and_too_large(monkeypatch):
    assert _post(b"hello", "a.txt").status_code == 422
    monkeypatch.setattr(api, "MAX_UPLOAD", 10)
    assert _post(b"%PDF-1.7 " + b"x" * 20).status_code == 413


def test_unregistered_is_not_judged_until_public(n12, unregistered, monkeypatch):
    monkeypatch.delenv(api.PUBLIC_ENV, raising=False)
    j = _post(n12).json()
    assert j["judge"]["by"] == "none" and j["identification"]["status"] == ni.UNREGISTERED
    p = next(p for _, _, p in gc.cases(only=[("N12", "청년")]))
    r = client.post("/evaluate", json={"sha256": j["sha256"], "layer": "청년", "profile": _body(p)})
    assert r.status_code == 403


def test_unregistered_upload_then_evaluate_equals_registered(n12, unregistered, monkeypatch):
    monkeypatch.setenv(api.PUBLIC_ENV, "1")
    j = _post(n12).json()
    assert j["judge"]["by"] == "analysis" and set(j["judge"]["grades"].values()) == {grading.AUTO}
    assert j["judge"]["layers"] == list(load_notice("N12").layers)
    reg = load_notice("N12")
    seen = set()
    for _, _, p in gc.cases(only=[("N12", "청년")]):
        want = evaluate(p, reg, "청년").verdict
        if want in seen:
            continue
        seen.add(want)
        r = client.post("/evaluate", json={"sha256": j["sha256"], "layer": "청년", "profile": _body(p)})
        assert r.status_code == 200, r.text
        got = r.json()
        assert got["verdict"] == want and got["checks"] == [] and got["common_note"] == COMMON_NOTE
    assert len(seen) >= 2


def test_evaluate_reads_analysis_from_store_after_restart(n12, unregistered, monkeypatch):
    """프로세스가 다시 떠서 메모리의 분석이 없어도 공유 저장소에 있으면 판정한다."""
    import analysis
    import draft

    monkeypatch.setenv(api.PUBLIC_ENV, "1")
    sha = _post(n12).json()["sha256"]
    snap = draft.to_snapshot(api._drafts[sha], sha)
    api._drafts.clear()

    class Saved:
        def latest_analysis(self, s, version):
            return snap if (s, version) == (sha, analysis.analysis_version()) else None

        def count(self, *a, **k):
            return True

    monkeypatch.setattr(api, "get_store", lambda: Saved())
    p = next(p for _, _, p in gc.cases(only=[("N12", "청년")]))
    r = client.post("/evaluate", json={"sha256": sha, "layer": "청년", "profile": _body(p)})
    assert r.status_code == 200 and r.json()["verdict"] == evaluate(p, load_notice("N12"), "청년").verdict
    assert client.post("/evaluate", json={"sha256": "0" * 64, "layer": "청년", "profile": _body(p)}).status_code == 404
    assert client.post("/evaluate", json={"sha256": sha, "layer": "없음", "profile": _body(p)}).status_code == 404


def test_evaluate_needs_exactly_one_target_and_shows_display():
    body = {"age": 25, "marital_status": "미혼", "home_ownership": "무주택", "household_size": 1}
    assert client.post("/evaluate", json={"layer": "청년", "profile": body}).status_code == 422
    assert client.post("/evaluate", json={"notice_id": "N12", "sha256": "x", "layer": "청년",
                                          "profile": body}).status_code == 422
    j = client.post("/evaluate", json={"notice_id": "N12", "layer": "청년", "profile": body}).json()
    assert j["display"]["group"] in ("지원 가능", "보류", "지원 불가") and j["checks"] == [] and j["common_note"] == COMMON_NOTE


def test_held_condition_check_reaches_the_api(n12, unregistered, monkeypatch):
    """확실하지 않은 조건이 그 사용자의 결론을 바꿀 수 있으면 보류 + 확인할 곳(쪽·문장)이 응답에 온다."""
    monkeypatch.setenv(api.PUBLIC_ENV, "1")
    sha = _post(n12).json()["sha256"]
    d = api._drafts[sha]
    home = next(c for c in d.doc["layers"]["청년"]["conditions"] if c["id"].endswith("-home"))
    api._drafts[sha] = dataclasses.replace(d, held_conditions=dict(d.held_conditions, **{"청년": {home["id"]}}))
    reg = load_notice("N12")
    p = next(p for _, _, p in gc.cases(only=[("N12", "청년")]) if evaluate(p, reg, "청년").verdict == "ELIGIBLE")
    j = client.post("/evaluate", json={"sha256": sha, "layer": "청년", "profile": _body(p)}).json()
    assert j["verdict"] == "MANUAL_REVIEW" and j["display"]["title"].endswith("원문 확인 1건")
    assert j["checks"][0]["kind"] == "held" and j["checks"][0]["page"] == home["source"]["page"]
