# -*- coding: utf-8 -*-
"""test_job_linked.py — LH 통합공공임대 일자리연계형 지원주택(N66 전주동서학 2026.09.14., N67 담양삼만 2026.10.29.).

기준은 원문에서 손으로 옮겼다(전주 p.10~12, 담양 p.9~11):
- 직업기준: 전주 '지역전략산업 종사자'(전주시·국가유산청 인정 — 입력 job_criterion_met), 담양 '사업·근로소득자'(입력 has_earned_income)
- 신분: 청년 19~39세 미혼(일반형은 18세), 신혼부부·예비신혼부부·6세 이하 자녀, 한부모(6세 이하 자녀). 장기종사자·주거약자용은 미지원
- 소득: 2026 기준중위소득 1인 170% 4,359,205·2인 160% 6,718,867·3인 150% 8,038,554, 신혼 맞벌이 +30%p
- 자산: 총자산 345,000,000·자동차 45,420,000
"""
import sys
from datetime import date
from pathlib import Path

import draft
import form_spec
import notice_candidates as nc
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402

BASE = dict(profile_id="T", age=30, marital_status="미혼", household_size=1, monthly_income=3_000_000, total_assets=100_000_000,
            car_value=0, home_ownership="무주택", house_head_status="세대주", children_birth_dates=[], dual_income=False,
            marriage_date=date(2023, 5, 1), job_criterion_met=True, has_earned_income=True)


def v(nid, layer, **kw):
    return evaluate(HouseholdProfile(**dict(BASE, **kw)), load_notice(nid), layer).verdict


def test_classification_and_job_kind():
    assert nc.classify(["무형유산종사자및예술인종사자만신청가능전주동서학통합공공임대일자리연계형지원주택입주자모집공고", "LH청약플러스"]) == \
        ("LH", "통합공공임대(일자리연계형)")
    assert X.choose_template("LH", "통합공공임대(일자리연계형)") == "lh.integrated_job" and "lh.integrated_job" in draft.PASSING
    assert X.choose_template("LH", "통합공공임대주택") == "lh.integrated_rental"           # 일반형은 그대로
    assert "lh.integrated_rental" in X.VARIANT                                               # 일반형 틀에 일자리연계형이 오면 여전히 막는다


def test_job_criterion_by_notice():
    assert v("N66", "청년", job_criterion_met=False) == "INELIGIBLE"
    assert v("N66", "청년", job_criterion_met=None) == "NEEDS_INFO"
    assert v("N66", "청년", has_earned_income=False) == "ELIGIBLE"          # 전주는 '지역전략산업 종사자'만 본다
    assert v("N67", "청년", has_earned_income=False) == "INELIGIBLE"
    assert v("N67", "청년", job_criterion_met=False) == "ELIGIBLE"          # 담양은 '사업·근로소득자'만 본다


def test_youth_is_19_to_39_and_income_assets():
    assert v("N66", "청년", age=18) == "INELIGIBLE" and v("N66", "청년", age=19) == "ELIGIBLE" and v("N66", "청년", age=40) == "INELIGIBLE"
    assert v("N66", "청년", monthly_income=4_359_205) == "ELIGIBLE" and v("N66", "청년", monthly_income=4_359_206) == "INELIGIBLE"
    assert v("N66", "청년", total_assets=345_000_001) == "INELIGIBLE" and v("N66", "청년", car_value=45_420_001) == "INELIGIBLE"
    married = dict(marital_status="혼인중", household_size=2)
    assert v("N67", "신혼부부", monthly_income=6_718_867, **married) == "ELIGIBLE"
    assert v("N67", "신혼부부", monthly_income=6_718_868, **married) == "INELIGIBLE"


def test_each_notice_asks_only_its_job_question():
    def asked(nid):
        return {f["name"] for f in form_spec.form_for(load_notice(nid), "청년")["fields"]}
    assert "job_criterion_met" in asked("N66") and "has_earned_income" not in asked("N66")
    assert "has_earned_income" in asked("N67") and "job_criterion_met" not in asked("N67")
