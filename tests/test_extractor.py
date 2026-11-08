# -*- coding: utf-8 -*-
"""test_extractor.py — PDF 글자 추출기 pypdfium2(2026-11-09 pypdf에서 교체, docs/10 '추출기 교체').

- 화면에 안 보이는 글자(그리기 방식 3·7, 쪽 영역 밖)는 보이는 글자가 있는 쪽에서 뺀다 — 정정 공고의 옛 내용이 섞이지 않게.
- 쪽 전체가 안 보이는 글자(스캔 PDF의 OCR 글자 층)면 그대로 둔다.
- 흰 글자·덮인 글자는 거르지 않는다(배경을 모른다 — 어두운 머리띠의 흰 제목은 보이는 글자다).
- 같은 공고를 '・'로 읽어도 '·'와 같게 대조한다. 조항 장부는 줄 안의 목록 기호에서도 문장을 나눈다.
"""
import sys
from pathlib import Path

import source_verify as sv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import clause_ledger as CL  # noqa: E402


def _pdf(tmp_path, pages):
    """쪽마다 PDF 그리기 명령(Helvetica, 영문)으로 시험 PDF를 만든다."""
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    w = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    for ops in pages:
        p = w.add_blank_page(612, 792)
        p[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        s = DecodedStreamObject()
        s.set_data(ops.encode())
        p[NameObject("/Contents")] = w._add_object(s)
    out = tmp_path / "t.pdf"
    w.write(str(out))
    return out.read_bytes()


def _txt(x, y, text, mode=0):
    return f"BT {mode} Tr /F1 14 Tf {x} {y} Td ({text}) Tj ET "


def test_invisible_text_is_dropped_but_ocr_layer_is_kept(tmp_path):
    data = _pdf(tmp_path, [
        _txt(72, 700, "VISIBLEA") + _txt(72, 680, "HIDDENMODE", mode=3),
        _txt(72, 700, "VISIBLED") + _txt(900, 900, "OUTSIDEBOX"),
        _txt(72, 700, "ONLYOCRA", mode=3) + _txt(72, 680, "ONLYOCRB", mode=3),          # 쪽 전체가 OCR 층
        _txt(72, 700, "VISIBLEB") + "1 1 1 rg " + _txt(72, 680, "WHITETEXT"),            # 흰 글자는 둔다
    ])
    raws = sv.raw_pages_bytes(data)
    assert "VISIBLEA" in raws[0] and "HIDDENMODE" not in raws[0]
    assert "VISIBLED" in raws[1] and "OUTSIDEBOX" not in raws[1]
    assert "ONLYOCRA" in raws[2] and "ONLYOCRB" in raws[2]
    assert "WHITETEXT" in raws[3]
    assert sv.extract_pages_bytes(data, cache=False)[0] == "VISIBLEA"


def test_unreadable_pdf_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        sv.extract_pages_bytes(b"%PDF-1.4 broken", cache=False)


def test_katakana_middle_dot_matches_middle_dot():
    assert sv.normalize("미성년자(만19세 미만)・외국인") == sv.normalize("미성년자(만19세 미만)·외국인")
    assert sv.page_has("N25", 20, "민법상 미성년자(만19세 미만)·외국인은 신청할 수 없습니다")


def test_registered_notices_have_no_hidden_text_dropped_except_off_page():
    """등록 공고에는 보이지 않게 그린 글자(방식 3·7)가 없다 — 추출기 교체로 등록 공고의 근거 문장이 사라지지 않는다."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as pr
    for nid in ("N1", "N25", "N55"):
        doc = pdfium.PdfDocument(str(sv.pdf_path(nid)))
        try:
            for i in range(len(doc)):
                assert not any(pr.FPDFTextObj_GetTextRenderMode(o.raw) in sv._INVISIBLE
                               for o in doc[i].get_objects(filter=[pr.FPDF_PAGEOBJ_TEXT])), (nid, i + 1)
        finally:
            doc.close()


def test_ledger_splits_inline_list_marks():
    units = CL._units_from_raw(["※난방방식은지역난방,구조는철근콘크리트벽식,지붕은평지붕입니다.※청약신청은주택타입별로공급물량이있는유형에한하여신청가능\n"
                                "•동일순위내경쟁시해당주택건설지역의거주자에게공급■일반공급대상자간경쟁시입주자선정기준\n"
                                "•우선공급대상자는조합의요청에의하며(별도안내문참고)•신청(수정)접수는지정된접수기간동안에"])
    texts = [u for _, u in units]
    assert texts[0].endswith("평지붕입니다.") and texts[1].startswith("※청약신청은")
    assert any(t.startswith("■일반공급대상자간") for t in texts)
    assert any(t.startswith("•신청(수정)접수는") for t in texts)


def test_known_matches_sibling_body_regardless_of_split_and_mark():
    known = CL.Known([(3, "-건설공사종사자(동일한고용주에게계속하여1년이상고용된자제외)-하역(항만)작업종사자")])
    assert known.has("•건설공사종사자(동일한고용주에게계속하여1년이상고용된자제외)")
    assert not known.has("•재건축조합원으로서관리처분계획인가를받은자")
