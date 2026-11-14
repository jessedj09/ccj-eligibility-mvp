# -*- coding: utf-8 -*-
"""test_sh_safe.py — SH 청년안심주택(공공임대) 판정 틀(N73 2026년 1차 2026.3.31. / N74 2025년 3차 2025.12.30.).

기준은 원문에서 손으로 옮겼다:
- N73 p.21~24: 공통 19세 이상 39세 이하·무주택. 청년은 미혼(현재 혼인 상태 아님)·1·2·3순위(SH 청년 매입임대와 같은 금액 —
  2순위 본인+부모 34,500만·3순위 25,100만·자동차 4,542만, 1인 4,576,036원)
- N73 p.26~29: 신혼부부Ⅰ 70%(2인 4,693,016 / 배우자 소득 5,866,270), 6인 이상 5인 + 1인당 405,495원, 자산 34,500만·자동차 4,542만,
  혼인 '2019.04.01.~2026.03.31.', 신생아 '2024.04.01.이후'. 신혼부부Ⅱ 130%(2인 8,212,778 / 200% 12,319,167), 자산 36,200만,
  그 밖의 혼인가구(5순위) 포함
- N74 p.28~30: 신혼부부Ⅰ만(Ⅱ 모집 없음), 2024년도 표 2인 4,381,602 / 5,477,003, 6인 + 491,426원, 자산 33,700만·자동차 4,563만,
  혼인 '2018.12.31.~2025.12.30.'
"""
import sys
from datetime import date
from pathlib import Path

import draft
import notice_candidates as nc
import source_verify as sv
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

YOUTH = dict(profile_id="T", age=25, marital_status="미혼", household_size=1, monthly_income=3_000_000, total_assets=50_000_000,
             car_value=0, home_ownership="무주택", children_birth_dates=[], welfare_status="해당없음",
             parent_welfare_status="해당없음", is_supported_single_parent=False, registered_with_parents=True,
             parents_count=2, parents_monthly_income=20_000_000)       # 2순위는 떨어짐 — 3순위 경계만 본다
WED = dict(profile_id="W", age=32, marital_status="혼인중", marriage_date=date(2022, 1, 1), household_size=2,
           monthly_income=3_000_000, dual_income=False, has_children=False, children_birth_dates=[], total_assets=100_000_000,
           car_value=0, home_ownership="무주택", welfare_status="해당없음", is_supported_single_parent=False)


def y(nid, **kw):
    return evaluate(HouseholdProfile(**dict(YOUTH, **kw)), load_notice(nid), "청년").verdict


def w(nid, layer, **kw):
    return evaluate(HouseholdProfile(**dict(WED, **kw)), load_notice(nid), layer).verdict


def test_classified_as_sh_youth_safe():
    assert nc.classify(sv.pdf_pages("N73")) == ("SH", "청년안심주택")
    assert X.choose_template("SH", "청년안심주택") == "sh.youth_safe"
    assert list(load_notice("N73").layers) == ["청년", "신혼부부Ⅰ", "신혼부부Ⅱ"]
    assert list(load_notice("N74").layers) == ["청년", "신혼부부Ⅰ"]          # 2025년 3차는 신혼부부Ⅱ 모집 없음


def test_youth_layer_matches_sh_youth_rental_amounts():
    assert y("N73") == "ELIGIBLE" and y("N73", age=40) == "INELIGIBLE" and y("N73", marital_status="혼인중") == "INELIGIBLE"
    assert y("N73", monthly_income=4_576_036) == "ELIGIBLE" and y("N73", monthly_income=4_576_037) == "INELIGIBLE"
    assert y("N73", total_assets=251_000_001) == "INELIGIBLE" and y("N73", car_value=45_420_001) == "INELIGIBLE"
    assert y("N74", monthly_income=4_317_797) == "ELIGIBLE" and y("N74", monthly_income=4_317_798) == "INELIGIBLE"
    assert y("N74", total_assets=254_000_000) == "ELIGIBLE" and y("N74", total_assets=254_000_001) == "INELIGIBLE"
    assert y("N73", welfare_status="차상위계층", monthly_income=9_000_000) == "ELIGIBLE"          # 1순위


