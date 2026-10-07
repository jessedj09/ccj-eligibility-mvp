# -*- coding: utf-8 -*-
"""test_source_verify.py — 규칙 데이터의 원문 근거가 공고문 PDF와 맞는지(src/source_verify.py) 검증.

1) 실제 데이터 전체 대조: 불일치가 0건이어야 한다.
2) 도구의 민감도: 쪽수·인용문·수치가 틀리면 실제로 잡아내는지(잡지 못하는 검사기는 안전장치가 아니다).
"""

import json

import pytest
import source_verify as sv
from source_verify import Report, normalize, page_has


@pytest.mark.parametrize("name", ["N1", "N2", "N3", "income_standard"])
def test_all_sources_match_the_pdfs(name):
    report = sv.verify_all()[name]
    assert report.ok, "\n".join(report.problems)
    assert report.checked > 0


def test_every_condition_and_table_was_checked():
    # 조건·표마다 최소 1건 이상 대조했는지(인용문이 비어 통과하는 일이 없게)
    for nid in ("N1", "N2", "N3"):
        doc = json.loads((sv.RULES / "notices" / f"{nid}.json").read_text(encoding="utf-8"))
        quotes = sum(len(c["source"].get("quote", [])) for ls in doc["layers"].values() for c in ls["conditions"])
        quotes += sum(len(t["source"]["quote"]) for t in doc["tables"].values())
        assert sv.verify_notice(nid).checked == quotes + 1       # +1 = sha256


def test_normalize_handles_pdf_spacing_and_circled_numbers():
    assert normalize("혼 인 기 간  7년") == normalize("혼인기간 7년")
    assert normalize("➀-㉮") == normalize("①-㉮")
    assert normalize("34,500만원") == "34,500만원"


# --- 민감도: 일부러 틀린 근거를 넣으면 잡아야 한다 -----------------------------------------
def check(nid, source):
    report = Report()
    sv._check_source(report, nid, "test", source)
    return report


def test_detects_wrong_page_and_reports_where_it_really_is():
    # N1 자녀가산표 수치는 p.5. p.4로 적으면 잡고, 실제 쪽을 알려 준다.
    assert check("N1", {"page": 5, "quote": ["345,000,000원"]}).ok
    bad = check("N1", {"page": 4, "quote": ["345,000,000원"]})
    assert not bad.ok and "[5" in bad.problems[0]


def test_detects_altered_quote_and_number():
    assert not check("N1", {"page": 5, "quote": ["혼인중이 아닐 것"]}).ok                  # 없는 문장
    assert not check("N1", {"page": 5, "quote": ["345,000,001원"]}).ok                     # 수치 1원 차이
    assert not check("N2", {"page": 5, "quote": ["10,900만원 이하이고"]}).ok               # 수치 변형(원문은 10,800만원)


def test_dict_form_quote_uses_its_own_page():
    assert check("N3", {"page": 5, "quote": [{"page": 3, "text": "대학생, 청년 계층의 주택 소유여부는 신청자 본인에 한하여 검증합니다"}]}).ok
    assert not check("N3", {"page": 3, "quote": [{"page": 5, "text": "대학생, 청년 계층의 주택 소유여부는 신청자 본인에 한하여 검증합니다"}]}).ok


def test_page_out_of_range_is_a_problem_not_a_crash():
    assert not page_has("N1", 0, "무주택")
    assert not page_has("N1", 999, "무주택")


def test_derivation_is_not_checked_against_pdf_but_counted():
    report = check("N1", {"page": 5, "quote": ["345,000,000원"], "derivation": "공고문에 없는 지침 문장"})
    assert report.ok and report.derivations == 1


def test_income_reference_number_not_in_cited_pages_is_detected(monkeypatch, tmp_path):
    ref = json.loads((sv.RULES / "reference" / "income_standard.json").read_text(encoding="utf-8"))
    ref["table"]["3"]["100"] += 1                               # 소득기준 1원 오타
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "income_standard.json").write_text(json.dumps(ref), encoding="utf-8")
    monkeypatch.setattr(sv, "RULES", tmp_path)
    report = sv.verify_income_reference()
    assert not report.ok and "8,168,430" in report.problems[0]
