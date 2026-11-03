# -*- coding: utf-8 -*-
"""test_g5_rental.py — G5: SH 국민임대(sh.national_rental, N53)·SH 영구임대(sh.permanent_rental, N54)·LH 고령자복지주택(lh.elderly_welfare, N55).

기준은 원문에서 손으로 옮겼다:
- p.22 공통: "입주자 모집공고일(2026.08.20.) 현재 서울특별시에 거주하는 성년자인 무주택세대구성원" — 상계장암지구 1·2단지는
  의정부·남양주·양주·포천시 거주자도(3·4단지는 의정부시도) 신청 가능, 민법상 미성년자 불가(예외 있음).
- p.24~25 소득 70%(1인 +20%p·2인 +10%p, 2023.3.28. 이후 출생자녀 1명 +10%p·2명 이상 +20%p) — 2025년도 표 1~6인
  (3인 70% 5,717,900원, 1인 90% 3,432,027원), 총자산 34,500만·자동차 4,542만(가산 37,900·4,996 / 41,300·5,451).
- p.29 일반공급(주거약자): 고령자(만 65세 이상)·장애인·상이 국가유공자 등 ①~⑦ 중 하나(공급신청자 본인).
50% 선순위·해당구/연접구·청약저축 회차는 경쟁 시 순서라 판정하지 않는다.
"""
import importlib.util
import sys
from datetime import date
from pathlib import Path

import draft
import notice_candidates as nc
import pytest
import source_verify as sv
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sheet_extract as X  # noqa: E402

_spec = importlib.util.spec_from_file_location("gen_c6_public", ROOT / "tools" / "gen_c6_public.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)


def v(layer="일반", **kw):
    base = dict(profile_id="T", age=40, marital_status="혼인중", home_ownership="무주택", household_size=3,
                monthly_income=5_000_000, total_assets=200_000_000, car_value=20_000_000, residence_area="서울특별시",
                children_birth_dates=[], housing_weak_type="해당없음")
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice("N53"), layer).verdict


def test_income_70_percent_with_household_adders():
    assert v(monthly_income=5_717_900) == "ELIGIBLE" and v(monthly_income=5_717_901) == "INELIGIBLE"     # 3인 70%
    assert v(household_size=1, monthly_income=3_432_027) == "ELIGIBLE"                                     # 1인 90%
    assert v(household_size=1, monthly_income=3_432_028) == "INELIGIBLE"
    assert v(household_size=3, monthly_income=6_534_743, children_birth_dates=[date(2024, 1, 1)]) == "ELIGIBLE"  # 출생자녀 +10%p
    assert v(household_size=3, monthly_income=6_534_744, children_birth_dates=[date(2024, 1, 1)]) == "INELIGIBLE"


def test_assets_and_car():
    assert v(total_assets=345_000_000) == "ELIGIBLE" and v(total_assets=345_000_001) == "INELIGIBLE"
    assert v(car_value=45_420_000) == "ELIGIBLE" and v(car_value=45_420_001) == "INELIGIBLE"


def test_seoul_residence_and_sanggye_near_cities():
    assert v(residence_area="수원시") == "INELIGIBLE"
    assert v(residence_area="의정부시") == "MANUAL_REVIEW"       # 상계장암지구 단지에만 신청 가능 — 확인 필요
    assert v(home_ownership="주택보유") == "INELIGIBLE"


def test_weak_layer_needs_applicant_weak_status():
    assert v("일반(주거약자용)", age=70) == "ELIGIBLE"
    assert v("일반(주거약자용)", housing_weak_type="장애인") == "ELIGIBLE"
    assert v("일반(주거약자용)") == "INELIGIBLE"


def test_template_choice_and_korean_announcement_date():
    assert X.choose_template("SH", "국민임대주택") == "sh.national_rental"
    assert X.choose_template("LH", "국민임대주택") == "lh.national_rental"
    assert X.choose_template("SH", "통합공공임대주택") is None
    assert nc.announcement_candidates(["모집공고일:2026년8월20일(목)"])[0]["date"] == "2026-08-20"
    assert tuple(X.SH_NEAR_CITIES) == tuple(G.SH_NEAR)
    assert "sh.national_rental" in draft.PASSING


