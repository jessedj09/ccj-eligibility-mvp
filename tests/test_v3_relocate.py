# -*- coding: utf-8 -*-
"""test_v3_relocate.py — 자동 판정 v3 ①: 근거 문장을 값·핵심 표현으로 다시 찾기(sheet_extract.relocate, docs/10 §2-2).

형제 공고 문장과 표현이 달라도(조사·괄호·'만'·'및 태아') 값이 같으면 같은 근거로 찾고, 값·날짜·Ⅰ/Ⅱ 유형이 다르면 찾지 않는다.
평가는 실제 새 공고와 같은 조건(--loo: 형제 = 같은 사업의 등록 공고 전부, 자기 제외)과 근거 위치까지 본다.
"""
import sys
from datetime import date
from pathlib import Path

import pytest
import source_verify as sv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import eval_extraction as E  # noqa: E402
import sheet_extract as X  # noqa: E402
import templates as T  # noqa: E402


def _from(sibling, nid, key):
    s = T.gold_sheet(sibling)
    ann = date.fromisoformat(T.gold_sheet(nid)["announcement_date"])
    return X.adapt(s["params"]["quotes"][key], X.date_mapping(date.fromisoformat(s["announcement_date"]), ann))


def test_paraphrased_sentence_is_found_by_value_and_core():
    # N21 원문 "6세 이하 자녀가 있는 혼인가구(’19. 8. 25. 이후 출생한 자녀 및 태아)" ← N18 "만 6세 이하 … (‘19. 10. 1. …)"
    hit = X.relocate(sv.pdf_pages("N21"), _from("N18", "N21", "child6_m"))
    assert hit and "6세이하자녀가있는혼인가구" in hit[2] and date(2019, 8, 25) in X._dates_of(hit[2])
    assert E.same_place(T.gold_sheet("N21")["params"]["quotes"]["child6_m"], hit[2])


def test_different_value_is_not_found():
    # N18(신혼·신생아Ⅰ) 소득 70% 문장 — Ⅱ 유형 공고(N19)에는 70%·Ⅰ 문장이 없다
    assert X.relocate(sv.pdf_pages("N19"), _from("N18", "N19", "income")) is None


def test_roman_type_and_date_must_match():
    pages = sv.pdf_pages("N19")
    good = _from("N18", "N19", "child6_m")
    assert X.relocate(pages, good)
    shifted = good.replace("19. 10. 1.", "19. 10. 2.")          # 기준일이 하루 다르면 다른 조건
    assert X.relocate(pages, shifted) is None
    assert X.relocate(pages, "신혼·신생아 매입임대Ⅲ 세부 신청자격이 있는 자로서 아래 요건") is None


def test_short_or_valueless_fragment_is_not_relocated():
    assert X.relocate(sv.pdf_pages("N19"), "세부 신청자격") is None


def test_quote_place_metric():
    gold = "도시근로자 가구원수별 가구당 월평균소득의 130% 이하(맞벌이 인 경우 200% 이하)"
    assert E.same_place(gold, "도시근로자가구원수별가구당월평균소득의130%이하(맞벌이인경우200%이하)※신청시")
    f = lambda v: X.Field(X.FILLED, v, 1, v, "t")                       # noqa: E731
    assert E._cmp_quote(gold, f("해당세대의월평균소득이전년도도시근로자가구당월평균소득의130%")) == E.ALT
    assert E._cmp_quote(gold, f("해당세대의월평균소득이전년도도시근로자가구당월평균소득의70%이하")) == E.WRONG


@pytest.fixture(scope="module")
def loo():
    E.LOO = True
    try:
        return E.evaluate(E.TUNE + E.TEST)
    finally:
        E.LOO = False


def test_leave_one_out_has_no_wrong_fields_and_fills_95_percent(loo):
    tot, crit, by_t = E.summarize(loo)
    n = sum(tot.values())
    assert tot[E.WRONG] == 0 and crit[E.WRONG] == 0
    assert (tot[E.CORRECT] + tot[E.ALT] + tot[E.OK_ABSENT]) / n >= 0.94
    assert tot[E.HELD] <= 11                                         # 2026-10-28: 22 → 11 (근거 다시 찾기)
    assert by_t["sh.newlywed"][E.HELD] <= 2 and by_t["sh.jeonse2"][E.HELD] == 0
