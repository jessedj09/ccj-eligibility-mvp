# -*- coding: utf-8 -*-
"""test_c5_housing_weak.py — C5a 주거약자용 주택형.

원문: N1 공릉 p.7·p.8(N7과 같은 문구) / N2 봉천 p.1 "주거약자용주택은 '대학생인 주거약자'에게 우선공급"·p.7 /
N4 하남 p.7 / N7 대방 p.7·p.8 / N8 의왕 p.8 — "신혼부부·한부모가족 계층의 요건을 모두 갖추고 주거약자의 요건을 갖춘 자",
주거약자 = ① 65세 이상 ② 장애인 ③~⑦ 상이 국가유공자 등. N5 부천 p.11 — "지역전략산업종사자, 청년, 대학생 중 하나의
자격요건을 충족하면서 주거약자(장애인 등)" (정의에 고령자 없음). N6 금천·N10 오류 — 고령자 배정 주택형(고령자 판정과 같음).
"""

import copy
import dataclasses
import json
import re

import golden_cases as gc
import pytest
from rule_data import RULES_DIR, load_notice
from rule_engine import HouseholdProfile, evaluate

VARIANTS = [(nid, base) for nid in ("N1", "N4", "N7", "N8") for base in ("신혼부부", "한부모")] + [("N2", "대학생")]


def _doc(nid):
    return json.loads((RULES_DIR / "notices" / f"{nid}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("nid,base", VARIANTS)
def test_variant_layer_is_base_conditions_plus_one_weak_condition(nid, base):
    layers = _doc(nid)["layers"]
    variant = layers[f"{base}(주거약자용)"]["conditions"]
    assert variant[:-1] == layers[base]["conditions"], "기본 계층 조건이 그대로 복사돼야 한다"
    assert variant[-1]["id"] == f"{nid}-W-weak"


def _norm(r):
    return re.sub(r"N\d+-", "X-", json.dumps([r.verdict, r.failed, r.unknown, r.review], ensure_ascii=False))


@pytest.mark.parametrize("nid,base", VARIANTS)
def test_weak_applicant_gets_exactly_the_base_verdict(nid, base):
    """장애인이면 주거약자 조건이 충족이므로, 변형 계층 판정 = 기본 계층 판정(골든의 기본 계층 입력 전부)."""
    notice = load_notice(nid)
    n = 0
    for gnid, layer, p in gc.cases():
        if (gnid, layer) != (nid, base):
            continue
        q = dataclasses.replace(p, housing_weak_type="장애인")
        a, b = evaluate(q, notice, base), evaluate(q, notice, f"{base}(주거약자용)")
        assert f"{nid}-W-weak" in b.matched
        assert _norm(a) == _norm(b), (nid, base, p)
        n += 1
    assert n > 5000


@pytest.mark.parametrize("nid,base", VARIANTS)
def test_non_weak_applicant_is_ineligible_even_if_base_is_eligible(nid, base):
    notice = load_notice(nid)
    checked = 0
    for gnid, layer, p in gc.cases():
        if (gnid, layer) != (nid, base) or evaluate(p, notice, base).verdict != "ELIGIBLE":
            continue
        for weak, age, expect in (("해당없음", 40, "INELIGIBLE"), (None, 40, "NEEDS_INFO"), ("해당없음", 65, "ELIGIBLE")):
            q = dataclasses.replace(p, housing_weak_type=weak, age=age)
            assert evaluate(q, notice, f"{base}(주거약자용)").verdict == expect, (weak, age, p)
        checked += 1
    assert checked > 100


def test_bucheon_weak_layer_needs_one_of_three_layers_and_no_elderly_path():
    notice = load_notice("N5")
    artist = HouseholdProfile("T", 30, "미혼", "무주택", household_size=1, monthly_income=1, total_assets=1, car_value=0,
                              children_birth_dates=[], regional_industry_type="등록 예술인")
    layer = "주거약자(26A1/B1형)"
    r = evaluate(dataclasses.replace(artist, housing_weak_type="장애인"), notice, layer)
    assert r.verdict == "ELIGIBLE" and "지역전략산업종사자" in r.eligible_tracks
    assert evaluate(dataclasses.replace(artist, housing_weak_type="해당없음"), notice, layer).verdict == "INELIGIBLE"
    # 고령자는 부천 주거약자 정의에 없다 — 65세 이상이어도 주거약자 경로가 열리지 않는다
    old = dataclasses.replace(artist, age=70, housing_weak_type="해당없음", student_status="재학중")
    assert evaluate(old, notice, layer).verdict == "INELIGIBLE"
    # 세 계층 중 어느 것에도 맞지 않으면 장애인이어도 불충족(예: 혼인 중 + 종사자 아님)
    none = dataclasses.replace(artist, marital_status="혼인중", regional_industry_type="해당없음", housing_weak_type="장애인")
    assert evaluate(none, notice, layer).verdict == "INELIGIBLE"


@pytest.mark.parametrize("nid", ["N1", "N2", "N4", "N5", "N6", "N7", "N8", "N10"])
def test_housing_weak_units_are_no_longer_unsupported(nid):
    meta = load_notice(nid).meta
    assert not any("주거약자" in u["name"] for u in meta.get("unsupported_layers", []))