def test_unseen_draft_matches_registered_rules():
    """N53 원문을 처음 보는 공고처럼(형제에서 자기 자신을 빼고) 읽은 초안의 조건이 등록 규칙과 같다(인용문 표기 차이 제외)."""
    d = draft.make_draft(sv.pdf_path("N53").read_bytes(), only=None, pages=sv.pdf_pages("N53"), exclude="N53")
    assert d.status == draft.OK and d.template == "sh.national_rental" and not d.held_fields
    reg = load_notice("N53")
    assert set(d.notice.layers) == set(reg.layers)
    for layer in reg.layers:
        for p in (dict(), dict(monthly_income=5_717_901), dict(residence_area="의정부시"), dict(age=70),
                  dict(household_size=1, monthly_income=3_432_027)):
            prof = HouseholdProfile(**dict(dict(profile_id="T", age=40, marital_status="혼인중", home_ownership="무주택",
                                                household_size=3, monthly_income=5_000_000, total_assets=200_000_000,
                                                car_value=0, residence_area="서울특별시", children_birth_dates=[],
                                                housing_weak_type="해당없음"), **p))
            assert evaluate(prof, d.notice, layer).verdict == evaluate(prof, reg, layer).verdict, (layer, p)


def test_near_sentence_with_other_cities_is_held():
    pages = ["입주자모집공고일(2026.08.20.)현재서울특별시에거주하는성년자인무주택세대구성원으로서",
             "-○○지구1,2단지는서울특별시외고양시,파주시에거주하는사람도신청가능"]
    assert X._sh_national_rental(pages)["near_quote"].status == X.HELD
    assert X._sh_national_rental(pages[:1])["near_quote"].status == X.ABSENT


# ---------------------------------------------------------------- SH 영구임대(N54 2025.11.13.)
# p.7 서울 거주 성년 무주택세대구성원 + 별표3 1순위(가~자), p.9 70%(1인 90%·2인 80%) 총자산 23,700만·자동차 4,563만
# (출생자녀 1명 261백만·5,020만, 2명 이상 285백만·5,476만), p.10 2025년도 표(3인 70% 5,338,881원).
def vp(**kw):
    base = dict(profile_id="T", age=50, marital_status="혼인중", home_ownership="무주택", household_size=3,
                monthly_income=5_000_000, total_assets=200_000_000, car_value=0, residence_area="서울특별시",
                children_birth_dates=[], housing_weak_type="장애인", welfare_status="해당없음",
                livelihood_medical_recipient=False, merit_person=False, is_supported_single_parent=False,
                north_korean_defector=False, disabled_spouse_qualifies=False, supports_elderly_parent=False,
                child_facility_leaver=False)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice("N54"), "일반").verdict


def test_sh_permanent_tracks_income_assets_and_seoul():
    assert vp(monthly_income=5_338_881) == "ELIGIBLE" and vp(monthly_income=5_338_882) == "INELIGIBLE"
    assert vp(total_assets=237_000_000) == "ELIGIBLE" and vp(total_assets=237_000_001) == "INELIGIBLE"
    assert vp(car_value=45_630_000) == "ELIGIBLE" and vp(car_value=45_630_001) == "INELIGIBLE"
    assert vp(housing_weak_type="해당없음") == "INELIGIBLE"                      # 1순위 신분이 없으면(2순위 없음)
    assert vp(housing_weak_type="해당없음", livelihood_medical_recipient=True, monthly_income=9_000_000) == "ELIGIBLE"
    assert vp(housing_weak_type="해당없음", age=70, welfare_status="차상위계층") == "ELIGIBLE"
    assert vp(residence_area="고양시") == "INELIGIBLE"


