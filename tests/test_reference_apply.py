# -*- coding: utf-8 -*-
"""test_reference_apply.py — 표 읽기 적용(docs/09 §21 B단계).

1) 기준 연도가 바뀐 공고: 운영자가 승인한 새 기준표(`successor_of`)가 있고 그 표의 '모든 공고가 싣는 칸' 금액이 원문에 전부 있으면
   규칙이 그 표로 바뀌어 보류 없이 새 금액으로 판정된다. 후보(CANDIDATE)는 쓰지 않는다.
2) 결정표 위치 확인: 가구원수별 금액이 원문 표의 다른 가구원수 칸에만 있으면 그 표를 쓰는 조건을 보류한다(등록 공고 오경보 0).
3) 기준 연도가 다른 공고는 'reference' 작업(운영자 기준표 후보 검토)으로 넘어간다.
"""
import copy
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("pdfplumber")

import analysis  # noqa: E402
import draft  # noqa: E402
import rule_data  # noqa: E402
import source_verify as sv  # noqa: E402
import store as S  # noqa: E402
from rule_data import build_notice, load_notice  # noqa: E402
from rule_engine import HouseholdProfile, evaluate  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

OLD_ID = "income_standard_public"


def successor_of(ref, factor=1.05, year="2026"):
    new = copy.deepcopy(ref)
    new.update(id=f"{ref['id']}_{year}", successor_of=ref["id"], year_basis=year,
               table={s: {r: round(v * factor) for r, v in row.items()} for s, row in ref["table"].items()})
    return new


@pytest.fixture
def next_year(monkeypatch):
    """국민임대 기준표의 '내년 표'를 승인된 새 기준표로 둔 세계 + 그 금액을 실은 N30 원문(모의 새해 공고)."""
    old = X._reference(OLD_ID)
    new = successor_of(old)
    real_ref, real_load = X._reference, rule_data.load_reference
    monkeypatch.setattr(X, "_reference", lambda rid: new if rid == new["id"] else real_ref(rid))
    monkeypatch.setattr(X, "successors", lambda: {OLD_ID: [new]})
    monkeypatch.setattr(rule_data, "load_reference",
                        lambda rid: rule_data.ReferenceTable(new) if rid == new["id"] else real_load(rid))
    pages = list(sv.pdf_pages("N30"))
    for s, row in old["table"].items():
        for r, v in row.items():
            pages = [p.replace(f"{v:,}", f"{new['table'][s][r]:,}") for p in pages]
    return old, new, pages


def income_verdict(notice, income, size=3):
    p = HouseholdProfile(profile_id="T", age=40, marital_status="혼인중", home_ownership="무주택", household_size=size,
                         monthly_income=income, total_assets=10_000_000, car_value=0, children_birth_dates=[])
    return evaluate(p, notice, "일반").verdict


def test_stale_notice_switches_to_approved_successor(next_year):
    old, new, pages = next_year
    doc = sv.notice_doc("N30")
    assert X.reference_guard(doc, pages, "lh.national_rental")            # 지금은 기준 연도가 달라 보류
    doc2, swaps = X.swap_successors(doc, pages)
    assert swaps == {OLD_ID: new["id"]}
    assert X.reference_guard(doc2, pages, "lh.national_rental") == []
    assert f'"{OLD_ID}"' not in json.dumps(doc2, ensure_ascii=False)


def test_switched_rule_judges_with_new_year_amounts(next_year):
    old, new, pages = next_year
    doc2, _ = X.swap_successors(sv.notice_doc("N30"), pages)
    limit = new["table"]["3"]["70"]                                       # 3인 70%(내년 표)
    assert limit > old["table"]["3"]["70"]
    assert income_verdict(build_notice(doc2), limit) == "ELIGIBLE"
    assert income_verdict(build_notice(doc2), limit + 1) == "INELIGIBLE"
    assert income_verdict(load_notice("N30"), limit) == "INELIGIBLE"     # 옛 표라면 불가였을 소득


