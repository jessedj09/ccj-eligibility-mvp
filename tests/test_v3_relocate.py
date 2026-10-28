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


def test_leave_one_out_has_no_wrong_fields_and_fills_97_percent(loo):
    tot, crit, by_t = E.summarize(loo)
    n = sum(tot.values())
    assert tot[E.WRONG] == 0 and crit[E.WRONG] == 0
    assert (tot[E.CORRECT] + tot[E.ALT] + tot[E.OK_ABSENT]) / n >= 0.96
    assert tot[E.HELD] <= 7                    # 2026-10-28: 22 → 11(근거 다시 찾기) → 7(표현 사전·근거 없는 조건 보강)
    assert by_t["sh.newlywed"][E.HELD] <= 2 and by_t["sh.jeonse2"][E.HELD] == 0
    assert by_t["lh.happy_housing"][E.HELD] <= 3                   # 남은 것: 1순위 지역 2(⑤), 주거약자 1


def test_phrasebook_finds_same_condition_written_differently():
    # N5 대학생·청년 무주택(본인 기준): 템플릿 "… 주택 소유여부는 신청자 본인에 한하여 검증합니다"가 N5에는 없고,
    # N5는 "'무주택자'란 … 세대 내 다른 구성원이 주택을 소유해도 신청 가능함"으로 적었다 — 같은 판정식의 N9 표현으로 찾는다
    cond = next(c for c in sv.notice_doc("N5")["layers"]["청년"]["conditions"] if c["id"] == "N5-R5")
    book = X.phrasebook("R5", X._check_key(cond), exclude="N5")
    assert any("세대내다른구성원이주택을소유해도" in sv.normalize(t) for t in book)
    assert book == [t for t in X.phrasebook("R5", X._check_key(cond)) if t in book]       # exclude는 빼기만 한다
    found = [X._find_quote(sv.pdf_pages("N5"), t) for t in book]
    assert any(f and "무주택자" in sv.normalize(f) for f in found)


def test_draft_evaluation_does_not_see_registered_overrides():
    """초안·평가(templates.build)에는 등록 정답 문구(gen_c1 OVERRIDES)가 공고 번호로 새어 들어가지 않는다."""
    sheet = dict(T.gold_sheet("N5"), params=dict(T.gold_sheet("N5")["params"], overrides={}))
    doc, missing = T.build(sheet, sv.pdf_path("N5"), sv.pdf_pages("N5"))
    assert any("N5-R5" in m for m in missing)                       # 정답 문구 없이는 템플릿 문구를 못 찾는다


def test_condition_without_any_quote_is_held():
    """근거 문장이 하나도 없는 조건(생성 스크립트가 날짜 문구를 빼고 나면 생길 수 있음)은 찾지 못한 인용문으로 — 보류."""
    import copy
    real = T.build
    def emptied(sheet, pdf, pages=None):
        doc, missing = real(sheet, pdf, pages)
        doc = copy.deepcopy(doc)
        next(iter(doc["layers"].values()))["conditions"][0]["source"]["quote"] = []
        return doc, missing
    T.build = emptied
    try:
        ext = X.extract(sv.pdf_pages("N12"), E.siblings_for("N12"))
        g = X.gate(ext, sv.pdf_path("N12"), sv.pdf_pages("N12"), "N12")
    finally:
        T.build = real
    assert any(X.NO_EVIDENCE in m for m in g["missing"])
