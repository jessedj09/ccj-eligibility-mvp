# -*- coding: utf-8 -*-
"""test_reference_candidates.py — 새 기준표 후보(src/reference_candidates.py, docs/09 §21 T3 A단계).

실제 다음 해 공고가 없으므로 '모의 연도 전환'으로 시험한다: 등록 기준표(도시근로자)를 5% 낮춘 것을 '작년 표'로 두면, 등록 공고의
표에서 만든 후보가 지금의 등록 기준표와 칸 하나 틀림없이 같아야 한다.
"""
import copy

import pytest

pytest.importorskip("pdfplumber")

import pdf_tables as P  # noqa: E402
import reference_candidates as R  # noqa: E402
import source_verify as sv  # noqa: E402


@pytest.fixture(scope="module")
def refs():
    return P.load_references()


@pytest.fixture(scope="module")
def last_year(refs):
    """도시근로자 기준표를 5% 낮춘 '작년 표'(기준중위소득 표는 그대로)."""
    old = copy.deepcopy(refs)
    for ref in old.values():
        if "중위" not in ref["label"]:
            ref["year_basis"] = "2024"
            ref["table"] = {s: {r: round(v * 0.95) for r, v in row.items()} for s, row in ref["table"].items()}
    return old


def by_ref(cands):
    return {c.ref_id: c for c in cands}


def test_same_year_notice_has_no_candidate():
    assert R.candidates(sv.pdf_path("N3")) == []


@pytest.mark.parametrize("nid,rid", [("N30", "income_standard_public"), ("N31", "income_standard_public"),
                                     ("N33", "income_standard_permanent")])
def test_candidate_reproduces_registered_table(nid, rid, refs, last_year):
    c = by_ref(R.candidates(sv.pdf_path(nid), refs=last_year))[rid]
    assert c.ok, c.problems + [str(m) for m in c.missing]
    assert c.table == {s: {r: v for r, v in row.items()} for s, row in refs[rid]["table"].items()}
    assert all(abs(v - (1 / 0.95 - 1)) < 1e-4 for v in c.change.values())
    assert c.year == "2025"                       # 원문 '2025년도 도시근로자…'


def test_missing_adder_keeps_candidate_open(refs, last_year):
    """행복주택 기준표는 금액은 다 맞아도 7인 이상 1인당 가산액이 표 쪽에 없으면 운영자 확인으로 남긴다."""
    c = by_ref(R.candidates(sv.pdf_path("N3"), refs=last_year))["income_standard"]
    found = {(s, r): v for s, row in c.table.items() for r, v in row.items()}
    real = {(s, r): v for s, row in refs["income_standard"]["table"].items() for r, v in row.items()}
    assert found == {k: real[k] for k in found} and not c.missing
    assert not c.ok and any("1인당 가산" in p for p in c.problems)


def test_partial_tables_combine_across_notices(refs, last_year):
    """매입임대 기준표 — Ⅰ형 공고(70·90%)와 Ⅱ형 공고(130·200%)의 후보를 합치면 완성된다."""
    one = by_ref(R.candidates(sv.pdf_path("N13"), refs=last_year))["income_standard_rental"]
    two = by_ref(R.candidates(sv.pdf_path("N15"), refs=last_year))["income_standard_rental"]
    assert one.missing and two.missing
    both = R.combine([one, two], refs["income_standard_rental"])
    assert both.ok and both.table == refs["income_standard_rental"]["table"]
    assert R.agree([one, two]) == []


def test_previous_year_notice_is_flagged_not_completed(refs):
    """장기전세 49차(이전 연도 표) — 후보는 만들되 등록 표 칸을 다 채우지 못해 완성되지 않는다(자동 등록 없음).
    같은 연도 금액의 SH 영구임대 표(N54, G5)·SH 국민임대 2024년도 표(N60, 2026-11-08)는 빼고 본다 — 그 표가 있으면 N25 표는
    '이미 등록된 연도'다. SH 행복주택 2024년도 표(N69·N70, 2026-11-10)도 같은 해라 뺀다."""
    others = {k: v for k, v in refs.items() if k not in ("income_standard_sh_permanent", "income_standard_sh_public_2024",
                                                         "income_standard_sh_happy_2024")}
    cands = R.candidates(sv.pdf_path("N25"), refs=others)
    assert cands and not any(c.ok for c in cands)
    assert all(-0.07 < v < 0 for c in cands for v in c.change.values())


def test_changed_cell_breaks_candidate(refs, last_year, monkeypatch):
    """원문 칸 하나를 잘못 읽은 것처럼 바꾸면 그 가구원수 기준액이 맞지 않아 문제로 잡힌다."""
    real = R.new_year_cells

    def tamper(pdf, pages, fams):
        cells = real(pdf, pages, fams)
        cells[0].amount += 7000
        return cells
    monkeypatch.setattr(R, "new_year_cells", tamper)
    c = by_ref(R.candidates(sv.pdf_path("N30"), refs=last_year))["income_standard_public"]
    assert not c.ok and any("기준액으로 설명되지 않음" in p for p in c.problems)


def test_candidate_json_is_marked_unapproved(refs, last_year):
    c = by_ref(R.candidates(sv.pdf_path("N30"), refs=last_year))["income_standard_public"]
    doc = R.to_reference(c, last_year["income_standard_public"], "N30")
    assert doc["status"] == "CANDIDATE" and doc["candidate_of"] == "income_standard_public"
    assert doc["id"] == "income_standard_public_2025" and doc["cited_pages"] == {}
    assert doc["table"] == refs["income_standard_public"]["table"]
