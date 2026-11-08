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


def test_upload_is_read_once_for_ledger_raw_text(monkeypatch, tmp_path):
    """조항 장부의 띄어쓰기 유지 원문(raw_pages)은 방금 업로드 추출을 다시 쓴다 — PDF를 두 번 읽지 않고, 결과는 새로 읽은 것과 같다."""
    import llm_slot as L
    data = sv.pdf_path("N2").read_bytes() + b"\n%upload-once\n"       # 지문을 바꿔 다른 캐시에 걸리지 않게
    pdf = tmp_path / "up.pdf"
    pdf.write_bytes(data)
    sv.extract_pages_bytes(data, cache=False)
    cached = L.raw_pages(pdf)
    monkeypatch.setattr(sv, "_read_pdf", lambda *a, **k: pytest.fail("두 번째 추출"))
    assert L.raw_pages(pdf) == cached
    monkeypatch.undo()
    with sv._recent_lock:
        sv._recent_raw.clear()
    assert L.raw_pages(pdf) == cached                                     # 캐시 없이 새로 읽어도 같다


def test_three_state_display_covers_every_verdict():
    assert set(DISPLAY) == {"ELIGIBLE", "INELIGIBLE", "NEEDS_INFO", "MANUAL_REVIEW", "NOT_OFFERED"}
    assert display("ELIGIBLE").title == "지원 가능" and display("INELIGIBLE").title == "지원 불가"
    assert display("NEEDS_INFO").group == display("MANUAL_REVIEW").group == HOLD_GROUP
    assert display("NEEDS_INFO").title == "보류 — 추가 정보 필요"
    assert display("MANUAL_REVIEW").title == "보류 — 수동 확인 필요" and "1600-1004" in display("MANUAL_REVIEW").todo


def test_not_a_notice_is_told_apart():
    """앞쪽에 모집 공고 표현이 없으면 입주자모집공고문이 아니다(당첨자 명단·안내문 등) — A1."""
    r = ni.identify_pages("x", ["단지명성명접수번호동호평면유형공급구분강일리버파크11최*자행복주택(고령자)", "당첨자명단"])
    assert r.status == ni.NOT_NOTICE and "입주자모집공고문이 아닌" in r.reason


def test_unsupported_programs_are_recognized():
    """판정하지 않는 사업도 이름을 알아본다 — 분양은 '다음 단계', 임대는 '차례로 추가' 안내(A1)."""
    import draft
    import notice_candidates as nc
    cases = {
        "www.i-sh.co.kr2026고덕강일지구3단지토지임대부분양주택입주자모집공고▶공급위치": ("SH", "토지임대부 분양주택"),
        "2023년9월사전청약나눔형(이익공유형)공공분양주택입주자모집공고": (None, "공공분양(나눔형)"),
        "-1-○○국민임대주택예비입주자모집공고apply.lh.or.kr": ("LH", "국민임대주택"),
        "-1-구리갈매역세권A-1BL신혼희망타운행복주택입주자모집(입주자모집공고일:2026.10.27)장기임대주택(통합공공임대,국민임대)":
            ("LH", "행복주택(신혼희망타운)"),
    }
    for text, want in cases.items():
        assert nc.classify([text]) == want, text
    assert nc.is_sale("토지임대부 분양주택") and not nc.is_sale("국민임대주택")
    assert "이 분양 공고(토지임대부 분양주택)" in draft.unsupported_reason("토지임대부 분양주택")   # 공공분양 일부는 판정 — '다음 단계' 안내는 뺐다
    assert "차례로 추가" in draft.unsupported_reason("국민임대주택")


def test_registered_notices_keep_their_program():
    """사업 이름표를 넓혀도 등록 공고 26건은 그대로 알아본다(본문의 다른 사업 언급에 끌려가지 않음)."""
    import notice_candidates as nc
    from notices_data import ALL_NOTICES
    for nid, n in ALL_NOTICES.items():
        pages = sv.pdf_pages(nid)
        issuer, program = nc.classify(pages)
        assert nc.looks_like_notice(pages), nid
        assert program and program.replace("SH ", "") in n.meta["program"].replace("SH ", ""), (nid, program)


def test_same_day_same_program_other_site_is_not_bound_to_the_registered_notice():
    """G2: 같은 날 같은 사업의 미등록 공고(화성동탄 행복주택 10-27 ↔ 구리갈매 N28 10-27)를 등록 공고로 묶으면 사용자가
    확인란을 누르는 순간 다른 공고의 규칙으로 판정한다 — 후보가 하나여도 단지 이름이 앞쪽에 없으면 미등록으로."""
    pages = [p.replace("구리갈매역세권", "화성동탄").replace("구리갈매", "화성동탄") for p in sv.pdf_pages("N28")]
    r = ni.identify_pages(FAKE_SHA, pages)
    assert r.status == ni.UNREGISTERED and r.notice_id is None
    assert "N28" in r.reason
