# -*- coding: utf-8 -*-
"""test_sh_youth.py — SH 청년 매입임대 판정 틀(N71 2026년 1차 2026.6.26. / N72 2025년 2차 2025.12.26.).

기준은 원문에서 손으로 옮겼다:
- N71 p.22·28: 유형 청년(19~39세)·대학생(서울 소재 대학)·취업준비생(졸업·중퇴 2년 이내, 미재직)·이공계인재(판정 안 함),
  미혼 = 현재 혼인 상태가 아님(기혼자 불가), 1순위 수급자·차상위·지원대상 한부모 또는 같은 등본의 부모가 수급자·차상위,
  2순위 본인+부모 소득 1인 4,576,036·2인 6,452,897·3인 8,168,429원, 총자산 34,500만·자동차 4,542만,
  3순위 본인 4,576,036원·총자산 25,100만·자동차 4,542만
- N72 p.23·25: 2024년도 표 1인 4,317,797·2인 6,024,703·3인 7,626,973원, 2순위 총자산 33,700만·3순위 25,400만·자동차 4,563만,
  이공계인재 유형 없음
"""
import json
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

# 3순위로 통과하는 기본 프로필(본인 소득·자산 낮음, 부모 정보 없음)
BASE = dict(profile_id="T", age=25, marital_status="미혼", household_size=1, monthly_income=3_000_000, total_assets=50_000_000,
            car_value=0, home_ownership="무주택", children_birth_dates=[], student_status="재학중", school_area="서울특별시",
            welfare_status="해당없음", parent_welfare_status="해당없음", is_supported_single_parent=False,
            registered_with_parents=True, is_employed=False, grad_or_dropout_date=date(2026, 2, 20))
PARENTS = dict(parents_count=2, parents_monthly_income=0, parents_total_assets=0, parents_car_value=0)
OVER3 = dict(monthly_income=5_000_000)          # 3순위(본인 1인 기준)는 넘는다 — 2순위 경계만 본다
NO_RANK2 = dict(parents_count=2, parents_monthly_income=20_000_000)       # 2순위는 떨어짐 — 3순위 경계만 본다


def v(nid, layer, **kw):
    return evaluate(HouseholdProfile(**dict(BASE, **kw)), load_notice(nid), layer).verdict


def test_sh_title_goes_to_sh_youth():
    assert X.choose_template("SH", "청년매입임대") == "sh.youth_rental"
    assert X.choose_template("LH", "청년매입임대") == "lh.youth_rental"
    assert nc.classify(sv.pdf_pages("N71")) == ("SH", "청년매입임대")


def test_common_marital_and_age():
    assert v("N71", "청년") == "ELIGIBLE"
    assert v("N71", "청년", marital_status="혼인중") == "INELIGIBLE"
    assert v("N71", "청년", marital_status="한부모") == "ELIGIBLE" and v("N71", "청년", marital_status="예비신혼") == "ELIGIBLE"
    assert v("N71", "청년", home_ownership="주택보유") == "INELIGIBLE"
    assert v("N71", "청년", age=39) == "ELIGIBLE" and v("N71", "청년", age=40) == "INELIGIBLE"
    assert v("N71", "청년", age=18) == "INELIGIBLE"
    assert v("N71", "대학생", age=45) == "ELIGIBLE"           # 대학생·취업준비생은 나이 기준 없음


def test_student_must_attend_seoul_university():
    assert v("N71", "대학생", school_area="고양시") == "INELIGIBLE"
    assert v("N71", "대학생", school_area=None) == "NEEDS_INFO"
    assert v("N71", "대학생", student_status="입학예정") == "ELIGIBLE"


def test_job_seeker_within_two_years():
    assert v("N71", "취업준비생", grad_or_dropout_date=date(2024, 6, 26)) == "ELIGIBLE"
    assert v("N71", "취업준비생", grad_or_dropout_date=date(2024, 6, 25)) == "INELIGIBLE"
    assert v("N71", "취업준비생", is_employed=True) == "INELIGIBLE"
    assert v("N72", "취업준비생", grad_or_dropout_date=date(2023, 12, 26)) == "ELIGIBLE"


def test_rank1_welfare_and_parents_on_same_register():
    rich = dict(NO_RANK2, monthly_income=20_000_000, total_assets=900_000_000)     # 2·3순위는 떨어짐 — 1순위로만 통과
    assert v("N71", "청년", **rich) == "INELIGIBLE"
    assert v("N71", "청년", **dict(rich, welfare_status="차상위계층")) == "ELIGIBLE"
    assert v("N71", "청년", **dict(rich, is_supported_single_parent=True)) == "ELIGIBLE"
    parent = dict(rich, parent_welfare_status="생계·의료·주거급여 수급자")
    assert v("N71", "청년", **dict(parent, registered_with_parents=True)) == "ELIGIBLE"
    assert v("N71", "청년", **dict(parent, registered_with_parents=False)) == "INELIGIBLE"
    assert v("N71", "청년", **dict(rich, welfare_status="교육급여만 수급")) == "INELIGIBLE"


