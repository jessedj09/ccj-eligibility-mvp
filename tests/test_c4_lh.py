# -*- coding: utf-8 -*-
"""test_c4_lh.py — C4a: LH 청년매입임대(N11·N12)·신혼·신생아 매입임대(N13~N15)·든든전세(N16·N17).

기준값은 원문에서 손으로 옮겼다(엔진 출력을 복사하지 않음):
- 청년매입(LH06 p.3): 2순위 본인+부모 소득 (1인) 4,576,036 (2인) 6,452,897 (3인) 8,168,429원, 자산 34,500만·자동차 4,542만.
  3순위 본인 소득 4,576,036원, 자산 25,100만·자동차 4,542만. 30세 미만 = 1996.06.26. 이후 출생.
- 신혼·신생아Ⅰ(LH01 p.3~4): 혼인신고 2019.6.25.~, 6세 이하 '19.6.26 이후, 신생아 '24.6.25 이후.
  70% 열 1인 3,432,027 / 2인 4,693,016 / 3인 5,717,900, 90% 열 3인 7,351,586. 자산 345/379/413M, 자동차 45.42/49.96/54.51M.
- 신혼·신생아Ⅱ(LH02 p.4): 130% 열 3인 10,618,958, 200% 열 3인 16,336,858. 자산 362/396/431M, 자동차 기준 없음.
- 신혼·신생아Ⅰ 3차(LH03 p.3): 혼인신고 2019.9.17~, 6세 '19.9.18 이후, 신생아 '24.9.17 이후.
- 든든전세(LH04 p.3·4): 무주택세대구성원, 수도권(서울·인천·경기) 거주, 미성년자(19세 미만) 원칙적 불가. 소득·자산 요건 없음.
"""

from datetime import date

import pytest
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

KID_NEW = date(2025, 1, 1)


def run(nid, layer, **kw):
    base = dict(profile_id="T", age=25, marital_status="미혼", home_ownership="무주택", household_size=1,
                monthly_income=1_000_000, total_assets=10_000_000, car_value=0, children_birth_dates=[],
                welfare_status="해당없음", parent_welfare_status="해당없음", is_supported_single_parent=False,
                registered_with_parents=True, parents_count=2, parents_monthly_income=1_000_000,
                parents_total_assets=10_000_000, parents_car_value=0)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), layer)


def v(*a, **kw):
    return run(*a, **kw).verdict


def codes(r):
    return {x.code for x in r.review_reasons.values()}


# 3순위를 막는 설정(본인 자산 2억6천만 > 2억5,100만) — 2순위만 따로 시험할 때
NO_RANK3 = dict(total_assets=260_000_000, parents_total_assets=85_000_000)


# --- 청년매입임대 -------------------------------------------------------------------------------
@pytest.mark.parametrize("nid", ["N11", "N12"])
def test_youth_rank3_own_income_boundary(nid):
    kw = dict(parents_monthly_income=50_000_000)              # 2순위는 확실히 불충족
    assert run(nid, "청년", monthly_income=4_576_036, **kw).eligible_tracks == ["3순위"]
    assert v(nid, "청년", monthly_income=4_576_037, **kw) == "INELIGIBLE"
    assert v(nid, "청년", total_assets=251_000_001, **kw) == "INELIGIBLE"
    assert v(nid, "청년", car_value=45_420_001, **kw) == "INELIGIBLE"


@pytest.mark.parametrize("parents,limit", [(0, 4_576_036), (1, 6_452_897), (2, 8_168_429)])
def test_youth_rank2_combined_income_by_household_size(parents, limit):
    own = 1_000_000
    kw = dict(NO_RANK3, parents_count=parents, monthly_income=own)
    assert run("N11", "청년", **kw, parents_monthly_income=limit - own).eligible_tracks == ["2순위"]
    assert v("N11", "청년", **kw, parents_monthly_income=limit - own + 1) == "INELIGIBLE"


def test_youth_rank2_assets_and_highest_car():
    assert run("N11", "청년", **NO_RANK3).eligible_tracks == ["2순위"]                # 260M + 85M = 345M
    assert v("N11", "청년", total_assets=260_000_000, parents_total_assets=85_000_001) == "INELIGIBLE"
    assert v("N11", "청년", **NO_RANK3, parents_car_value=45_420_001) == "INELIGIBLE"  # 가장 높은 차량가액
    assert v("N11", "청년", **NO_RANK3, parents_monthly_income=None) == "NEEDS_INFO"   # 부모 소득 모름


