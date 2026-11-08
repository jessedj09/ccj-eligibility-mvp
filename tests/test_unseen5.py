# -*- coding: utf-8 -*-
"""test_unseen5.py — 처음 보는 실공고 5건 검증(2026-11-08, 초안은 docs/draft-checks/Z-*.draft.json)에서 보강한 판정 틀.

- N58 인제서화 국민임대: 자산·자동차 한도가 원 단위 한 표(p.5 "총자산가액(원)자동차가액(원)") — 금액은 표준과 같다.
"""
import json
import sys
from pathlib import Path

import draft
import source_verify as sv
from rule_data import load_notice

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import gen_c6_public as G  # noqa: E402
import sheet_extract as X  # noqa: E402


def test_national_money_style_detected():
    assert X._national_rental(sv.pdf_pages("N58"))["money"].value == "won"
    for nid in ("N30", "N31", "N32"):
        assert X._national_rental(sv.pdf_pages(nid))["money"].value == "million"


def test_national_money_styles_same_limits():
    _, million = G.national_rental("NX", money="million")
    _, won = G.national_rental("NX", money="won")
    assert million["national_terms"]["rows"] == won["national_terms"]["rows"]   # 표기만 다르고 한도는 같다


def test_n58_unseen_draft_has_no_held_conditions():
    d = draft.make_draft(sv.pdf_path("N58").read_bytes(), only=None, pages=sv.pdf_pages("N58"), exclude="N58")
    assert d.status == draft.OK and d.missing == [] and d.held_conditions == {"일반": set()}


def test_n58_registered_layers():
    n = load_notice("N58")
    assert list(n.layers) == ["일반"]


def test_n59_integrated_layers_and_elderly_weak_type_unsupported():
    n = load_notice("N59")
    assert list(n.layers) == ["청년", "신혼부부", "한부모", "고령자", "일반"]
    assert [u["name"] for u in n.meta["unsupported_layers"]] == ["주거약자용주택(31AS형)"]
    d = draft.make_draft(sv.pdf_path("N59").read_bytes(), only=None, pages=sv.pdf_pages("N59"), exclude="N59")
    assert d.status == draft.OK and d.template == "lh.integrated_rental" and d.missing == []


def test_sh_national_edition_picked_from_asset_table():
    assert X._sh_national_rental(sv.pdf_pages("N60"))["edition"].value == "2025"
    assert X._sh_national_rental(sv.pdf_pages("N53"))["edition"].value == "2026"
    assert X._sh_national_rental(["자산기준(단위:만원)기본35,0004,600"])["edition"].value == "2026"   # 모르는 판 → 기본(보류됨)


def test_n60_uses_2024_income_table_and_2025_limits():
    n = load_notice("N60")
    doc = json.loads((Path(__file__).resolve().parent.parent / "rules" / "notices" / "N60.json").read_text(encoding="utf-8"))
    assert "income_standard_sh_public_2024" in json.dumps(doc["layers"], ensure_ascii=False)
    rows = doc["tables"]["sh_national_terms"]["rows"]
    assert rows[0]["out"] == [90, 337_000_000, 38_030_000]
    assert list(n.layers) == ["일반", "일반(주거약자용)"]


def test_n60_unseen_draft_has_no_held_conditions():
    d = draft.make_draft(sv.pdf_path("N60").read_bytes(), only=None, pages=sv.pdf_pages("N60"), exclude="N60")
    assert d.status == draft.OK and d.missing == [] and d.stale == []
    assert d.held_conditions == {"일반": set(), "일반(주거약자용)": set()}
