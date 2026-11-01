# -*- coding: utf-8 -*-
"""test_pdf_tables.py — 표 칸 위치 읽기(src/pdf_tables.py, docs/09 §19 T1·T2).

평가 단계라 판정 경로에는 연결하지 않았다. pdfplumber가 없으면(배포 의존성에 아직 넣지 않음) 건너뛴다.
"""
import dataclasses

import pytest

pytest.importorskip("pdfplumber")

import pdf_tables as P  # noqa: E402
import source_verify as sv  # noqa: E402


@pytest.fixture(scope="module")
def fams():
    return P.families(P.load_references())


def grids(nid, page):
    return [g for g in (P.income_cells(t) for t in P.read_tables(sv.pdf_path(nid), [page])) if g.cells]


def test_fully_ruled_table_keeps_blank_cells(fams):
    """장기전세 50차 p.8 — 빈 칸(1인 80%·2인 90% 등)이 있어도 칸 위치가 맞고, 두 방법이 같다."""
    lines, words = grids("N26", 8)
    assert len(lines.cells) == len(words.cells) == 55
    assert P.agree(lines, words) == (55, 0)
    cell = {(c.size, c.ratio): c.amount for c in lines.cells}
    assert cell[(2, 80)] == 4_693_016 and (1, 80) not in cell
    assert P.consistent(lines) is True
    assert len(P.compare_reference(lines.cells, fams)["same"]) == 55


def test_unmarked_one_two_person_adder_is_solved(fams):
    """LH 신혼·신생아Ⅰ p.4 — 머리글은 70%·90%인데 1인 칸은 +20%p, 2인 칸은 +10%p 금액(표시 없음)."""
    g = grids("N14", 4)[0]
    cell = {(c.size, c.ratio): c.amount for c in g.cells}
    assert cell[(1, 90)] == 3_432_027 and cell[(1, 110)] == 4_194_699
    assert cell[(2, 80)] == 4_693_016 and cell[(3, 70)] == 5_717_900
    assert P.compare_reference(g.cells, fams)["misplaced"] == []


def test_table_without_row_lines_read_by_word_positions():
    """SH 신혼Ⅰ p.16 — 행 머리(50%·70%·90%)가 선 밖이라 lines는 못 읽고 words가 읽는다. '(+10p%)' 표기도."""
    found = grids("N18", 16)
    assert [g.method for g in found] == ["words"]
    cell = {(c.size, c.ratio): c.amount for c in found[0].cells}
    assert cell[(2, 60)] == 3_519_762 and cell[(3, 50)] == 4_084_215


def test_range_headers_of_median_income_table(fams):
    """통합공공임대 p.14 — 머리글 '~30%'·'~150%'(기준중위소득 구간)."""
    g = grids("N35", 14)[0]
    cell = {(c.size, c.ratio): c.amount for c in g.cells}
    assert cell[(2, 150)] == 6_298_938
    assert P.compare_reference(g.cells, fams)["misplaced"] == []


def test_previous_year_table_is_recognised_not_matched(fams):
    """장기전세 49차 — 이전 연도 기준표: 표 안은 일관되지만 등록 기준표와는 한 칸도 맞지 않는다(연도 전환 감지)."""
    for g in grids("N25", 8):
        assert P.consistent(g) is True
        cmp = P.compare_reference(g.cells, fams)
        assert cmp["same"] == [] and cmp["misplaced"] == []


def test_swapped_cells_are_flagged_as_misplaced(fams):
    g = grids("N26", 8)[0]
    a, b = g.cells[0], g.cells[1]
    swapped = [dataclasses.replace(a, amount=b.amount), dataclasses.replace(b, amount=a.amount)] + g.cells[2:]
    assert len(P.compare_reference(swapped, fams)["misplaced"]) == 2


def test_digit_misread_breaks_consistency_and_cross_check():
    g = grids("N26", 8)[0]
    bad = P.Grid(g.page, g.method, [dataclasses.replace(g.cells[0], amount=g.cells[0].amount + 9000)] + g.cells[1:])
    assert P.consistent(bad) is False
    assert len(P.cross_check(bad, sv.pdf_pages("N26")[7])) == 1
    assert P.cross_check(g, sv.pdf_pages("N26")[7]) == []


def test_merge_drops_conflicting_cells():
    g = grids("N26", 8)[0]
    other = P.Grid(g.page, "words", [dataclasses.replace(g.cells[0], amount=g.cells[0].amount + 1)])
    cells, conflicts = P.merge([g, other])
    assert conflicts == 1 and len(cells) == len(g.cells) - 1


@pytest.mark.parametrize("nid", ["N3", "N13", "N26", "N30", "N35", "N46", "N49"])
def test_registered_notices_have_no_wrong_cells(nid, fams):
    """평가 도구와 같은 계산 — 틀린 칸·교차 실패·방법 충돌 0, 인용 기준표 칸을 표 위치로 찾는다."""
    import sys
    sys.path.insert(0, str(sv.PROJECT / "tools"))
    import eval_tables as E
    refs = P.load_references()
    r, _, wrong = E.evaluate_pdf(sv.pdf_path(nid), E.registered_truth(refs)[nid], refs, fams)
    assert (r["wrong"], r["cross_fail"], r["conflicts"]) == (0, 0, 0) and wrong == []
    assert r["ref_located"] == r["ref_expected"]          # N26(장기전세)은 기준표를 인용하지 않고 결정표에 금액을 적는다
    assert r["ref_expected"] > 0 or nid == "N26"
