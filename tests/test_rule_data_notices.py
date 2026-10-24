# -*- coding: utf-8 -*-
"""test_rule_data_notices.py — 공고 데이터 파일(rules/notices/*.json)의 메타데이터·구조·컷오프 경계 검증.
(결과 전체의 회귀는 test_rules_golden.py, 연산자 의미는 test_rule_data.py가 맡는다.)"""

import hashlib
from datetime import date, timedelta
from pathlib import Path

import pytest
from rule_engine import HouseholdProfile, evaluate
from rule_data import load_notice
from notices_data import (
    ALL_NOTICES, N1, N2, N3, N1_MARRIAGE_CUTOFF, N1_CHILD_CUTOFF, N3_MARRIAGE_CUTOFF, N3_CHILD_CUTOFF,
)

PROJECT = Path(__file__).resolve().parent.parent
PDF_GLOB = {"N1": "*공릉*.pdf", "N2": "*관악봉천*.pdf", "N3": "*번동3*.pdf"}
EXPECTED = {
    # 주거약자용 주택형 계층은 E1(2026-10-24)에서 추가 — tools/gen_c5_housing_weak.py
    "N1": ("서울공릉 신혼희망타운 행복주택", date(2026, 7, 29), {"신혼부부", "한부모", "신혼부부(주거약자용)", "한부모(주거약자용)"}),
    "N2": ("서울관악봉천 행복주택 예비입주자모집", date(2026, 7, 15), {"대학생", "대학생(주거약자용)"}),
    "N3": ("서울번동3 행복주택", date(2026, 8, 19), {"대학생", "청년", "신혼부부", "한부모"}),
}


@pytest.mark.parametrize("nid", ["N1", "N2", "N3"])
def test_notice_meta_layers_and_source_hash(nid):
    notice = load_notice(nid)
    title, ann, layers = EXPECTED[nid]
    assert (notice.title, notice.announcement_date, set(notice.layers)) == (title, ann, layers)
    assert notice.meta["review"]["status"] == "DRAFT"       # 독립 검토 전 — REVIEWED로 올리려면 검증 워크시트 필요
    pdf = next((PROJECT / "sample_lh").glob(PDF_GLOB[nid]))
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == notice.meta["source"]["sha256"]


def test_shim_exports_the_loaded_notices():
    assert {"N1": N1, "N2": N2, "N3": N3}.items() <= ALL_NOTICES.items()
    assert N1 is load_notice("N1")


def test_only_the_subscription_account_condition_is_deferred_to_move_in():
    for nid, notice in ALL_NOTICES.items():
        for layer, ruleset in notice.layers.items():
            deferred = [c.rule_id for c in ruleset.conditions if c.timing == "BEFORE_MOVE_IN"]
            # 청약통장 요건이 없는 계층: 대학생(N2·N3 p.5), 고령자(금천 p.13 등), 주거급여수급자(오류 p.12).
            # 행복주택이 아닌 사업(매입임대·든든전세, C4)은 청약통장이 배점에만 쓰이고 자격요건이 아니다(LH01·LH06 p.4).
            if any(c.tracks for c in ruleset.conditions) and layer.startswith("주거약자"):
                continue   # 부천 주거약자(26A1/B1형): 청약통장 조건은 계층별 트랙 안에 있다(트랙마다 원 계층 그대로)
            base = layer.split("(")[0]          # 주거약자용 변형 계층은 기본 계층과 같다
            no_subscription = (base in ("대학생", "고령자", "주거급여수급자")
                               or not notice.meta.get("program", "행복주택").startswith("행복주택"))
            assert len(deferred) == (0 if no_subscription else 1), (nid, layer, deferred)
            assert all(c.rule_id.endswith(("-sub", "R10")) for c in ruleset.conditions
                       if c.timing == "BEFORE_MOVE_IN")


def _married(marriage):
    return HouseholdProfile("D", 33, "혼인중", "무주택", household_size=3, monthly_income=1, total_assets=1,
                            car_value=0, marriage_date=marriage, has_children=False)


def _single_parent(child):
    return HouseholdProfile("D", 38, "한부모", "무주택", household_size=2, monthly_income=1, total_assets=1,
                            car_value=0, has_children=True, youngest_child_birth_date=child)


@pytest.mark.parametrize("nid,marriage_cut,child_cut", [
    ("N1", N1_MARRIAGE_CUTOFF, N1_CHILD_CUTOFF),     # 원문 p.5 리터럴
    ("N3", N3_MARRIAGE_CUTOFF, N3_CHILD_CUTOFF),     # 같은 공식으로 공고일에서 도출
])
def test_cutoff_boundaries_in_data_rules(nid, marriage_cut, child_cut):
    notice = load_notice(nid)
    one = timedelta(days=1)
    assert f"{nid}-M-duration" in evaluate(_married(marriage_cut), notice, "신혼부부").matched
    assert f"{nid}-M-duration" in evaluate(_married(marriage_cut - one), notice, "신혼부부").failed
    assert f"{nid}-S-child6" in evaluate(_single_parent(child_cut), notice, "한부모").matched
    assert f"{nid}-S-child6" in evaluate(_single_parent(child_cut - one), notice, "한부모").failed


def test_cutoff_constants_are_hand_checked_literals():
    assert (N1_MARRIAGE_CUTOFF, N1_CHILD_CUTOFF) == (date(2019, 7, 29), date(2019, 7, 30))
    assert (N3_MARRIAGE_CUTOFF, N3_CHILD_CUTOFF) == (date(2019, 8, 19), date(2019, 8, 20))