def test_rank3_own_income_assets_car_boundaries():
    assert v("N71", "청년", monthly_income=4_576_036, **NO_RANK2) == "ELIGIBLE"
    assert v("N71", "청년", monthly_income=4_576_037, **NO_RANK2) == "INELIGIBLE"
    assert v("N71", "청년", total_assets=251_000_000, **NO_RANK2) == "ELIGIBLE"
    assert v("N71", "청년", total_assets=251_000_001, **NO_RANK2) == "INELIGIBLE"
    assert v("N71", "청년", car_value=45_420_000, **NO_RANK2) == "ELIGIBLE"
    assert v("N71", "청년", car_value=45_420_001, **NO_RANK2) == "INELIGIBLE"
    assert v("N72", "청년", monthly_income=4_317_797, **NO_RANK2) == "ELIGIBLE"
    assert v("N72", "청년", monthly_income=4_317_798, **NO_RANK2) == "INELIGIBLE"
    assert v("N72", "청년", total_assets=254_000_000, **NO_RANK2) == "ELIGIBLE"
    assert v("N72", "청년", total_assets=254_000_001, **NO_RANK2) == "INELIGIBLE"
    assert v("N72", "청년", car_value=45_630_000, **NO_RANK2) == "ELIGIBLE"
    assert v("N72", "청년", car_value=45_630_001, **NO_RANK2) == "INELIGIBLE"


def test_rank2_parents_sum_by_size():
    def p(**kw):
        return dict(PARENTS, **OVER3, **kw)
    assert v("N71", "청년", **p(parents_monthly_income=8_168_429 - 5_000_000)) == "ELIGIBLE"
    assert v("N71", "청년", **p(parents_monthly_income=8_168_430 - 5_000_000)) == "INELIGIBLE"
    assert v("N71", "청년", **p(parents_count=1, parents_monthly_income=6_452_897 - 5_000_000)) == "ELIGIBLE"
    assert v("N71", "청년", **p(parents_count=1, parents_monthly_income=6_452_898 - 5_000_000)) == "INELIGIBLE"
    assert v("N72", "청년", **p(parents_monthly_income=7_626_973 - 5_000_000)) == "ELIGIBLE"
    assert v("N72", "청년", **p(parents_monthly_income=7_626_974 - 5_000_000)) == "INELIGIBLE"
    # 2순위 자산은 본인+부모 합계, 자동차는 가장 비싼 한 대
    assert v("N71", "청년", **p(parents_total_assets=345_000_000 - 50_000_000)) == "ELIGIBLE"
    assert v("N71", "청년", **p(parents_total_assets=345_000_001 - 50_000_000)) == "INELIGIBLE"
    assert v("N72", "청년", **p(parents_total_assets=337_000_001 - 50_000_000)) == "INELIGIBLE"
    assert v("N71", "청년", **p(parents_car_value=45_420_001)) == "INELIGIBLE"


def test_unsupported_scientist_only_in_2026():
    def raw(nid):
        return json.loads((Path(__file__).resolve().parent.parent / "rules" / "notices" / f"{nid}.json").read_text(encoding="utf-8"))
    assert [u["name"] for u in raw("N71").get("unsupported_layers", [])] == ["이공계인재"]
    assert not raw("N72").get("unsupported_layers")


def test_extractor_reads_money_and_age_quote():
    f = X.extract(sv.pdf_pages("N71"))["fields"]
    assert f["money"].status == X.FILLED and f["money"].value == {"income": "2025", "assets2": 34500, "assets3": 25100, "car": 4542}
    assert f["age_quote"].value == "청년만19세이상~만39세이하인자"
    f = X.extract(sv.pdf_pages("N72"))["fields"]
    assert f["money"].value == {"income": "2024", "assets2": 33700, "assets3": 25400, "car": 4563}
    assert f["age_quote"].value == "청년만19세이상~39세이하인자"


def test_unseen_draft_builds_without_missing_quotes():
    for nid in ("N71", "N72"):
        d = draft.make_draft(sv.pdf_path(nid).read_bytes(), only=None, pages=sv.pdf_pages(nid), exclude=nid)
        assert d.status == draft.OK and d.template == "sh.youth_rental" and d.missing == [], nid
