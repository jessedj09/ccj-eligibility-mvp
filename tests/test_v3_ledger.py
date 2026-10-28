# -*- coding: utf-8 -*-
"""test_v3_ledger.py — 자동 판정 v3 ②: 조항 장부(tools/clause_ledger.py, docs/10 §2-4).

규칙이 모르는 새 조건 문장을 공고에 끼워 넣으면 '미분류'로 잡고, 규칙 근거·형제 공고 문장·공통 제한(외국인 등)은 미분류로 남기지 않는다.
"""
import sys
from pathlib import Path

import pytest
import source_verify as sv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import clause_ledger as CL  # noqa: E402

NEW_CONDITIONS = [
    "• 신청자 본인이 입주자모집공고일 현재 서울특별시에 2년 이상 거주한 자에 한하여 신청 가능",
    "• 주택청약종합저축 가입기간이 6개월 이상인 자",
    "• 만 25세 미만인 자는 신청할 수 없습니다",
    "• 공고일 현재 사업자등록을 한 자는 신청 불가합니다",
]


def _with(nid, extra_lines, page=3):
    units = list(CL.registered_units(nid)) + CL._units_from_raw([""] * (page - 1) + ["\n".join(extra_lines)])
    known = CL.Known([u for s in CL.siblings_of(nid) for u in CL.registered_units(s)])
    return CL.classify(units, sv.notice_doc(nid), known)


@pytest.mark.parametrize("nid", ["N12", "N24", "N20"])
def test_injected_new_conditions_are_unclassified(nid):
    rows = _with(nid, NEW_CONDITIONS)
    flagged = {u for _, u, lab in rows if lab == CL.UNCLASSIFIED}
    for line in NEW_CONDITIONS:
        assert sv.normalize(line) in flagged, line


def test_common_restrictions_evidence_and_sibling_sentences_are_not_flagged():
    sibling_sentence = next(u for _, u in CL.registered_units("N11") if CL.CONDLIKE.search(u))
    rows = _with("N12", ["• 외국인은 신청할 수 없습니다",
                         "• 공고일 현재(2026.09.17.) 무주택자인 미혼 청년으로서 소득 및 자산 기준을 충족하는,",
                         sibling_sentence])
    label = {u: lab for _, u, lab in rows}
    assert label[sv.normalize("• 외국인은 신청할 수 없습니다")] == "무관:공통 제한"
    assert label[sv.normalize("• 공고일 현재(2026.09.17.) 무주택자인 미혼 청년으로서 소득 및 자산 기준을 충족하는,")] == "근거"
    assert label[sibling_sentence] in ("형제 공고에도", "근거")


def test_strong_restriction_is_not_hidden_by_unrelated_keywords():
    # '서류'가 들어 있어도 '~에 한하여 신청' 같은 강한 제한이면 미분류로 남는다
    rows = _with("N12", ["• 서울특별시에 1년 이상 거주한 자에 한하여 신청 가능하며 관련 서류를 제출하여야 합니다"])
    assert any(lab == CL.UNCLASSIFIED for _, u, lab in rows if "1년이상거주" in u)


@pytest.mark.parametrize("nid,most", [("N12", 1), ("N11", 0), ("N24", 0), ("N23", 0)])
def test_registered_notices_have_few_unclassified(nid, most):
    """등록 공고(사람이 규칙을 만든 공고)의 미분류는 적어야 한다 — 늘어나면 분류 규칙이 망가진 것(2026-10-28 기준값)."""
    assert CL.summary(CL.ledger_for_registered(nid))[CL.UNCLASSIFIED] <= most


def test_units_cache_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(CL, "CACHE", tmp_path)
    first = CL.units_of_pdf(sv.pdf_path("N11"))
    assert list(tmp_path.glob("*.json")) and CL.units_of_pdf(sv.pdf_path("N11")) == first
