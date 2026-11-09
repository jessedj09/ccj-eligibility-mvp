# -*- coding: utf-8 -*-
"""test_sh_happy.py — SH 행복주택 판정 틀(N68 2026년 1차 2026.5.28. / N69 2025년 1차 / N70 2025년 3차).

기준은 원문에서 손으로 옮겼다:
- N68 p.21~23·24~32: 소득 1인 4,576,036·2인 6,452,897(맞벌이 7,626,151)·3인 8,168,429, 6인 이상은 5인 + 비율별 1인당
  (100% 579,278원 → 6인 9,906,263), 대학생 자산 10,800만·자동차 불가, 청년 25,100만·4,542만, 신혼·고령자 34,500만,
  한부모 '2019. 5. 29. 이후 출생', 혼인 '7년(2,555일)' — 2019.5.28.~5.30.은 셈법에 따라 갈려 확인 필요
- N69 p.16~18(2024년도 표): 1인 4,317,797, 6인 100% 9,031,048 + 702,038, 청년 25,400만·자동차 3,803만, 신혼 33,700만
- N70 p.26~27: 대학생 10,400만, 자동차 4,563만(출생자녀 2명 5,476만)
"""
import sys
from datetime import date
from pathlib import Path

import draft
import notice_candidates as nc
import source_verify as sv
from rule_data import load_notice, load_reference
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

BASE = dict(profile_id="T", age=25, marital_status="미혼", household_size=1, monthly_income=3_000_000, total_assets=50_000_000,
            car_value=0, home_ownership="무주택", residence_area="부산광역시", children_birth_dates=[],
            has_subscription_account=True, dual_income=False, house_head_status="세대주", student_status="재학중",
            housing_benefit_status="해당없음")
WED = dict(age=32, marital_status="혼인중", marriage_date=date(2024, 1, 1))


def v(nid, layer, **kw):
    return evaluate(HouseholdProfile(**dict(BASE, **kw)), load_notice(nid), layer).verdict


def test_sh_title_goes_to_sh_happy():
    assert X.choose_template("SH", "행복주택") == "sh.happy_housing"
    assert X.choose_template("LH", "행복주택") == "lh.happy_housing"
    assert nc.classify(sv.pdf_pages("N68")) == ("SH", "행복주택")


def test_income_table_adds_per_ratio_above_five():
    ref = load_reference("income_standard_sh_happy")
    assert ref.lookup(1, 120) == 4_576_036 and ref.lookup(5, 110) == 10_259_684
    assert ref.lookup(6, 100) == 9_906_263 and ref.lookup(6, 110) == 10_259_684 + 637_205
    assert ref.lookup(7, 140) == 13_057_779 + 2 * 810_989
    assert ref.lookup(1, 110) is None and ref.lookup(3, 140) is None        # 원문 표의 '-' 칸
    assert load_reference("income_standard_sh_happy_2024").lookup(6, 100) == 9_031_048 + 702_038


def test_n68_boundaries():
    assert v("N68", "대학생", monthly_income=4_576_036) == "ELIGIBLE" and v("N68", "대학생", monthly_income=4_576_037) == "INELIGIBLE"
    assert v("N68", "대학생", total_assets=108_000_001) == "INELIGIBLE" and v("N68", "대학생", car_value=1) == "INELIGIBLE"
    assert v("N68", "청년", household_size=6, monthly_income=9_906_263) == "ELIGIBLE"
    assert v("N68", "청년", household_size=6, monthly_income=9_906_264) == "INELIGIBLE"
    assert v("N68", "청년", total_assets=251_000_001) == "INELIGIBLE" and v("N68", "청년", car_value=45_420_001) == "INELIGIBLE"
    assert v("N68", "신혼부부", household_size=2, dual_income=True, monthly_income=7_626_151, **WED) == "ELIGIBLE"
    assert v("N68", "신혼부부", household_size=2, dual_income=True, monthly_income=7_626_152, **WED) == "INELIGIBLE"
    assert v("N68", "한부모", age=32, marital_status="한부모", household_size=2, children_birth_dates=[date(2019, 5, 29)]) == "ELIGIBLE"
    assert v("N68", "한부모", age=32, marital_status="한부모", household_size=2, children_birth_dates=[date(2019, 5, 28)]) == "INELIGIBLE"
    assert v("N68", "고령자", age=65, monthly_income=4_576_036) == "ELIGIBLE" and v("N68", "고령자", age=64) == "INELIGIBLE"
    assert v("N68", "주거급여수급자", housing_benefit_status="수급자") == "ELIGIBLE"
    assert v("N68", "주거급여수급자") == "INELIGIBLE"


def test_marriage_2555_days_edge_needs_review():
    wed = dict(WED, household_size=2)
    assert v("N68", "신혼부부", **dict(wed, marriage_date=date(2019, 5, 31))) == "ELIGIBLE"
    assert v("N68", "신혼부부", **dict(wed, marriage_date=date(2019, 5, 28))) == "MANUAL_REVIEW"
    assert v("N68", "신혼부부", **dict(wed, marriage_date=date(2019, 5, 27))) == "INELIGIBLE"


def test_2025_notices_use_their_own_money():
    assert v("N69", "청년", monthly_income=4_317_797) == "ELIGIBLE" and v("N69", "청년", monthly_income=4_317_798) == "INELIGIBLE"
    assert v("N69", "청년", car_value=38_030_001) == "INELIGIBLE" and v("N69", "청년", total_assets=254_000_000) == "ELIGIBLE"
    assert v("N69", "신혼부부", household_size=6, monthly_income=9_733_086, **WED) == "ELIGIBLE"
    assert v("N69", "신혼부부", household_size=6, monthly_income=9_733_087, **WED) == "INELIGIBLE"
    assert v("N70", "대학생", total_assets=104_000_001) == "INELIGIBLE" and v("N70", "청년", car_value=45_630_000) == "ELIGIBLE"
    two = [date(2024, 2, 1), date(2025, 2, 1)]
    assert v("N70", "신혼부부", household_size=4, children_birth_dates=two, car_value=54_760_000, total_assets=405_000_000,
             **WED) == "ELIGIBLE"
    assert v("N70", "신혼부부", household_size=4, children_birth_dates=two, total_assets=405_000_001, **WED) == "INELIGIBLE"


def test_extractor_reads_money_and_layers():
    f = X.extract(sv.pdf_pages("N69"))["fields"]
    assert f["layers"].value == ["청년", "신혼부부", "한부모"] and f["extra_layers"].value == ["고령자"]
    assert f["money"].status == X.FILLED and f["money"].value == {
        "income": "2024", "student": None, "youth": [25400, 27900, 30500], "base": [33700, 37100, 40500], "car": [3803, 4183, 4563]}
    f = X.extract(sv.pdf_pages("N70"))["fields"]
    assert f["money"].value["student"] == [10400, 11400, 12500] and f["money"].value["car"] == [4563, 5020, 5476]
    assert f["child"].value == "2019-01-01"


def test_unseen_draft_builds_without_missing_quotes():
    for nid in ("N68", "N69", "N70"):
        d = draft.make_draft(sv.pdf_path(nid).read_bytes(), only=None, pages=sv.pdf_pages(nid), exclude=nid)
        assert d.status == draft.OK and d.template == "sh.happy_housing" and d.missing == [], nid
