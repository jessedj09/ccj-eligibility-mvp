# -*- coding: utf-8 -*-
"""test_t32_extract.py — 결정론 추출기·검증 관문(P1 T3.2, tools/sheet_extract.py)과 평가 도구(tools/eval_extraction.py).

안전 기준: 다듬기용 공고에서 틀린 빈칸 0, 확정 판정 틀림 0(보류는 틀림이 아니다). 추출 규칙은 일반 패턴만 쓴다.
"""
import re
import sys
from datetime import date
from pathlib import Path

import pytest
import source_verify as sv
from rule_data import load_notice, notice_ids

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import eval_extraction as E  # noqa: E402
import sheet_extract as X  # noqa: E402

SRC = (Path(__file__).resolve().parent.parent / "tools" / "sheet_extract.py").read_text(encoding="utf-8")


def test_extractor_has_no_notice_specific_strings():
    """공고 번호·단지 이름 같은 특정 공고 전용 문자열이 없어야 한다(템플릿 원본 이름 N1·N3만 허용)."""
    ids = set(re.findall(r'"(N\d+)"', SRC))
    assert ids <= {"N1", "N3"}, ids
    sites = {load_notice(n).title.split()[0] for n in notice_ids()} - {"SH", "서울지역본부"}
    assert not [s for s in sites if s in SRC], sites


def test_adapt_keeps_the_original_date_format():
    m = X.date_mapping(date(2026, 9, 30), date(2026, 8, 14))
    assert X.adapt("혼인 7년 이내(혼인신고일이 ‘19. 10. 1. ~ ’26. 9. 30.)인 사람", m) == \
        "혼인 7년 이내(혼인신고일이 ‘19. 8. 15. ~ ’26. 8. 14.)인 사람"
    assert X.adapt("(’24. 08. 15. 이후 출생한 자녀 및 태아)", X.date_mapping(date(2026, 8, 14), date(2026, 8, 24))) == \
        "(’24. 08. 25. 이후 출생한 자녀 및 태아)"


def test_loose_match_allows_only_numbers_and_roman_numerals_to_differ():
    pages = ["앞문장무주택세대구성원으로서아래의신혼·신생아I매입임대주택세부신청자격중뒷문장"]
    hit = X.loose_find(pages, "무주택세대구성원으로서 아래의 신혼·신생아Ⅱ 매입임대주택 세부 신청자격 중")
    assert hit == (1, "무주택세대구성원으로서아래의신혼·신생아I매입임대주택세부신청자격중")
    assert X.loose_find(pages, "무주택세대구성원으로서 아래의 청년 매입임대주택 세부 신청자격 중") is None
    assert X.loose_pattern("70% 이하") is None          # 너무 짧으면 쓰지 않는다


def test_dates_are_filled_only_when_written_in_the_source():
    pages = sv.pdf_pages("N13")
    ann = date(2026, 6, 25)
    assert X.by_convention(pages, ann, 7, "혼인신고", False).value == "2019-06-25"
    blank = [re.sub(r"2019\.0?6\.25|[‘’'`]19\.0?6\.25", "", p) for p in pages]
    # 혼인 기준일 글자가 없으면 보류 — 근처의 6세 자녀 기준일(2019.6.26)을 혼인 기준일로 잡지 않는다
    assert X.by_convention(blank, ann, 7, "혼인신고", False).status == X.HELD


def test_unknown_program_is_blocked_not_guessed():
    ext = X.extract(["아무 공고도 아닌 문서입니다. 입주자모집공고일:2026.12.01"])
    g = X.gate(ext, sv.pdf_path("N2"), ["x"])
    assert ext["template"] is None and g["blocked"] and g["doc"] is None


def test_critical_classification():
    assert X.is_critical("sh.newlywed", "dates.marriage")
    assert not X.is_critical("sh.newlywed", "quotes.home")
    assert X.is_critical("sh.jeonse", "quotes.assets") and X.is_critical("sh.jeonse", "income")
    assert X.is_critical("lh.happy_housing", "region") and not X.is_critical("lh.happy_housing", "weak")


@pytest.fixture(scope="module")
def tuned():
    return E.evaluate(E.TUNE)


def test_tuning_set_has_no_wrong_fields_and_fills_most(tuned):
    tot, crit, _ = E.summarize(tuned)
    assert tot[E.WRONG] == 0
    filled = tot[E.CORRECT] + tot[E.OK_ABSENT]
    assert filled / sum(tot.values()) >= 0.75


def test_tuning_set_has_no_wrong_firm_judgments(tuned):
    j = E.judge_all(tuned, limit=150)
    assert j[E.J_WRONG] == 0 and j[E.SAME] > 0


def test_split_is_disjoint_and_covers_all_sheets():
    assert not set(E.TEST) & set(E.TUNE)
    assert sorted(E.TEST + E.TUNE, key=lambda n: int(n[1:])) == [n for n in notice_ids() if n not in ("N1", "N2", "N3")]


def test_test_set_stays_safe():
    """시험용 공고(다듬기에 쓰지 않음)도 틀린 빈칸 0·확정 판정 틀림 0 — 회귀 방지용(이 결과로 추출 규칙을 다듬지 않는다)."""
    per = E.evaluate(E.TEST)
    tot, _, _ = E.summarize(per)
    assert tot[E.WRONG] == 0
    assert E.judge_all(per, limit=100)[E.J_WRONG] == 0