def test_sh_permanent_unseen_draft_matches_and_other_limits_are_held():
    assert X.choose_template("SH", "영구임대주택") == "sh.permanent_rental" and "sh.permanent_rental" in draft.PASSING
    d = draft.make_draft(sv.pdf_path("N54").read_bytes(), only=None, pages=sv.pdf_pages("N54"), exclude="N54")
    assert d.status == draft.OK and d.template == "sh.permanent_rental" and not d.held_fields
    reg = load_notice("N54")
    for kw in (dict(), dict(monthly_income=5_338_882), dict(total_assets=237_000_001), dict(residence_area="고양시")):
        p = HouseholdProfile(**dict(dict(profile_id="T", age=50, marital_status="혼인중", home_ownership="무주택",
                                         household_size=3, monthly_income=5_000_000, total_assets=200_000_000, car_value=0,
                                         residence_area="서울특별시", children_birth_dates=[], housing_weak_type="장애인",
                                         welfare_status="해당없음"), **kw))
        assert evaluate(p, d.notice, "일반").verdict == evaluate(p, reg, "일반").verdict, kw
    # 다음 해 공고처럼 한도 금액이 다르면 리터럴로 판정하지 않고 보류
    pages = [t.replace("(23,700)만원이하", "(24,500)만원이하") for t in sv.pdf_pages("N54")]
    assert X._sh_permanent_rental(pages)["asset_quote"].status == X.HELD


# ---------------------------------------------------------------- LH 고령자복지주택(N55 평택고덕 A-58, 2026.08.20.)
# p.5 만 65세 이상 무주택세대구성원, p.6 1순위 가 생계·의료급여 / 2순위 나 국가유공자 등 70%(1인 90%·2인 80%) / 3순위 차 50%
# (1인 70%·2인 60%) — 적용 금액 2인 60% 3,519,762원·80% 4,693,016원, p.7 총자산 24,500만·자동차 4,542만(출생자녀 가산 없음).
def ve(**kw):
    base = dict(profile_id="T", age=70, marital_status="혼인중", home_ownership="무주택", household_size=2,
                monthly_income=3_000_000, total_assets=200_000_000, car_value=0, residence_area="평택시",
                children_birth_dates=[], livelihood_medical_recipient=False, merit_person=False)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice("N55"), "고령자").verdict


def test_elderly_welfare_ranks_and_limits():
    assert ve(monthly_income=3_519_762) == "ELIGIBLE" and ve(monthly_income=3_519_763) == "INELIGIBLE"     # 3순위 2인 60%
    assert ve(merit_person=True, monthly_income=4_693_016) == "ELIGIBLE"                                       # 2순위 2인 80%
    assert ve(merit_person=True, monthly_income=4_693_017) == "INELIGIBLE"
    assert ve(livelihood_medical_recipient=True, monthly_income=9_000_000, total_assets=900_000_000) == "ELIGIBLE"
    assert ve(age=64) == "INELIGIBLE" and ve(total_assets=245_000_001) == "INELIGIBLE"
    assert ve(car_value=45_420_001) == "INELIGIBLE"
    assert ve(household_size=1, monthly_income=2_669_354) == "ELIGIBLE"                                     # 1인 70%


def test_elderly_welfare_unseen_draft_and_only_permanent_type():
    assert X.choose_template("LH", "고령자복지주택") == "lh.elderly_welfare" and "lh.elderly_welfare" in draft.PASSING
    d = draft.make_draft(sv.pdf_path("N55").read_bytes(), only=None, pages=sv.pdf_pages("N55"), exclude="N55")
    assert d.status == draft.OK and d.template == "lh.elderly_welfare" and not d.held_fields
    reg = load_notice("N55")
    for kw in (dict(), dict(monthly_income=3_519_763), dict(age=64), dict(merit_person=True, monthly_income=4_600_000)):
        p = HouseholdProfile(**dict(dict(profile_id="T", age=70, marital_status="혼인중", home_ownership="무주택",
                                         household_size=2, monthly_income=3_000_000, total_assets=200_000_000, car_value=0,
                                         residence_area="평택시", children_birth_dates=[], livelihood_medical_recipient=False,
                                         merit_person=False), **kw))
        assert evaluate(p, d.notice, "고령자").verdict == evaluate(p, reg, "고령자").verdict, kw
    # 영구임대형이라는 표시가 없으면(국민임대형 등) 자동 판정하지 않는다
    pages = [t.replace("고령자복지주택(영구임대)", "고령자복지주택") for t in sv.pdf_pages("N55")]
    assert X._elderly_welfare(pages)["kind"].status == X.HELD
    assert X.is_critical("lh.elderly_welfare", "kind")
