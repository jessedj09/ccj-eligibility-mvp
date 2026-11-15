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


def test_previous_year_table_is_recognised_not_matched():
    """장기전세 49차 — 이전 연도 기준표: 표 안은 일관되지만 등록 기준표와는 한 칸도 맞지 않는다(연도 전환 감지).
    G5(2026-11-03)부터 같은 연도 금액의 SH 영구임대 표(N54, income_standard_sh_permanent)가 등록돼 있어 그 표를 빼고 본다 —
    그 표와는 칸이 맞는다(같은 해 표를 쓴 공고). 2026-11-08 N60(SH 2025년 국민임대)·2026-11-10 N69·N70(SH 2025년 행복주택)의
    2024년도 표도 같은 해라 뺀다."""
    refs = P.load_references()
    others = P.families({k: v for k, v in refs.items() if k not in ("income_standard_sh_permanent", "income_standard_sh_public_2024",
                                                                     "income_standard_sh_happy_2024")})
    same_year = P.families({"income_standard_sh_permanent": refs["income_standard_sh_permanent"]})
    for g in grids("N25", 8):
        assert P.consistent(g) is True
        cmp = P.compare_reference(g.cells, others)
        assert cmp["same"] == [] and cmp["misplaced"] == []
        assert P.compare_reference(g.cells, same_year)["same"]


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


def _cells(t):
    return sorted((c.size, c.ratio, c.amount) for c in P.income_cells(t).cells)


def test_ratio_on_neighbor_row_and_share_percent_ignored():
    """여러 줄 머리 칸: 비율 글자가 금액 줄 아래 줄에 따로 있다(N70·N57 words). '우선공급(70%)'의 70%는 공급 물량 비율이라 쓰지 않는다."""
    t = P.Table(1, (0, 0, 1, 1), "words", [
        ["구분", "3인", "4인"],
        ["도시근로자가구당", "", ""],
        ["일반공급", "6,718,198", "7,622,056"],
        ["월평균소득액의100%", "", ""],
        ["(70%)도시근로자가구당", "", ""],
        ["우선공급(70%)", "8,733,657", "9,908,673"],
        ["월평균소득액의130%", "", ""],
        ["※ 참고: 120% 이하는 별도", "1", "2"],          # 금액 열에 글자가 있는 설명 줄은 보지 않는다
    ])
    assert _cells(t) == [(3, 100, 6718198), (3, 130, 8733657), (4, 100, 7622056), (4, 130, 9908673)]


def test_neighbor_ratio_ambiguous_is_not_used():
    """위아래 같은 거리에 다른 비율이 있으면 정하지 않는다."""
    t = P.Table(1, (0, 0, 1, 1), "words", [
        ["구분", "3인", "4인"],
        ["100%", "", ""],
        ["일반", "6,718,198", "7,622,056"],
        ["130%", "", ""],
    ])
    assert _cells(t) == []


def test_split_row_inherits_head_and_prefixed_size_header():
    """한 칸이 두 줄로 나뉜 줄(앞 줄이 비운 열에만 금액)은 앞 줄 머리를 잇는다(N57 lines p.10). 머리글 '소득기준3인가구'도 3인."""
    t = P.Table(1, (0, 0, 1, 1), "lines", [
        ["공급유형", "소득기준3인가구", "4인"],
        ["일반공급 월평균소득액의100%", "", "7,622,056"],
        ["", "6,718,198", ""],
        ["다자녀 월평균소득액의120%", "8,061,838", "9,146,467"],
    ])
    assert _cells(t) == [(3, 100, 6718198), (3, 120, 8061838), (4, 100, 7622056), (4, 120, 9146467)]


def test_single_size_column_table():
    """가구원수 열이 하나뿐인 표(선택형 임대 '2인' 표, N57 p.10) — 머리 비율로 읽고 가산 폭은 두 칸 이상으로 푼다."""
    t = P.Table(1, (0, 0, 1, 1), "lines", [
        ["공급유형", "가구원수별가구당월평균소득비율", "2인"],
        ["일반공급", "도시근로자가구원수별가구당월평균소득액의110%", "5,505,914"],
        ["노부모부양", "도시근로자가구원수별가구당월평균소득액의130%", "6,506,989"],
    ])
    assert _cells(t) == [(2, 110, 5505914), (2, 130, 6506989)]


@pytest.mark.parametrize("nid", ["N57", "N70"])
def test_multiline_head_tables_restored(nid, fams):
    """2026-11-14 보강 전 복원율 N57 70.8%·N70 38.9% — 지금은 인용 기준표 칸을 모두 찾고 틀린 칸 0."""
    import sys
    sys.path.insert(0, str(sv.PROJECT / "tools"))
    import eval_tables as E
    refs = P.load_references()
    r, _, wrong = E.evaluate_pdf(sv.pdf_path(nid), E.registered_truth(refs)[nid], refs, fams)
    assert (r["wrong"], r["cross_fail"], r["conflicts"], r["grid_bad"]) == (0, 0, 0, 0) and wrong == []
    assert r["ref_expected"] > 0 and r["ref_located"] == r["ref_expected"]


def test_seven_plus_rows_explained_by_their_own_table(fams):
    """7·8인 행은 표마다 기준액을 따로 둔다 — 통합공공임대 7인 30~130% 열(등록은 150~200%만)도 같은 표로 설명된다(N59)."""
    med = next(f for f in fams if f.name.startswith("기준중위소득"))
    assert P.predicts(med, 7, 100, 9515150) and P.predicts(med, 8, 30, 3142304)
    assert not P.predicts(med, 7, 100, 9515150 + 5000)