def test_newlywed_one_income_assets_and_age():
    assert w("N73", "신혼부부Ⅰ", monthly_income=4_693_016) == "ELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", monthly_income=4_693_017) == "INELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", dual_income=True, monthly_income=5_866_270) == "ELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", dual_income=True, monthly_income=5_866_271) == "INELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", household_size=6, monthly_income=6_528_890 + 405_495) == "ELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", household_size=6, monthly_income=6_528_890 + 405_496) == "INELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", total_assets=345_000_001) == "INELIGIBLE" and w("N73", "신혼부부Ⅰ", car_value=45_420_001) == "INELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", age=40) == "INELIGIBLE" and w("N73", "신혼부부Ⅰ", age=18) == "INELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", welfare_status="생계·의료·주거급여 수급자", monthly_income=9_000_000) == "ELIGIBLE"   # 검증 면제
    assert w("N73", "신혼부부Ⅰ", household_size=1) == "MANUAL_REVIEW"       # 1인 금액은 원문에 없음


def test_newlywed_types_dates():
    assert w("N73", "신혼부부Ⅰ", marriage_date=date(2019, 4, 1)) == "ELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", marriage_date=date(2019, 3, 31)) == "INELIGIBLE"
    assert w("N73", "신혼부부Ⅱ", marriage_date=date(2019, 3, 31)) == "ELIGIBLE"      # Ⅱ는 그 밖의 혼인가구(5순위)도
    old = dict(marriage_date=date(2010, 1, 1), has_children=True, youngest_child_birth_date=date(2024, 4, 1),
               children_birth_dates=[date(2024, 4, 1)], household_size=3, total_assets=0)
    assert w("N73", "신혼부부Ⅰ", **old) == "ELIGIBLE"                               # 신생아가구(2024.04.01. 이후)
    assert w("N73", "신혼부부Ⅰ", **dict(old, youngest_child_birth_date=date(2019, 3, 31),
                                       children_birth_dates=[date(2019, 3, 31)])) == "INELIGIBLE"
    assert w("N73", "신혼부부Ⅰ", marital_status="예비신혼", marriage_date=None) == "ELIGIBLE"


def test_newlywed_two_and_2025_amounts():
    assert w("N73", "신혼부부Ⅱ", monthly_income=8_212_778, total_assets=362_000_000) == "ELIGIBLE"
    assert w("N73", "신혼부부Ⅱ", monthly_income=8_212_779) == "INELIGIBLE"
    assert w("N73", "신혼부부Ⅱ", dual_income=True, monthly_income=12_319_167) == "ELIGIBLE"
    assert w("N73", "신혼부부Ⅱ", total_assets=362_000_001) == "INELIGIBLE"
    assert w("N74", "신혼부부Ⅰ", monthly_income=4_381_602) == "ELIGIBLE" and w("N74", "신혼부부Ⅰ", monthly_income=4_381_603) == "INELIGIBLE"
    assert w("N74", "신혼부부Ⅰ", household_size=6, monthly_income=6_321_734 + 491_426) == "ELIGIBLE"
    assert w("N74", "신혼부부Ⅰ", total_assets=337_000_001) == "INELIGIBLE" and w("N74", "신혼부부Ⅰ", car_value=45_630_001) == "INELIGIBLE"
    assert w("N74", "신혼부부Ⅰ", marriage_date=date(2018, 12, 31)) == "ELIGIBLE"
    assert w("N74", "신혼부부Ⅰ", marriage_date=date(2018, 12, 30)) == "INELIGIBLE"


def test_extractor_reads_layers_money_dates():
    f = X.extract(sv.pdf_pages("N74"))["fields"]
    assert f["layers"].value == ["청년", "신혼부부Ⅰ"] and f["money"].status == X.FILLED and f["money"].value["nw2"] is None
    assert f["money"].value["nw1"]["adder"] == 491_426 and f["money"].value["nw1"]["cars"] == [4563, 5019, 5475]
    assert {k: v.value for k, v in f["dates"].items()} == {"marriage": "2018-12-31", "newborn": "2023-12-31", "child6": "2018-12-31"}
    f = X.extract(sv.pdf_pages("N73"))["fields"]
    assert f["money"].value["nw2"]["adder_dual"] == 1_158_556 and "cars" not in f["money"].value["nw2"]


def test_private_rental_variant_blocked():
    assert X.variant_notice("sh.youth_safe", ["2026년청년안심주택(민간임대)입주자모집공고"])
    assert X.variant_notice("sh.youth_safe", sv.pdf_pages("N73")) is None


def test_unseen_draft_builds_without_missing_quotes():
    for nid in ("N73", "N74"):
        d = draft.make_draft(sv.pdf_path(nid).read_bytes(), only=None, pages=sv.pdf_pages(nid), exclude=nid)
        assert d.status == draft.OK and d.template == "sh.youth_safe" and d.missing == [] and d.unclassified == [], nid
