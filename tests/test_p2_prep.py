# -*- coding: utf-8 -*-
"""test_p2_prep.py — P2 선행 안전장치(docs/09 §17)와 초안 판정 입구(src/draft.py).

1) 기준표 연도: 기준표를 직접 참조하는 조건(인용문에 금액 없는 것 포함)은 그 기준표 대표 금액이 원문에 없으면 보류.
2) 새 제한 문구: 규칙의 어느 조건도 인용하지 않는 지역·모집 제한 문구가 있으면 '지원 가능'을 '수동 확인'으로.
등록 공고에서는 둘 다 하나도 걸리지 않아야 한다(헛경보 0).
"""
import sys
from pathlib import Path

import draft
import golden_cases as gc
import pytest
import source_verify as sv
from rule_data import load_notice
from rule_engine import evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402
import templates as T  # noqa: E402


@pytest.mark.parametrize("nid", T.sheet_ids())
def test_no_false_alarms_on_registered_notices(nid):
    sheet = T.gold_sheet(nid)
    doc = sv.notice_doc(nid)
    assert X.reference_guard(doc, sv.pdf_pages(nid), sheet["template"], sheet["params"].get("kind")) == []
    assert X.new_restrictions(doc, sv.pdf_pages(nid)) == []


def test_reference_year_change_holds_conditions_without_amount_quotes():
    """다음 해 공고처럼 기준표 금액이 바뀌면 — 인용문에 금액이 없는 3순위 본인 소득(T3-income)까지 보류된다."""
    pages = [p.replace("4,576,036", "4,800,000").replace("6,452,897", "6,700,000").replace("8,168,429", "8,500,000")
             for p in sv.pdf_pages("N12")]
    stale = " ".join(X.reference_guard(sv.notice_doc("N12"), pages, "lh.youth_rental"))
    assert "N12-T3-income" in stale and "N12-T2-income" in stale


def test_new_restriction_phrase_downgrades_eligible():
    pages = sv.pdf_pages("N12") + ["2,3순위이번공고에서는모집하지않음"]
    found = X.new_restrictions(sv.notice_doc("N12"), pages)
    assert found and found[0][0] == len(pages)

    class R:
        verdict, failed = "ELIGIBLE", []
    assert X.adjust_verdict(R, set(), restricted=True) == "MANUAL_REVIEW"
    assert X.adjust_verdict(R, set(), restricted=False) == "ELIGIBLE"


@pytest.mark.parametrize("nid", ["N12", "N14", "N17", "N24", "N26"])
def test_draft_for_passing_programs_judges_like_the_registered_rules(nid):
    d = draft.make_draft(sv.pdf_path(nid).read_bytes())
    assert d.status == draft.OK and not any(d.held_conditions.values()) and not d.stale and not d.restrictions
    reg = load_notice(nid)
    for layer in list(reg.layers)[:2]:
        for _, _, p in list(gc.cases(only=[(nid, layer)]))[:150]:
            v, notes = draft.judge(d, p, layer)
            assert v == evaluate(p, reg, layer).verdict and notes[0].startswith("검증 전 초안")


def test_draft_refuses_other_programs_and_bad_files():
    assert draft.make_draft(sv.pdf_path("N10").read_bytes()).status == draft.UNSUPPORTED     # 행복주택(조건부)
    assert draft.make_draft(sv.pdf_path("N21").read_bytes()).status == draft.UNSUPPORTED     # 미리내집(불합격)
    assert draft.make_draft(b"not a pdf").status == draft.UNREADABLE
    with pytest.raises(ValueError):
        draft.judge(draft.Draft(draft.BLOCKED), None, "청년")


def test_draft_notice_is_loaded_through_the_rule_loader():
    """초안도 등록 규칙과 같은 로더(스키마 검증)를 거친다 — 다시 불러도 같은 계층."""
    d = draft.make_draft(sv.pdf_path("N17").read_bytes())
    assert d.notice.notice_id == "DRAFT" and list(d.notice.layers) == ["일반"]
