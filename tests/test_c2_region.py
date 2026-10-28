# -*- coding: utf-8 -*-
"""test_c2_region.py — 1순위 지역만 모집하는 공고(N9 서울가좌, N10 서울오류)의 지역 요건.

원문(N9 p.6, N10 p.6·p.8·p.10): "1순위 해당 주택건설지역(서울특별시) 또는 연접지역(의정부시, 남양주시, 하남시,
구리시, 성남시, 과천시, 안양시, 광명시, 부천시, 인천광역시, 김포시, 고양시, 양주시)이 거주지나 [재학 중인 대학
소재지 / 소득 근거지]인 자 · 2,3순위 이번 공고에서는 모집하지 않음". 신혼부부는 "신청자 본인 또는 배우자
(예비신혼부부의 경우 대표신청자 또는 예비배우자)가 … 거주지나 소득 근거지인 자".

2026-10-28 결정: **본인 거주지로 판정**한다(소득 근거지·대학 소재지·배우자 지역은 묻지 않는다). 거주지가 목록 안이면 충족,
밖이면 '지원 불가'가 아니라 수동 확인(원문은 다른 지역 항목으로도 신청할 수 있으므로), 거주지를 모르면 정보 부족.
"""

import copy
import dataclasses
import json
import re

import golden_cases as gc
import pytest
from rule_data import RULES_DIR, RuleDataError, build_notice, load_notice
from rule_engine import evaluate, validate_profile

ADJ = ["서울특별시", "의정부시", "남양주시", "하남시", "구리시", "성남시", "과천시", "안양시", "광명시",
       "부천시", "인천광역시", "김포시", "고양시", "양주시"]
REGION_FIELDS = ("residence_area", "school_area", "income_base_area", "spouse_residence_area",
                 "spouse_income_base_area")


def base(nid, layer, **regions):
    """골든 기준 프로필(모든 조건 통과 쪽 기본값)에 지역만 바꾼 프로필."""
    attrs = gc._attributes(layer, gc._pools(nid), nid)
    values = {k: d for k, (_p, d) in attrs.items()}
    values.update({f: None for f in REGION_FIELDS if f in values})
    values.update(regions)
    if layer == "한부모":
        values["kids"] = [gc.AFTER]          # 골든 기준값은 자녀 미입력 — 6세 이하 자녀 1명을 넣어 통과 쪽으로
    p = gc._profile(layer, values, "T")
    return dataclasses.replace(p, **{f: regions.get(f) for f in REGION_FIELDS})


def verdict(nid, layer, **regions):
    return evaluate(base(nid, layer, **regions), load_notice(nid), layer).verdict


def test_baseline_profile_is_eligible_in_seoul():
    for nid, layers in gc.REGION_FIELDS_BY_LAYER.items():
        for layer in layers:
            assert verdict(nid, layer, residence_area="서울특별시") == "ELIGIBLE", (nid, layer)


@pytest.mark.parametrize("area", ADJ)
def test_every_listed_area_passes_by_residence(area):
    assert verdict("N10", "청년", residence_area=area) == "ELIGIBLE"


@pytest.mark.parametrize("area", ["수원시", "의왕시", "시흥시", "부산광역시", "광주광역시", "광주시", "해당없음"])
def test_residence_outside_the_list_is_manual_review_not_ineligible(area):
    # 의왕·시흥은 서울 인접처럼 보이지만 이 공고의 연접지역 목록에 없다. 광주시(경기)·광주광역시도 목록 밖.
    # 원문은 소득 근거지 등으로도 신청할 수 있으므로 거주지만으로 '지원 불가'를 내지 않는다.
    r = evaluate(base("N10", "청년", residence_area=area), load_notice("N10"), "청년")
    assert r.verdict == "MANUAL_REVIEW" and r.review == ["N10-region"]
    assert "소득 근거지(근무지)" in r.review_reasons["N10-region"].detail


