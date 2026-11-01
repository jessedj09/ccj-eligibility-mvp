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


def test_priority_section_is_not_a_new_condition():
    """'■우선공급대상자' 절의 지역요건은 일반공급 자격이 아니다 — 같은 문장이 일반공급 절에 있으면 그대로 미분류(새 조건 후보)."""
    units = [(8, "■우선공급대상자입주자모집공고일(2026.10.28.)현재일반공급대상자의요건을모두갖추고아래지역요건을갖춘자"),
             (8, "•지역요건행복주택이위치하는과천시에거주하는자"),
             (9, "■일반공급대상자입주자모집공고일(2026.10.28.)현재무주택자로서아래의요건을모두갖춘자"),
             (9, "•지역요건행복주택이위치하는과천시에거주하는자")]
    doc = {"layers": {"청년": {"conditions": []}}, "tables": {}}
    rows = [(page, label) for page, u, label in CL.classify(units, doc, CL.Known([])) if u.startswith("•지역요건")]
    assert rows == [(8, "무관:우선공급"), (9, CL.UNCLASSIFIED)]


def test_facility_notes_and_layer_intro_are_unrelated():
    doc = {"layers": {"청년": {"conditions": []}}, "tables": {}}
    units = [(40, "•본단지의지하주차장은각동과직접연결되는주동통합형이며전세대가위치에관계없이공동으로이용하여야하며"),
             (1, "•과천지식정보타운S12블록행복주택은입주자모집공고일(2026.10.28.)현재다음중하나에해당하는사람에게공급됩니다."),
             (5, "•서울특별시에2년이상거주하는자만신청할수있습니다")]
    labels = [label for _, _, label in CL.classify(units, doc, CL.Known([]))]
    assert labels[0].startswith("무관") and labels[1].startswith("무관") and labels[2] == CL.UNCLASSIFIED


def test_visit_only_procedure_is_not_a_condition_but_other_strong_words_are():
    doc = {"layers": {"청년": {"conditions": []}}, "tables": {}}
    units = [(13, "*해당일제외현장방문신청불가교통편지하철(의정부경전철)어룡역1번출구약50M"),
             (13, "*현장방문신청불가하며서울특별시거주자만신청가능")]
    labels = [label for _, _, label in CL.classify(units, doc, CL.Known([]))]
    assert labels[0].startswith("무관") and labels[1] == CL.UNCLASSIFIED


def test_child_words_and_house_lists_are_not_conditions():
    """G1(2026-11-01): '출생한자녀'의 '한자'는 조건 표현이 아니고, 공급 주택 목록 표 머리글은 안내 — 진짜 제한은 그대로 미분류."""
    doc = {"layers": {"청년": {"conditions": []}}, "tables": {}}
    units = [(10, "•2년이내출생한자녀또는태아가있는신생아가구"),
             (58, "58주택목록:시세의70%공급주택현황:128호월평균소득130%(맞벌이200%)이내인자"),
             (3, "•(신청접수)청약신청은1개주택단지만신청하며동및호는전산추첨"),
             (5, "•서울특별시에1년이상거주한자만신청할수있습니다")]
    rows = {page: label for page, _, label in CL.classify(units, doc, CL.Known([]))}
    assert 10 not in rows and rows[58].startswith("무관") and rows[3].startswith("무관") and rows[5] == CL.UNCLASSIFIED