@pytest.mark.parametrize("kw,verdict", [
    (dict(welfare_status="생계·의료·주거급여 수급자"), "ELIGIBLE"),
    (dict(welfare_status="차상위계층"), "ELIGIBLE"),
    (dict(welfare_status="교육급여만 수급"), "INELIGIBLE"),                  # 1순위는 생계·의료·주거급여만(p.3)
    (dict(is_supported_single_parent=True), "ELIGIBLE"),
    (dict(parent_welfare_status="생계·의료·주거급여 수급자", registered_with_parents=True, age=35), "ELIGIBLE"),
    (dict(parent_welfare_status="차상위계층", registered_with_parents=False, age=29), "ELIGIBLE"),  # 30세 미만 분리 거주
    (dict(parent_welfare_status="차상위계층", registered_with_parents=False, age=30), "INELIGIBLE"),
])
def test_youth_rank1_welfare_paths_ignore_income(kw, verdict):
    rich = dict(monthly_income=50_000_000, total_assets=900_000_000, parents_monthly_income=50_000_000)
    r = run("N11", "청년", **{**rich, **kw})
    assert r.verdict == verdict
    if verdict == "ELIGIBLE":
        assert r.eligible_tracks == ["1순위"]


def test_youth_types_are_exclusive_by_age():
    assert v("N11", "대학생", student_status="재학중", age=25) == "INELIGIBLE"    # 19~39세는 청년으로 신청
    assert v("N11", "대학생", student_status="재학중", age=18) == "ELIGIBLE"
    assert v("N11", "청년", age=40) == "INELIGIBLE"
    assert v("N11", "청년", age=19) == "ELIGIBLE"


def test_job_seeker_graduation_within_two_years_and_unemployed():
    kw = dict(age=40, is_employed=False)
    assert v("N11", "취업준비생", **kw, grad_or_dropout_date=date(2024, 6, 25)) == "ELIGIBLE"
    assert v("N11", "취업준비생", **kw, grad_or_dropout_date=date(2024, 6, 24)) == "INELIGIBLE"
    assert v("N11", "취업준비생", age=40, is_employed=True, grad_or_dropout_date=date(2025, 1, 1)) == "INELIGIBLE"


def test_youth_marital_and_home():
    r = run("N11", "청년", marital_status="한부모")
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {"AMBIGUOUS_SOURCE"}
    assert v("N11", "청년", marital_status="혼인중") == "INELIGIBLE"
    assert v("N11", "청년", home_ownership="주택보유") == "INELIGIBLE"


def test_youth_unknown_ranks_mean_needs_info_not_ineligible():
    # 3순위 불충족이 확정이어도 1·2순위 정보가 없으면 정보 부족(다른 순위로 될 수 있으므로)
    r = run("N11", "청년", monthly_income=9_000_000, welfare_status=None, parent_welfare_status=None,
            is_supported_single_parent=None, parents_monthly_income=None)
    assert r.verdict == "NEEDS_INFO" and r.tracks["3순위"].verdict == "INELIGIBLE"


# --- 신혼·신생아 매입임대 -----------------------------------------------------------------------
NW = "신혼·신생아"


@pytest.mark.parametrize("nid,marriage,child6,newborn", [
    ("N13", date(2019, 6, 25), date(2019, 6, 26), date(2024, 6, 25)),
    ("N14", date(2019, 9, 17), date(2019, 9, 18), date(2024, 9, 17)),
    ("N15", date(2019, 6, 25), date(2019, 6, 26), date(2024, 6, 25)),
])
def test_newlywed_rental_type_cutoffs(nid, marriage, child6, newborn):
    from datetime import timedelta
    day = timedelta(days=1)
    married = dict(marital_status="혼인중", household_size=2)
    assert "①신혼부부" in run(nid, NW, **married, marriage_date=marriage).eligible_tracks
    assert "①신혼부부" not in run(nid, NW, **married, marriage_date=marriage - day).eligible_tracks
    kids = lambda d: dict(children_birth_dates=[d], household_size=2)
    assert "③-1한부모가족" in run(nid, NW, marital_status="한부모", **kids(child6)).eligible_tracks
    assert "③-1한부모가족" not in run(nid, NW, marital_status="한부모", **kids(child6 - day)).eligible_tracks
    assert "⑤신생아가구" in run(nid, NW, **kids(newborn)).eligible_tracks                  # 미혼도 가능
    assert "⑤신생아가구" not in run(nid, NW, **kids(newborn - day)).eligible_tracks


def test_newlywed_rental_I_has_no_plain_married_type_but_II_does():
    kw = dict(marital_status="혼인중", household_size=2, marriage_date=date(2010, 1, 1))   # 혼인 7년 초과, 자녀 없음
    assert v("N13", NW, **kw) == "INELIGIBLE"
    assert run("N15", NW, **kw).eligible_tracks == ["⑥혼인가구"]


@pytest.mark.parametrize("size,dual,limit", [(1, False, 3_432_027), (2, False, 4_693_016), (3, False, 5_717_900),
                                             (3, True, 7_351_586), (2, True, 5_866_270), (6, False, 6_934_384)])
