# -*- coding: utf-8 -*-
"""test_p0_upload.py — 공고 업로드 판정 P0: 업로드한 PDF의 공고 식별(src/notice_identify.py)과 3상태 표시(src/display_status.py).

판정은 기존 엔진 그대로이고, 여기서는 "어떤 공고로 판정할지"를 틀리지 않는지만 본다 — 잘못 식별하면 다른 공고의 규칙으로
판정하게 되므로, 확실하지 않으면 판정하지 않는(UNREGISTERED) 쪽으로 가야 한다.
"""
import io

import notice_identify as ni
import pytest
import source_verify as sv
from display_status import DISPLAY, HOLD_GROUP, display
from rule_data import load_notice, notice_ids

FAKE_SHA = "0" * 64


def test_every_registered_pdf_is_identified_by_fingerprint():
    for nid in notice_ids():
        r = ni.identify_pdf(sv.pdf_path(nid).read_bytes())
        assert (r.status, r.notice_id) == (ni.REGISTERED, nid)


@pytest.mark.parametrize("nid", notice_ids())
def test_same_notice_in_another_file_is_found_by_text(nid):
    """지문이 다른 같은 공고(다시 내려받기·재저장) — 공고일·사업 유형(·단지명)으로 찾되, 판정 전 확인이 필요한 상태로."""
    r = ni.identify_pages(FAKE_SHA, sv.pdf_pages(nid))
    assert (r.status, r.notice_id) == (ni.SAME_NOTICE_OTHER_FILE, nid), (r.status, r.notice_id, r.ambiguous)
    assert r.announcement == str(load_notice(nid).announcement_date)


def test_resaved_pdf_bytes_end_to_end():
    """실제로 다시 저장한 PDF(바이트가 다름) — 금천·오류는 같은 날 같은 사업이라 단지명으로 가려야 한다."""
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for page in PdfReader(str(sv.pdf_path("N10"))).pages:
        w.add_page(page)
    buf = io.BytesIO()
    w.write(buf)
    data = buf.getvalue()
    assert data != sv.pdf_path("N10").read_bytes()
    r = ni.identify_pdf(data)
    assert (r.status, r.notice_id) == (ni.SAME_NOTICE_OTHER_FILE, "N10")


def test_unregistered_notice_is_not_judged_but_candidates_are_shown():
    pages = [p.replace("2026.09.17", "2026.12.17").replace("26.09.17", "26.12.17") for p in sv.pdf_pages("N12")]
    r = ni.identify_pages(FAKE_SHA, pages)
    assert r.status == ni.UNREGISTERED and r.notice_id is None
    assert r.announcement == "2026-12-17" and r.program == "청년매입임대" and r.issuer == "LH"
    assert {"N11", "N12"} <= set(r.similar)


def test_same_day_same_program_without_site_name_is_ambiguous_not_guessed():
    pages = [p.replace("서울금천", "").replace("서울오류", "") for p in sv.pdf_pages("N6")]
    r = ni.identify_pages(FAKE_SHA, pages)
    assert r.status == ni.UNREGISTERED and r.notice_id is None and set(r.ambiguous) == {"N6", "N10"}


def test_unreadable_inputs():
    assert ni.identify_pdf(b"not a pdf").status == ni.UNREADABLE
    assert ni.identify_pages(FAKE_SHA, ["", "  "]).status == ni.UNREADABLE


def test_uploaded_file_is_not_written_to_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(sv, "PDF_CACHE", tmp_path)
    pages = sv.extract_pages_bytes(sv.pdf_path("N2").read_bytes(), cache=False)
    assert pages == sv.pdf_pages("N2")
    assert not list(tmp_path.iterdir())


def test_three_state_display_covers_every_verdict():
    assert set(DISPLAY) == {"ELIGIBLE", "INELIGIBLE", "NEEDS_INFO", "MANUAL_REVIEW", "NOT_OFFERED"}
    assert display("ELIGIBLE").title == "지원 가능" and display("INELIGIBLE").title == "지원 불가"
    assert display("NEEDS_INFO").group == display("MANUAL_REVIEW").group == HOLD_GROUP
    assert display("NEEDS_INFO").title == "보류 — 추가 정보 필요"
    assert display("MANUAL_REVIEW").title == "보류 — 수동 확인 필요" and "1600-1004" in display("MANUAL_REVIEW").todo
