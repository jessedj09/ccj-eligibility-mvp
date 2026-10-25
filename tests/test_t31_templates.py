# -*- coding: utf-8 -*-
"""test_t31_templates.py — 사업 템플릿과 파라미터 시트(P1 T3.1, tools/templates.py).

1) 정답 시트(생성 스크립트의 값)로 다시 만들면 등록 규칙과 똑같다 — 템플릿이 정확하다.
2) 시트의 값이 그 공고 것이 아니면(다른 차수·다른 연도) 원문에 없는 인용문이 'missing'으로 드러난다 — 연도별 상수가 바뀐
   새 공고에서 옛 값으로 조용히 판정하지 않게 하는 안전장치.
   한계: 공고에 있어야 할 조건이 시트에서 **빠진** 경우(예: 1순위 지역만 모집)는 인용문이 없으니 여기서 잡히지 않는다 —
   추출 평가(T3.4)의 판정 일치율(골든 입력)로 잡는다.
"""
import json
import sys
from pathlib import Path

import pytest
import source_verify as sv
from rule_data import notice_ids

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import templates as T  # noqa: E402


@pytest.mark.parametrize("nid", T.sheet_ids())
def test_gold_sheet_rebuilds_the_registered_rules_exactly(nid):
    doc, missing = T.build(T.gold_sheet(nid), T.pdf_of(nid))
    assert missing == []
    assert doc == sv.notice_doc(nid)


def test_every_registered_notice_has_a_sheet_except_base_notices():
    assert set(T.sheet_ids()) | set(T.BASE_NOTICES) == set(notice_ids())
    assert {T.gold_sheet(n)["template"] for n in T.sheet_ids()} == set(T.TEMPLATES)


@pytest.mark.parametrize("nid", T.sheet_ids())
def test_sheet_is_plain_json_and_matches_the_template_spec(nid):
    sheet = T.gold_sheet(nid)
    assert json.loads(json.dumps(sheet, ensure_ascii=False)) == sheet
    spec = {p.name for p in T.TEMPLATES[sheet["template"]]["params"]}
    assert set(sheet["params"]) <= spec
    optional = {"weak_quote"}
    assert spec - optional <= set(sheet["params"]), spec - set(sheet["params"])
    assert sheet["announcement_date"]


def _rebuild(sheet_of, pdf_of):
    sheet = T.gold_sheet(sheet_of)
    sheet["notice_id"] = pdf_of
    return T.build(sheet, T.pdf_of(pdf_of))[1]


def test_values_from_another_round_are_caught_as_missing_quotes():
    """청년매입임대 2차 값을 3차 원문에 — 출생일 범위·30세 기준일 문구가 3차 원문에 없다."""
    missing = _rebuild("N11", "N12")
    assert missing and all("1986.06.26" in m or "1996.06.26" in m for m in missing)


def test_values_from_another_year_are_caught_as_missing_quotes():
    """장기전세 50차(당해 연도 기준) 시트를 49차(이전 연도) 원문에 — 자산·자동차 한도와 소득 금액이 다르다."""
    missing = " ".join(_rebuild("N26", "N25"))
    assert "66,200만원" in missing and "4,542만원" in missing


def test_happy_housing_cutoff_dates_from_another_notice_are_caught():
    missing = " ".join(_rebuild("N4", "N10"))
    assert "2019-10-02" in missing