def test_newlywed_rental_I_income(size, dual, limit):
    kw = dict(marital_status="혼인중", marriage_date=date(2024, 1, 1), household_size=size, dual_income=dual)
    assert v("N13", NW, **kw, monthly_income=limit) == "ELIGIBLE"
    assert v("N13", NW, **kw, monthly_income=limit + 1) == "INELIGIBLE"


def test_newlywed_rental_II_income_and_assets_without_car_limit():
    kw = dict(marital_status="혼인중", marriage_date=date(2024, 1, 1), household_size=3)
    assert v("N15", NW, **kw, monthly_income=10_618_958) == "ELIGIBLE"
    assert v("N15", NW, **kw, monthly_income=10_618_959) == "INELIGIBLE"
    assert v("N15", NW, **kw, dual_income=True, monthly_income=16_336_858) == "ELIGIBLE"
    assert v("N15", NW, **kw, total_assets=362_000_000, car_value=90_000_000) == "ELIGIBLE"   # 자동차 개별 기준 없음
    assert v("N15", NW, **kw, total_assets=362_000_001) == "INELIGIBLE"


def test_newlywed_rental_assets_child_bonus():
    kw = dict(marital_status="혼인중", marriage_date=date(2024, 1, 1), household_size=3, children_birth_dates=[KID_NEW])
    assert v("N13", NW, **kw, total_assets=379_000_000, car_value=49_960_000) == "ELIGIBLE"
    assert v("N13", NW, **kw, total_assets=379_000_001) == "INELIGIBLE"
    assert v("N13", NW, **kw, car_value=49_960_001) == "INELIGIBLE"
    assert v("N15", NW, **kw, total_assets=396_000_000) == "ELIGIBLE"


def test_newlywed_rental_welfare_exemption_except_prospective():
    rich = dict(monthly_income=50_000_000, total_assets=900_000_000, household_size=2)
    assert v("N13", NW, marital_status="혼인중", marriage_date=date(2024, 1, 1), welfare_status="차상위계층", **rich) == "ELIGIBLE"
    assert v("N13", NW, marital_status="예비신혼", welfare_status="차상위계층", **rich) == "INELIGIBLE"
    assert v("N13", NW, is_supported_single_parent=True, **rich) == "ELIGIBLE"
    # 예비신혼부부 제외는 소득·자산 각각에 걸린다 — 하나만 초과하는 사례로 따로 확인
    prospective = dict(marital_status="예비신혼", welfare_status="차상위계층", household_size=2)
    assert v("N13", NW, **prospective, monthly_income=50_000_000, total_assets=1) == "INELIGIBLE"
    assert v("N13", NW, **prospective, monthly_income=1, total_assets=900_000_000) == "INELIGIBLE"
    assert v("N13", NW, **prospective, monthly_income=1, total_assets=1) == "ELIGIBLE"


def test_newlywed_rental_seven_plus_household_is_not_in_the_table():
    r = run("N13", NW, marital_status="혼인중", marriage_date=date(2024, 1, 1), household_size=7)
    assert r.verdict == "MANUAL_REVIEW" and codes(r) == {"AMBIGUOUS_SOURCE"}


# --- 든든전세 ----------------------------------------------------------------------------------
@pytest.mark.parametrize("nid", ["N16", "N17"])
@pytest.mark.parametrize("kw,verdict", [
    (dict(residence_area="서울특별시"), "ELIGIBLE"),
    (dict(residence_area="수원시"), "ELIGIBLE"),
    (dict(residence_area="인천광역시"), "ELIGIBLE"),
    (dict(residence_area="부산광역시"), "INELIGIBLE"),
    (dict(residence_area=None), "NEEDS_INFO"),
    (dict(residence_area="서울특별시", home_ownership="주택보유"), "INELIGIBLE"),
    (dict(residence_area="서울특별시", monthly_income=90_000_000, total_assets=None), "ELIGIBLE"),  # 소득·자산 요건 없음
    (dict(residence_area="서울특별시", age=18), "MANUAL_REVIEW"),
])
def test_jeonse(nid, kw, verdict):
    assert v(nid, "일반", **kw) == verdict


def test_source_dates_are_the_notice_literals():
    import json
    from rule_data import RULES_DIR
    dates = {nid: json.dumps(json.loads((RULES_DIR / "notices" / f"{nid}.json").read_text(encoding="utf-8")))
             for nid in ("N13", "N14", "N15")}
    for nid, ds in (("N13", ("2019-06-25", "2019-06-26", "2024-06-25")), ("N14", ("2019-09-17", "2019-09-18", "2024-09-17")),
                    ("N15", ("2019-06-25", "2019-06-26", "2024-06-25"))):
        assert all(d in dates[nid] for d in ds), nid
