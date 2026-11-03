# -*- coding: utf-8 -*-
"""test_eval_llm_slot.py — LLM 슬롯 문장 찾기 시험 도구(tools/eval_llm_slot.py, docs/09 §20). CI에는 Ollama가 없으므로 가짜 슬롯으로
문항 만들기와 채점만 시험한다."""
import sys
from pathlib import Path

import source_verify as sv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import eval_llm_slot as E  # noqa: E402


class Answer:
    """정해진 문장을 돌려주는 가짜 슬롯 — 문항마다 정답 / 다른 쪽 문장 / 없음."""
    name = "fake"

    def __init__(self, pick):
        self.pick = pick

    def find_sentence(self, raw, pages, what, example):
        return self.pick(example)


def test_items_are_real_sentences_with_reworded_examples():
    its = E.items()
    assert len(its) >= 30 and {"sh.newlywed", "lh.happy_housing"} <= {i["template"] for i in its}
    for it in its:
        assert it["target"] in sv.pdf_pages(it["nid"])[it["page"] - 1]                # 정답은 그 쪽 원문에 있다
        assert E._digits_masked(it["example"]) != E._digits_masked(it["target"])     # 숫자·날짜만 다른 문항은 없다
        assert it["sibling"] != it["nid"]


def test_judge_categories():
    it = {"target": sv.normalize("혼인기간이7년이내일것또는6세이하자녀(태아포함)를둔자"), "page": 5}
    assert E.judge(None, it) == "none"
    assert E.judge((5, it["target"]), it) == "right"
    assert E.judge((5, "1)신혼부부:" + it["target"] + "*혼인기간산정은혼인신고일기준으로함"), it) in ("right", "overlap")
    assert E.judge((3, it["target"]), it) == "different"                            # 다른 쪽
    assert E.judge((5, sv.normalize("한부모가족증명서가발급가능한자")), it) == "different"


def test_run_scores_a_slot_that_copies_the_answer():
    its = [i for i in E.items() if i["template"] == "sh.newlywed"][:3]
    by_example = {i["example"]: i for i in its}
    res = E.run(Answer(lambda ex: (by_example[ex]["target"], by_example[ex]["page"])), its)
    assert [r["verdict"] for r in res] == ["right"] * len(its)
    res = E.run(Answer(lambda ex: None), its)
    assert {r["verdict"] for r in res} == {"none"}
