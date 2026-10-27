# -*- coding: utf-8 -*-
"""test_a_stage.py — A단계: 초안으로 공고 등록 돕기(A1, notice_intake --draft)와 운영자 미리보기(A2) 잠금·판정.

A1) 등록 공고를 새 공고처럼 넣으면 — 합격 사업은 보류 0이고, 보고서의 생성 스크립트 항목을 그대로 붙여 넣어 만든 규칙이
    원문 대조를 모두 통과하고 등록 규칙과 같은 조건을 갖는다. 행복주택은 핵심 빈칸(1순위 지역)이 보류로 드러난다.
A2) 운영자 비밀번호 확인, 초안 판정 결과(근거 표시용)는 엔진 결과 그대로이고 판정만 낮춘다.
"""
import json
import sys
from pathlib import Path

import draft
import golden_cases as gc
import operator_mode
import pytest
import source_verify as sv
from rule_data import build_notice, load_notice
from rule_engine import evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import notice_intake as ni  # noqa: E402
import templates as T  # noqa: E402


def _report(nid):
    return ni.report(sv.pdf_path(nid), pages=sv.pdf_pages(nid), with_draft=True)


def _snippet_plan(md: str) -> dict:
    """보고서 8-4절의 파이썬 항목을 그대로 읽는다(생성 스크립트에 붙여 넣는 것과 같은 글자)."""
    code = md.split("### 8-4.")[1].split("```python")[1].split("```")[0]
    body = "\n".join(line for line in code.splitlines() if not line.strip().startswith("#")).strip().rstrip(",")
    return eval(body, {"dict": dict})


def _ids(doc):
    def walk(cs):
        for c in cs:
            yield c["id"].split("-", 1)[1]
            for t in c.get("tracks", []):
                yield from walk(t["conditions"])
    return {layer: sorted(walk(ld["conditions"])) for layer, ld in doc["layers"].items()}


@pytest.mark.parametrize("nid", ["N12", "N14", "N17", "N24", "N26"])
def test_draft_report_snippet_rebuilds_the_notice(nid):
    r = _report(nid)
    md = ni.to_markdown(r)
    d = r["draft"]
    assert d.status == draft.OK and d.held_fields == [] and "보류된 빈칸 — 원문에서 직접 찾아 채울 것\n- 없음" in md
    plan = _snippet_plan(md)
    gold = T.gold_sheet(nid)
    assert plan["nid"] == nid and plan["key"] == gold["meta"]["key"] and plan["ann"] == gold["announcement_date"]
    assert plan["template"] == T.TEMPLATES[gold["template"]]["builder"]
    sheet = dict(gold, params=plan["params"])            # 제목·notes는 사람이 채우는 칸 — 정답 시트 것을 쓴다
    doc, missing = T.build(sheet, sv.pdf_path(nid), sv.pdf_pages(nid))
    assert missing == [] and _ids(doc) == _ids(sv.notice_doc(nid))


def test_draft_report_shows_held_critical_field_for_happy_housing():
    r = _report("N10")
    md = ni.to_markdown(r)
    assert r["draft"].status == draft.BLOCKED
    assert "`region` **(핵심 — 판정에 직접 쓰임)**" in md and "대상 아님" in md
    assert "# tools/gen_c1_notices.py TARGETS" in md and "# tools/gen_c3_layers.py PLAN" in md
    assert "# 보류(원문에서 확인해 고칠 것): region" in md


def test_new_notice_gets_next_ids_and_index_entry():
    r = _report("N24")
    r["registered_as"], r["analysis_key"] = None, ni.analysis_key("0" * 64, "SH")     # 처음 보는 원문인 것처럼
    md = ni.to_markdown(r)
    assert r["analysis_key"] == "SH27" and ni.analysis_key(sv.notice_doc("N24")["source"]["sha256"], "SH") == "SH26"
    assert f'dict(nid="{r["next_id"]}", key="SH27"' in md
    entry = json.loads(md.split("### 8-5.")[1].split("```json")[1].split("```")[0])
    assert entry["key"] == "SH27" and entry["sha256"] == r["sha256"] and entry["file"].startswith("sample_sh/")


def test_save_draft_writes_loadable_rules(tmp_path):
    out = tmp_path / "draft.json"
    assert ni.main([str(sv.pdf_path("N17")), "--save-draft", str(out), "--out", str(tmp_path / "r.md")]) == 0
    notice = build_notice(json.loads(out.read_text(encoding="utf-8"))["doc"])      # 초안 스냅샷(B2)의 규칙 문서
    reg = load_notice("N17")
    assert list(notice.layers) == list(reg.layers)
    for _, _, p in list(gc.cases(only=[("N17", "일반")]))[:50]:
        assert evaluate(p, notice, "일반").verdict == evaluate(p, reg, "일반").verdict


def test_operator_password_check(monkeypatch):
    assert operator_mode.check("pw", "pw") and not operator_mode.check("pw", "other")
    assert not operator_mode.check("", None) and not operator_mode.check("pw", "")
    monkeypatch.setattr(operator_mode.st, "secrets", {})          # secrets에 없으면 환경변수
    monkeypatch.delenv(operator_mode.ENV, raising=False)
    assert operator_mode.configured_password() is None
    monkeypatch.setenv(operator_mode.ENV, "from-env")
    assert operator_mode.configured_password() == "from-env"
    monkeypatch.setattr(operator_mode.st, "secrets", {"operator_password": "from-secrets"})
    assert operator_mode.configured_password() == "from-secrets"


def test_evaluate_draft_keeps_engine_result_and_lowers_only_the_verdict():
    d = draft.make_draft(sv.pdf_path("N12").read_bytes(), pages=sv.pdf_pages("N12"))
    eligible = next(p for _, _, p in gc.cases(only=[("N12", "청년")])
                    if evaluate(p, load_notice("N12"), "청년").verdict == "ELIGIBLE")
    r, notes = draft.evaluate_draft(d, eligible, "청년")
    assert r.verdict == "ELIGIBLE" and notes == [draft.NOTE]
    d.restrictions = [(3, "2,3순위이번공고에서는모집하지않음")]
    r2, notes2 = draft.evaluate_draft(d, eligible, "청년")
    assert r2.verdict == "MANUAL_REVIEW" and r2.matched == r.matched and r2.failed == r.failed
    assert any("제한 문구" in n for n in notes2)
    assert draft.judge(d, eligible, "청년")[0] == "MANUAL_REVIEW"


def test_field_rows_flattens_nested_fields():
    d = draft.make_draft(sv.pdf_path("N24").read_bytes(), pages=sv.pdf_pages("N24"))
    paths = [p for p, _ in draft.field_rows(d.fields)]
    assert "dates.marriage" in paths and "quotes.home" in paths and "weak_quote" in paths
