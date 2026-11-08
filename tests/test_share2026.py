# -*- coding: utf-8 -*-
"""test_share2026.py — 2026 판 LH 나눔형(이익공유형) 판정 틀(N63 고양창릉 S-3 2026.06.30. 본청약).

2024.3. 개정 뒤 기준: 신생아 특별공급, 맞벌이 200%, 출산가구 +10/+20%p, 2025년도 소득표, 세대 362백만·청년 본인 276백만·부모 1,035백만.
SH 토지임대부(N51·N52)와 같은 기준이라 그 틀을 쓰고 인용문만 LH 표현. 판은 원문 금액 문구로 고른다(N56은 2024 판 그대로).
"""
import json
import sys
from pathlib import Path

import draft
import source_verify as sv
from rule_data import load_notice

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_edition_picked_from_amount_wording():
    assert X._share_sale(sv.pdf_pages("N63"))["edition"].value == "2026"
    assert X._share_sale(sv.pdf_pages("N56"))["edition"].value == "2024"


def test_n63_layers_and_limits_match_sh_land_sale_tables():
    assert list(load_notice("N63").layers) == ["청년", "신혼부부", "생애최초", "신생아", "일반공급"]
    n63 = json.loads((ROOT / "rules" / "notices" / "N63.json").read_text(encoding="utf-8"))
    n51 = json.loads((ROOT / "rules" / "notices" / "N51.json").read_text(encoding="utf-8"))
    for name in ("sh_terms_130", "sh_terms_140", "sh_terms_100", "sh_youth_terms"):
        assert n63["tables"][name]["rows"] == n51["tables"][name]["rows"], name
    assert [u["name"] for u in n63["unsupported_layers"]] == ["사전청약 당첨자"]


def test_n63_unseen_draft_builds_without_missing_quotes():
    d = draft.make_draft(sv.pdf_path("N63").read_bytes(), only=None, pages=sv.pdf_pages("N63"), exclude="N63")
    assert d.status == draft.OK and d.template == "lh.share_sale" and d.missing == []
