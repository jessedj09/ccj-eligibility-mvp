# -*- coding: utf-8 -*-
"""test_g1_region.py — G1(2026-11-01): '1순위 지역만 모집' 공고의 지역 자격을 원문에서 결정론으로 읽는다(LLM 없이).

- 주택건설지역 + 연접 지역 이름을 지역 표준 이름으로 — 서울이 아닌 지역도(과천시 + 연접 등) 그 목록으로 판정
- 이름 하나라도 모르면 보류(빼고 판정하면 틀린 '불가'), 미모집 문장이 없으면 보류
- 등록 공고 N9·N10을 처음 보는 공고처럼 읽어도 같은 지역(순서 무관)·같은 항목
"""
import sys
from pathlib import Path

import source_verify as sv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import eval_extraction as E  # noqa: E402
import gen_c1_notices as G  # noqa: E402
import sheet_extract as X  # noqa: E402


def test_areas_are_read_from_the_sentence_including_non_seoul():
    s = "해당주택건설지역(과천시)또는연접지역(서울특별시,안양시,의왕시,성남시)이거주지나소득근거지인자"
    assert X.first_rank_areas(s) == ["과천시", "서울특별시", "안양시", "의왕시", "성남시"]
    s2 = "해당주택건설지역(경기도구리시)또는연접지역(서울특별시,경기도남양주시,하남시)이거주지나소득근거지인자"
    assert X.first_rank_areas(s2) == ["구리시", "서울특별시", "남양주시", "하남시"]


def test_unknown_place_name_is_held():
    assert X.first_rank_areas("해당주택건설지역(가상시)또는연접지역(서울특별시)이거주지인자") is None


def test_region_needs_both_first_rank_and_not_recruited_sentences():
    page = "3-1.대학생계층■일반공급…해당주택건설지역(과천시)또는연접지역(서울특별시,안양시)이거주지나재학중인대학소재지인자"
    assert X._region_rules([page], ["대학생"], {"대학생": 1}) is None
    got = X._region_rules([page + "2,3순위이번공고에서는모집하지않음"], ["대학생"], {"대학생": 1})
    assert got["대학생"]["areas"] == ["과천시", "서울특별시", "안양시"]
    assert got["대학생"]["fields"] == ["residence_area", "school_area"]


def test_registered_first_rank_only_notices_read_without_llm():
    E.LOO = True
    try:
        for nid, layers in (("N9", {"대학생"}), ("N10", {"대학생", "청년", "신혼부부", "한부모"})):
            f = X.extract(sv.pdf_pages(nid), E.siblings_for(nid))["fields"]["region"]
            assert f.status == X.FILLED and set(f.value) == layers, nid
            for v in f.value.values():
                assert set(v["areas"]) == set(G.SEOUL_ADJ) and all(sv.normalize(q) for q in v["quote"])
    finally:
        E.LOO = False


def test_region_check_uses_the_notice_areas_and_keeps_registered_rules():
    chk = G.region_check(["residence_area", "income_base_area"], ["과천시", "서울특별시", "안양시"])
    assert chk["any"][0] == {"in": [{"var": "residence_area"}, ["과천시", "서울특별시", "안양시"]]}
    assert "과천시·연접 2개 시 밖" in chk["any"][1]["review_if_true"]["detail"]
    assert G.region_check(["residence_area"]) == G.region_check(["residence_area"], G.SEOUL_ADJ)   # 등록 N9·N10 그대로


def test_weak_layers_of_other_bases_and_tracks_are_read():
    """G1: 대학생 주거약자용(N2)·'세 계층 중 하나 + 주거약자'(N5)도 계층으로 — 고령자 포함 여부는 원문 그대로(N5는 제외 문장)."""
    E.LOO = True
    try:
        n2 = X.extract(sv.pdf_pages("N2"), E.siblings_for("N2"))["fields"]["weak"]
        n5 = X.extract(sv.pdf_pages("N5"), E.siblings_for("N5"))["fields"]["weak"]
    finally:
        E.LOO = False
    assert n2.status == X.FILLED and n2.value["bases"] == ["대학생"] and n2.value["elderly"] is True
    assert n5.status == X.FILLED and n5.value["tracks"] == ["지역전략산업종사자", "청년", "대학생"] and n5.value["elderly"] is False


def test_weak_elderly_needs_explicit_text():
    item = ["…주거약자란1고령자(만65세이상인자)2「장애인복지법」…"]
    excluded = ["…주거약자중고령자(65세이상인사람)는위에표기하지않았습니다."]
    assert X._weak_elderly(item, 1) is True and X._weak_elderly(excluded, 1) is False
    assert X._weak_elderly(["…장애인등주거약자…"], 1) is None
