# -*- coding: utf-8 -*-
"""test_e1_intake.py — 새 공고 등록용 내부 도구(tools/notice_intake.py).

등록된 공고 26건을 "새 공고"처럼 넣어 보고, 도구가 내놓은 후보에 실제로 등록한 값(공고일·접수기간·사업 유형)이 들어 있는지
확인한다 — 다음에 들어올 진짜 새 공고에서도 후보를 놓치지 않는지의 근거. 등록 누락 점검(--audit)은 지금 0건이어야 한다.
"""
import json
import re
import sys
from pathlib import Path

import pytest
import source_verify as sv
from rule_data import load_notice, notice_ids

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import notice_intake as ni  # noqa: E402

SCHEDULES = json.loads((sv.RULES / "schedules.json").read_text(encoding="utf-8"))["notices"]


@pytest.fixture(scope="module")
def reports():
    return {nid: ni.report(sv.pdf_path(nid), sv.pdf_pages(nid)) for nid in notice_ids()}


def test_every_registered_application_window_is_among_the_candidates(reports):
    for nid, r in reports.items():
        cands = {(w["start"], w["end"]) for w in r["windows"]}
        for w in SCHEDULES[nid]["windows"]:
            assert (w["start"], w["end"]) in cands, (nid, w["label"])
        # 후보의 인용문은 그 쪽에 있고 날짜와 맞아야 한다(그대로 schedules.json에 옮길 수 있게)
        for w in r["windows"]:
            assert sv.page_has(nid, w["page"], w["quote"]) and w["quote_check"], (nid, w)


def test_announcement_program_and_registration_are_detected(reports):
    for nid, r in reports.items():
        meta = load_notice(nid).meta
        assert r["announcement"][0]["date"] == load_notice(nid).announcement_date.isoformat(), nid
        assert r["registered_as"] == nid
        assert r["issuer"] == meta["issuer"] and r["program"].replace("SH ", "") in meta["program"], (nid, r["program"])
        assert nid in r["similar"] and r["generators"], nid


def test_cutoff_literals_used_in_rules_are_found(reports):
    """규칙 데이터가 원문 날짜 리터럴로 쓰는 기준일(출생·혼인 기준일 등, 26건에 30개)은 모두 후보에 있어야 한다."""
    for nid in notice_ids():
        text = json.dumps(sv.notice_doc(nid), ensure_ascii=False)
        literals = set(re.findall(r'"date": "(\d{4}-\d\d-\d\d)"', text))
        found = {c["date"] for c in reports[nid]["cutoffs"]}
        assert literals <= found | {load_notice(nid).announcement_date.isoformat()}, (nid, literals - found)


def test_markdown_report_has_sections_and_a_valid_schedule_snippet(reports):
    md = ni.to_markdown(reports["N4"])
    for head in ("## 1. 기본", "## 2. 공고일 후보", "## 3. 청약 접수기간 후보", "## 7. 등록 체크리스트"):
        assert head in md
    assert "이미 등록된 공고: N4" in md
    snippet = json.loads(re.search(r"```json\n(.*?)\n```", ni.to_markdown(reports["N25"]), re.S).group(1))
    assert snippet["N25"]["windows"][0]["start"] == "2026-01-08T10:00"


def test_audit_is_clean_now():
    assert ni.audit() == []


def test_audit_catches_missing_registration(monkeypatch):
    import golden_cases as gc
    monkeypatch.setattr(gc, "GROUPS", [g for g in gc.GROUPS if g != ("N2", "대학생(주거약자용)")])
    monkeypatch.setattr(gc, "DATES", {k: v for k, v in gc.DATES.items() if k != "N9"})
    problems = ni.audit()
    assert any("N2" in p and "대학생(주거약자용)" in p for p in problems)
    assert any("N9" in p and "DATES" in p for p in problems)
