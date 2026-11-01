# -*- coding: utf-8 -*-
"""test_g2_safety.py — G2(2026-11-01) 처음 보는 공고에서 찾은 안전 결함 두 가지.

1. 입주자격 완화 공고(화성동탄 행복주택: 소득·자산 요건 적용 배제, 혼인 10년·자녀 9세)를 평상시 템플릿으로 판정하면
   '지원 불가'가 틀린다 → 완화 문구가 있으면 자동 판정하지 않는다. 등록 공고에는 이 문구가 없다.
2. 찾지 못한 인용문의 조건 ID를 정규식으로 뽑아 '/'가 든 ID(DRAFT-R7/R7b)가 보류되지 않았다 → ID를 정확히 맞추고,
   표 인용문을 못 찾으면 그 표를 쓰는 조건도 보류한다.
"""
import sys
from pathlib import Path

import source_verify as sv
from rule_data import notice_ids

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

DOC = {"layers": {
    "청년": {"conditions": [
        {"id": "DRAFT-R7", "check": {"lte": [{"var": "monthly_income"}, 1]}},
        {"id": "DRAFT-R7/R7b", "check": {"lte": [{"var": "monthly_income"}, 1]}},
        {"id": "DRAFT-R9", "table": "terms", "check": {"lte": [{"var": "car_value"}, {"term": "car_limit"}]}},
    ]},
    "주거약자(26A1/B1형)": {"conditions": [
        {"id": "DRAFT-W", "check": {"lookup": ["rank_table", 1, 2]}},
        {"id": "DRAFT-T", "tracks": [{"id": "1", "conditions": [{"id": "DRAFT-T1", "check": {}}]}]},
    ]},
}}


def test_slash_in_condition_id_is_held_exactly():
    held = X.held_condition_ids(DOC, ["청년/DRAFT-R7/R7b: '월평균소득이 … 100퍼센트 이하'"])
    assert held == {"DRAFT-R7/R7b"}                       # 전에는 'DRAFT-R7'로 잘려 엉뚱한(또는 없는) 조건이 보류됐다
    assert X.held_condition_ids(DOC, ["청년/DRAFT-R7: '…'"]) == {"DRAFT-R7"}


def test_missing_table_quote_holds_conditions_using_it():
    assert X.held_condition_ids(DOC, ["table:terms: '45,420,000원'"]) == {"DRAFT-R9"}
    assert X.held_condition_ids(DOC, ["table:rank_table: '1인'"]) == {"DRAFT-W"}
    # 계층 이름에 '/'가 있어도, 트랙 안쪽 조건도
    assert X.held_condition_ids(DOC, ["주거약자(26A1/B1형)/DRAFT-T1: '…'"]) == {"DRAFT-T1"}


def test_relaxed_notice_is_not_judged():
    pages = ["안내", "•[입주자격완화](금회모집에한하여한시적적용)구분완화내용소득요건적용배제"]
    reason = X.relaxed_notice(pages)
    assert reason and "p.2" in reason and "자동 판정하지 않습니다" in reason
    assert X.relaxed_notice(["순자산평균값에서자녀1인15%완화(최대2자녀25%p)"]) is None   # 평상시 공고의 '완화' 표현


def test_no_registered_notice_looks_relaxed():
    for nid in notice_ids():
        assert X.relaxed_notice(sv.extract_pages(sv.pdf_path(nid))) is None, nid