@pytest.mark.parametrize("nid,layer", [("N9", "대학생"), ("N10", "대학생"), ("N10", "청년"), ("N10", "신혼부부"),
                                       ("N10", "한부모")])
def test_only_own_residence_is_judged(nid, layer):
    other = dict(school_area="서울특별시", income_base_area="서울특별시", spouse_residence_area="서울특별시",
                 spouse_income_base_area="서울특별시")
    assert verdict(nid, layer, residence_area="서울특별시") == "ELIGIBLE"
    assert verdict(nid, layer, residence_area="수원시", **other) == "MANUAL_REVIEW"   # 다른 지역 항목은 쓰지 않는다
    assert verdict(nid, layer, **other) == "NEEDS_INFO"                              # 거주지 모름
    assert load_notice(nid).layers[layer].inputs & set(REGION_FIELDS) == {"residence_area"}


def test_review_detail_names_the_other_paths_of_each_layer():
    n10 = load_notice("N10")
    detail = lambda layer: evaluate(base("N10", layer, residence_area="수원시"), n10, layer) \
        .review_reasons["N10-region"].detail                                      # noqa: E731
    assert "재학 중인 대학 소재지" in detail("대학생")
    assert "배우자 거주지" in detail("신혼부부") and "배우자" not in detail("한부모")


def test_other_failures_still_outrank_region_review():
    p = dataclasses.replace(base("N10", "청년", residence_area="부산광역시"), monthly_income=None)
    r = evaluate(p, load_notice("N10"), "청년")
    assert r.verdict == "MANUAL_REVIEW" and "N10-region" in r.review               # 수동 확인 > 정보 부족
    p = dataclasses.replace(base("N10", "청년", residence_area="부산광역시"), home_ownership="주택보유")
    assert evaluate(p, load_notice("N10"), "청년").verdict == "INELIGIBLE"         # 불충족 > 수동 확인


def test_same_verdicts_as_geumcheon_when_in_seoul():
    """N10(서울오류)과 N6(서울금천)은 같은 날(2026.5.15) 공고된 같은 템플릿이다. 지역이 서울이면 지역 조건을 뺀
    나머지 판정이 같아야 한다. N6 골든의 체계적 입력을 그대로 써서 비교한다."""
    n6, n10 = load_notice("N6"), load_notice("N10")
    compared = 0
    region_layers = gc.REGION_FIELDS_BY_LAYER["N10"]       # 지역 조건이 있는 계층만(고령자 등은 지역 요건 없음)
    for nid, layer, p in gc.cases(only=[("N6", lay) for lay in region_layers]):
        if nid != "N6" or layer not in region_layers:
            continue
        q = dataclasses.replace(p, residence_area="서울특별시")
        a, b = evaluate(p, n6, layer), evaluate(q, n10, layer)
        norm = lambda r: re.sub(r"N\d+-", "X-", json.dumps(
            [r.verdict, r.failed, r.unknown, r.review], ensure_ascii=False))
        b_failed = [c for c in b.failed if c != "N10-region"]
        assert "N10-region" in b.matched, (layer, q)
        assert norm(a) == norm(dataclasses.replace(b, failed=b_failed)), (layer, p)
        compared += 1
    assert compared > 20_000


def test_loader_rejects_misspelled_region_and_validation_rejects_unknown_area():
    doc = json.loads((RULES_DIR / "notices" / "N10.json").read_text(encoding="utf-8"))
    bad = copy.deepcopy(doc)
    region = bad["layers"]["청년"]["conditions"][-1]
    region["check"]["any"][0]["in"][1] = ["서울시"]            # 표준 이름은 '서울특별시'
    with pytest.raises(RuleDataError):
        build_notice(bad)
    assert validate_profile(base("N10", "청년", residence_area="서울시"))
    assert not validate_profile(base("N10", "청년", residence_area="서울특별시"))
    assert not validate_profile(base("N10", "청년", residence_area="해당없음"))


def test_region_inputs_only_where_needed():
    assert not set(REGION_FIELDS) & load_notice("N3").layers["청년"].inputs
