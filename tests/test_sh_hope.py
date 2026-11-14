# -*- coding: utf-8 -*-
"""test_sh_hope.py — SH 희망하우징(공공기숙사) 판정 틀(N75 2026년 2차 2026.9.17.).

기준은 원문에서 손으로 옮겼다(N75 p.6~9): 무주택자(본인)·미혼(현재 혼인 상태 아님)·서울특별시 소재 대학교(전문대 포함) 재학생
(다음 학기 입학·복학 예정 포함), 나이 기준 없음. 1순위 수급자·지원대상 한부모·차상위(본인 또는 같은 등본의 부모), 2순위 본인+부모
100%(1인 4,576,036·2인 6,452,897·3인 8,168,429원)·총자산 34,500만·자동차 4,542만, 3순위 본인 4,576,036원·총자산 10,800만·자동차 무소유.
2026년 3차 잔여세대(2026.10.28.)는 단지마다 대학 요건이 달라(내발산: 서울 주민등록 + 수도권 대학·대학원생) 자동 판정하지 않는다.
"""
import sys
from pathlib import Path

import draft
import notice_candidates as nc
import source_verify as sv
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sheet_extract as X  # noqa: E402

B = dict(profile_id="T", age=22, marital_status="미혼", household_size=1, monthly_income=1_000_000, total_assets=10_000_000,
         car_value=0, home_ownership="무주택", children_birth_dates=[], student_status="재학중", school_area="서울특별시",
         welfare_status="해당없음", parent_welfare_status="해당없음", is_supported_single_parent=False, registered_with_parents=True,
         parents_count=2, parents_monthly_income=20_000_000)          # 2순위는 떨어짐 — 3순위 경계만 본다
THIRD = ROOT / "sample_sh" / "2026년 3차 희망하우징(공공기숙사) 잔여세대 입주자 모집공고(2026_ 10_ 28_).pdf"


def v(**kw):
    return evaluate(HouseholdProfile(**dict(B, **kw)), load_notice("N75"), "대학생").verdict


def test_classified_as_hope_housing_not_national_rental():
    assert nc.classify(sv.pdf_pages("N75")) == ("SH", "희망하우징")          # 2026-11-14 전에는 '국민임대주택'으로 잘못 분류
    assert X.choose_template("SH", "희망하우징") == "sh.hope_housing"
    assert list(load_notice("N75").layers) == ["대학생"]


def test_student_scope_and_common():
    assert v() == "ELIGIBLE" and v(age=45) == "ELIGIBLE"                   # 나이 기준 없음
    assert v(school_area="고양시") == "INELIGIBLE" and v(student_status="해당없음") == "INELIGIBLE"
    assert v(student_status="복학예정") == "ELIGIBLE"
    assert v(marital_status="혼인중") == "INELIGIBLE" and v(home_ownership="주택보유") == "INELIGIBLE"


def test_rank3_assets_and_no_car():
    assert v(total_assets=108_000_000) == "ELIGIBLE" and v(total_assets=108_000_001) == "INELIGIBLE"
    assert v(car_value=1) == "INELIGIBLE"                                 # 3순위는 자동차 무소유
    assert v(monthly_income=4_576_036) == "ELIGIBLE" and v(monthly_income=4_576_037) == "INELIGIBLE"


def test_rank2_allows_car_with_parents():
    p = dict(parents_monthly_income=0, parents_total_assets=0, parents_car_value=0, monthly_income=5_000_000)
    assert v(**dict(p, car_value=45_420_000)) == "ELIGIBLE"
    assert v(**dict(p, car_value=45_420_001)) == "INELIGIBLE"
    assert v(**dict(p, parents_monthly_income=8_168_430 - 5_000_000)) == "INELIGIBLE"
    assert v(welfare_status="차상위계층", monthly_income=9_000_000, total_assets=900_000_000) == "ELIGIBLE"     # 1순위


def test_extractor_reads_money_and_blocks_other_scope():
    f = X.extract(sv.pdf_pages("N75"))["fields"]
    assert f["money"].status == X.FILLED and f["money"].value == {"income": "2025", "assets2": 34500, "assets3": 10800,
                                                                  "car": 4542, "car3": 0}
    f = X.extract(sv.extract_pages(THIRD))["fields"]
    assert f["money"].status == X.HELD and "수도권" in f["money"].how


def test_unseen_draft_builds_without_missing_quotes():
    d = draft.make_draft(sv.pdf_path("N75").read_bytes(), only=None, pages=sv.pdf_pages("N75"), exclude="N75")
    assert d.status == draft.OK and d.template == "sh.hope_housing" and d.missing == []
