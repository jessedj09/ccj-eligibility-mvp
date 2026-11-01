# -*- coding: utf-8 -*-
"""test_open_all_programs.py — 2026-11-02 사용자 결정: 판정 틀이 있는 사업은 모두 새 업로드 자동 판정(PASSING)에 연다.

각 사업의 등록 공고 원문을 '처음 보는 공고'처럼 자동 분석(draft.make_draft)해, 초안이 만들어지고 골든 입력에서 초안이
'지원 가능'인데 등록 규칙은 아닌 경우(틀린 지원 가능)가 없는지 본다. 초안이 더 조심(보류)한 것은 허용한다.
"""
import draft
import golden_cases as gc
import pytest
import source_verify as sv
from display_status import display
from rule_data import load_notice
from rule_engine import evaluate

OPENED = {"N30": "lh.national_rental", "N33": "lh.permanent_rental", "N35": "lh.integrated_rental",
          "N46": "lh.newlywed_town_sale", "N49": "lh.public_sale", "N51": "sh.land_sale"}


def test_all_templates_with_rules_are_open():
    for t in OPENED.values():
        assert t in draft.PASSING
    assert len(draft.passing_programs()) == len(draft.PASSING)


@pytest.mark.parametrize("nid,template", sorted(OPENED.items()))
def test_new_upload_is_judged_without_wrong_eligible(nid, template):
    d = draft.make_draft(sv.pdf_path(nid).read_bytes())
    assert d.status == draft.OK and d.template == template, d.reason
    reg = load_notice(nid)
    for layer in reg.layers:
        if layer not in d.notice.layers:
            continue
        for _, _, p in list(gc.cases(only=[(nid, layer)]))[:120]:
            v = draft.judge(d, p, layer)[0]
            r = evaluate(p, reg, layer).verdict
            if v == "ELIGIBLE":
                assert r == "ELIGIBLE", (nid, layer, p.profile_id)
            if display(v).group != display(r).group:
                assert display(v).group == display("NEEDS_INFO").group, (nid, layer, v, r)   # 다르면 초안이 보류여야
