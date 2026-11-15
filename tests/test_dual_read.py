# -*- coding: utf-8 -*-
"""test_dual_read.py — 이중 읽기(R1, tools/dual_read.py). LLM 없이 — 가짜 슬롯으로 읽기 검증·신호 규칙을 확인한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import dual_read as D  # noqa: E402
import source_verify as sv  # noqa: E402


def test_facts_of_registered_notice():
    """N30 국민임대 일반: 자산 3억4,500만(출산자녀별 3단)·자동차·소득 비율·성년 나이가 조건 단위로 나온다."""
    f = D.facts(sv.notice_doc("N30"))
    assert f[("일반", "G-assets")]["kind"] == "assets"
    assert 345_000_000 in f[("일반", "G-assets")]["values"]
    assert 45_420_000 in f[("일반", "G-car")]["values"]
    assert ("%", 70) in f[("일반", "G-income")]["values"]
    assert 19 in f[("일반", "G-adult")]["values"]


def test_money_forms_and_parse():
    for s, n in [("3억4,500만원", 345_000_000), ("(345)백만원 이하", 345_000_000), ("(4,542)만원", 45_420_000),
                 ("45,420,000원", 45_420_000), ("2억", 200_000_000)]:
        assert D.parse_value("assets", s) == n, s
    assert D.in_text("assets", 345_000_000, "총자산가액합산기준(345)백만원이하")
    assert D.in_text("car", 45_420_000, "자동차가액4,542만원이하")
    assert D.parse_value("income", "월평균소득 70% 이하") == ("%", 70)
    assert D.parse_value("income", "1인당 579,278원") is None            # 가산액은 상한이 아님
    assert D.parse_value("date", "2019. 7. 29. 이후") == "2019-07-29"
    assert D.region_name("의정부") == "의정부시" and D.region_name("경기도") == "묶음:경기도"


def test_value_must_follow_its_keyword():
    """표 한 줄에 총자산·자동차가 함께 있으면 자동차 값으로 총자산 금액을 인정하지 않는다."""
    q = "총자산2억5,100만원이하,자동차4,542만원이하"
    assert D.near("car", 45_420_000, q, D.QUESTIONS["car"][2])
    assert not D.near("car", 251_000_000, q, D.QUESTIONS["car"][2])
    assert D.near("assets", 251_000_000, q, D.QUESTIONS["assets"][2])


def test_signal_rules():
    text = "총자산3억4,500만원3억7,900만원4억1,300만원"
    S = {345_000_000, 379_000_000, 413_000_000}
    assert D.signal([345_000_000, 379_000_000, 413_000_000], S, S, "assets", text) == D.AGREE
    assert D.signal([345_000_000], S, S, "assets", text) == D.PARTIAL               # 일부만 읽음 = 중립
    assert D.signal([345_000_000, 300_000_000], S, S, "assets", text) == D.DISAGREE
    assert D.signal([], S, S, "assets", text) == D.NONE


def test_swapped_value_never_agrees():
    """일부러 바꾼 값(원문에 없는 값)이 결정론 쪽에 있으면, LLM이 무엇을 읽었든 '일치'가 될 수 없다 — 잘못된 일치 0의 근거."""
    text = "총자산3억4,500만원3억7,900만원4억1,300만원"
    true = {345_000_000, 379_000_000, 413_000_000}
    bad = (true - {413_000_000}) | {400_000_000}
    for read in ([345_000_000, 379_000_000], [345_000_000, 379_000_000, 413_000_000], [345_000_000]):
        assert D.signal(read, bad, bad, "assets", text) != D.AGREE
    assert D.signal([345_000_000, 379_000_000, 413_000_000], bad, bad, "assets", text) == D.DISAGREE
    # 계산된 비율(가산)도 빼지 않는다 — 원문에 없는 비율이 있으면 일치가 아니다
    assert D.signal([("%", 70)], {("%", 70), ("%", 90)}, {("%", 70), ("%", 90)}, "income", "월평균소득70%") == D.PARTIAL


class FakeSlot:
    name = "fake"

    def __init__(self, values):
        self.values = values

    def ask(self, prompt, schema):
        return {"values": self.values}


def test_llm_read_keeps_only_quotes_found_in_source():
    """인용이 원문 그 쪽에 글자 그대로 없거나, 값이 인용에 없으면 버린다(지어낸 답 = 답 없음)."""
    norm = sv.pdf_pages("N30")
    raw = norm                                  # 가짜 슬롯은 발췌를 읽지 않는다
    good = {"value": "345백만원", "quote": "총자산가액합산기준(345)백만원이하", "page": 6}
    made_up = {"value": "300백만원", "quote": "총자산가액합산기준(300)백만원이하", "page": 6}
    wrong_val = {"value": "400백만원", "quote": "총자산가액합산기준(345)백만원이하", "page": 6}
    got = D.llm_read(FakeSlot([good, made_up, wrong_val]), raw, norm, "일반", "assets")
    assert [v for v, _, _ in got] == [345_000_000]


def test_claude_reader_requires_approval():
    import pytest
    with pytest.raises(NotImplementedError):
        D.reader("claude:sonnet")