def test_no_switch_when_successor_amounts_are_not_in_notice(next_year):
    doc = sv.notice_doc("N30")
    assert X.swap_successors(doc, sv.pdf_pages("N30")) == (doc, {})      # 올해 공고(옛 금액)에는 새 표를 쓰지 않는다


def test_candidates_are_never_used_as_successors(tmp_path, monkeypatch):
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir()
    old = X._reference(OLD_ID)
    approved, pending = successor_of(old, year="2026"), successor_of(old, year="2027")
    pending.update(id=f"{OLD_ID}_2027", status="CANDIDATE")
    for doc in (old, approved, pending):
        (ref_dir / f"{doc['id']}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(sv, "RULES", tmp_path)
    assert [r["id"] for r in X.successors()[OLD_ID]] == [f"{OLD_ID}_2026"]


@pytest.mark.parametrize("nid", ["N18", "N23", "N26", "N3", "N30"])
def test_decision_table_positions_have_no_false_alarm(nid):
    assert X.table_positions(sv.notice_doc(nid), sv.pdf_path(nid), sv.pdf_pages(nid)) == []


def test_amount_in_another_household_size_cell_holds_the_table():
    doc = copy.deepcopy(sv.notice_doc("N23"))
    rows = [r for r in doc["tables"]["j2_income_60이하"]["rows"] if X._money_out(r.get("out"))]
    rows[0]["out"], rows[2]["out"] = rows[2]["out"], rows[0]["out"]          # 2인·3인 금액을 맞바꿈
    found = X.table_positions(doc, sv.pdf_path("N23"), sv.pdf_pages("N23"))
    assert found and all(m.startswith("table:j2_income_60이하:") for m in found)
    assert X.held_condition_ids(doc, found) == {"N23-income"}          # 그 표를 쓰는 소득 조건만 보류


def test_stale_reference_goes_to_operator_reference_job():
    assert "reference" in S.KINDS
    stale = draft.Draft(draft.OK, "초안", program="국민임대", stale=["일반/N-income: '기준표 금액이 원문에 없음'"])
    assert analysis.follow_up(stale, "LH") == ("reference", 8)
    assert analysis.follow_up(stale, None) is None
    assert "src/pdf_tables.py" in analysis.CODE


# ---- 운영자 검토 화면: reference 작업에서 기준표 후보 만들기 ----
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)


class Fake(S.NullStore):
    available = True

    def program_health(self):
        return []

    def list_jobs(self, kind=None, status=None, limit=100):
        return [dict(id=9, sha256="cd" * 32, kind="reference", status="pending", priority=8, attempts=0, error=None,
                     updated_at=NOW, issuer="LH", program="국민임대", title=None, announcement_date=date(2026, 9, 7),
                     first_seen=NOW, has_pdf=True)]

    def latest_snapshot(self, sha):
        return {"status": "ok", "template": "lh.national_rental", "reason": "", "held_conditions": {}, "held_fields": [],
                "stale": ["일반/DRAFT-G-income: '기준표 income_standard_public 금액 … 원문에 없음(다른 기준 연도)'"]}

    def get_pdf(self, sha):
        return sv.pdf_path("N30").read_bytes()

    def usage(self, days=14):
        return []


def test_operator_page_builds_reference_candidates(monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(S, "get_store", lambda: Fake())
    at = AppTest.from_file(str(Path(sv.PROJECT) / "ops" / "review.py"), default_timeout=120)
    at.session_state["operator_on"] = True
    at.run()
    assert any("기준표 후보(연도 전환)" in e.label for e in at.expander)
    assert any("기준 연도 다름" in c.value for c in at.caption)
    at.button(key="pdf_9").click().run()
    at.button(key="refc_9").click().run()
    # 실제 N30(올해 금액)은 등록 기준표로 설명되므로 후보가 없다 — 화면은 그 사실을 알린다
    assert any("후보 없음" in c.value for c in at.caption)
