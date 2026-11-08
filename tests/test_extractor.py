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


def test_ledger_allocation_and_boilerplate_are_not_new_conditions():
    """분양 공고의 지역별 물량 배분·장기복무군인 예외·주택형 배정 안내·사전청약 당첨자 제한·주택 소유 예외(규칙 제53조)는
    새 자격 조건이 아니다(2026-11-09 보류 원인 분석). 같은 문장에 '만 신청·신청할 수 없'이 있으면 배분으로 보지 않는다."""
    doc = {"layers": {"일반": {"conditions": []}}}
    units = [(6, "※해당주택건설지역거주자신청결과미달된물량은경기도거주자에게공급하고경기도거주자신청결과미달된물량은기타지역거주자에게공급합니다."),
             (12, "※10년·25년이상장기복무군인으로청약하는자는해당지역에실제거주하지않을경우0점"),
             (30, "■특별공급및일반공급신청자는주택타입별로배정물량이있는유형에대하여만신청가능하며"),
             (3, "•금회선정된사전청약당첨자및그세대에속한자는다른공공주택의사전청약모집에신청할수없으며,당첨되더라도부적격처리됩니다."),
             (7, "※「주택공급에관한규칙」개정시행('23.5.10.)전에임차주택을경매또는공매로매수한경우에도주택을소유하지않은것으로인정"),
             (6, "•서울특별시거주자만신청가능하며미달된물량은재공급하지않는자")]
    labels = [label for _, _, label in CL.classify(units, doc, CL.Known([]))]
    assert labels[:5] == ["무관:선정·순위", "무관:선정·순위", "무관:안내", "무관:공통 제한", "무관:정의"]
    assert labels[5] == CL.UNCLASSIFIED


def test_common_boilerplate_needs_two_other_notices_and_no_strong_restriction():
    known = CL.Known([], ["…•휴직자의소득은사회보장정보시스템을통해서조사된정상적으로근무한기간의소득자료를적용합니다.…",
                          "…•휴직자의소득은사회보장정보시스템을통해서조사된정상적으로근무한기간의소득자료를적용합니다.…",
                          "…•공고일현재만##세이상인자…"])
    assert known.has("•휴직자의소득은사회보장정보시스템을통해서조사된정상적으로근무한기간의소득자료를적용합니다.")
    assert not known.has("-공고일현재만65세이상인자")          # 강한 제한 표현·한 건뿐 — 새 조건일 수 있다
