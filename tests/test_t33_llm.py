# -*- coding: utf-8 -*-
"""test_t33_llm.py — LLM 슬롯 연결(P1 T3.3). CI에는 Ollama가 없으므로 정해진 답을 돌려주는 가짜 슬롯으로 '검증 규칙'을 시험한다:
LLM이 무엇을 답하든 원문에 없거나, 다른 주제거나, 지역 목록이 다르면 쓰지 않는다(보류)."""
import sys
from datetime import date
from pathlib import Path

import source_verify as sv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import llm_slot as L  # noqa: E402
import sheet_extract as X  # noqa: E402
import templates as T  # noqa: E402


class FakeSlot:
    name = "fake"

    def __init__(self, sentence=None, answer=None):
        self.sentence, self.answer, self.asked = sentence, answer or {}, 0

    def find_sentence(self, raw, pages, what, example):
        self.asked += 1
        return (self.sentence, 1) if self.sentence else None

    def ask(self, prompt, schema):
        self.asked += 1
        return self.answer


SIB = [{"notice_id": "S1", "announcement_date": "2026-09-30",
        "params": {"quotes": {"home": "무주택세대구성원으로서 아래의 신혼·신생아Ⅱ 매입임대주택 세부 신청자격 중"}}}]
RAW = ["가. 신청자격 무주택세대구성원으로서 아래의 일반주택형 미리내집 세부 신청자격 중 하나에 해당하는 자. 소득 기준은 별도."]
PAGES = [sv.normalize(RAW[0])]


def _quotes(slot):
    return X.adapt_quotes(PAGES, date(2026, 8, 14), SIB, lambda s: s["params"]["quotes"], X.LLM(slot, RAW))["home"]


def test_llm_sentence_used_only_if_in_source_and_on_topic():
    ok = _quotes(FakeSlot("무주택세대구성원으로서 아래의 일반주택형 미리내집 세부 신청자격 중"))
    assert ok.status == X.FILLED and ok.how.startswith("LLM(fake)")
    assert _quotes(FakeSlot("무주택세대구성원으로서 아래의 공공한옥 세부 신청자격 중")).status == X.HELD   # 원문에 없음
    assert _quotes(FakeSlot("소득 기준은 별도")).status == X.HELD                                    # 다른 주제(겹침 낮음)
    assert _quotes(FakeSlot(None)).status == X.HELD


def test_without_llm_nothing_is_asked():
    q = X.adapt_quotes(PAGES, date(2026, 8, 14), SIB, lambda s: s["params"]["quotes"])
    assert q["home"].status == X.HELD


ADJ = T.C1.SEOUL_ADJ
FIRST = "해당 주택건설지역(서울특별시) 또는 연접지역(" + ", ".join(ADJ[1:]) + ")이 거주지나 재학 중인 대학 소재지인 자"
NORE = "2,3순위 이번 공고에서는 모집하지 않음"


def _region(first):
    raw = [f"3-1.대학생계층 {first} {NORE}"]
    pages = [sv.normalize(raw[0])]
    slot = FakeSlot(answer={"first_rank": first, "not_recruited": NORE})
    return X._llm_region(pages, X.LLM(slot, raw), ["대학생"], {"대학생": 1})


def test_region_needs_exactly_the_template_region_list():
    got = _region(FIRST)
    assert got and got["대학생"]["fields"] == ["residence_area", "school_area"] and got["대학생"]["quote"] == [FIRST, NORE]
    assert _region(FIRST.replace(", 고양시", "")) is None                 # 목록에서 빠진 지역
    assert _region(FIRST.replace("양주시", "양주시, 수원시")) is None        # 목록 밖 지역(수원시)


def test_similarity_and_page_choice():
    assert L.bigram_similarity("혼인 7년 이내인 사람", "혼인 7년 이내인 자") > 0.5
    assert L.bigram_similarity("혼인 7년 이내인 사람", "자동차 가액 기준") == 0.0
    assert L.pages_like(["자동차 기준", "혼인7년이내인사람조건"], "혼인 7년 이내인 사람", 1) == [2]


def test_snap_copies_the_source_text_not_the_model_text():
    """LLM 답은 위치로만 쓰고 인용문은 원문에서 잘라 온다 — 조사 한 글자가 달라도 원문 그대로, 섞어 만든 문장은 거부."""
    pages = [sv.normalize("6세 이하의 자녀가 있는 한부모가족 6세 이하 자녀를 둔 모자가족 또는 부자가족('19.08.15.이후 출생한 자녀) "
                          "해당 세대의 월평균소득이 전년도 도시근로자 가구당 월평균소득의 130% 이하(본인 및 배우자가 소득이 있는 경우 200%)")]
    got = X.snap(pages, "6 세 이하의 자녀를 둔 모자가족 또는 부자가족(’19. 08. 15. 이후 출생한 자녀)")
    assert got == (1, "6세이하자녀를둔모자가족또는부자가족('19.08.15.이후출생한자녀)")
    assert X.snap(pages, "해당 세대의 월평균소득이 전년도 도시근로자 가구원수별 가구당 월평균소득의 130% 이하 (맞벌이 인 경우 200% 이하)") is None
    assert X.snap(pages, "전혀 관계없는 문장인데 원문에는 없는 내용입니다") is None
