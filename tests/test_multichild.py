# -*- coding: utf-8 -*-
"""test_multichild.py — SH 다자녀 매입임대 판정 틀(N65 2026.5.29.).

기준은 원문에서 손으로 옮겼다(p.6 신청자격·순위, p.9~10 소득·자산):
- 공통: 미성년 자녀(태아 포함) 2명 이상, 무주택세대구성원, 서울 거주 요건 없음
- 1·2순위: 수급자(생계·주거·의료·교육급여)·차상위·지원대상 한부모 — 소득·자산 검증 없음
- 3순위: 월평균소득 70%(3인 5,717,900·4인 6,161,541), 총자산 345,000,000(출생자녀 1명 379,000,000·2명 이상 413,000,000),
  자동차 45,420,000(49,960,000·54,510,000)
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

KIDS = [date(2012, 1, 1), date(2015, 1, 1)]
BASE = dict(profile_id="T", age=38, marital_status="혼인중", household_size=4, monthly_income=5_000_000, total_assets=200_000_000,
            car_value=0, home_ownership="무주택", residence_area="부산광역시", children_birth_dates=KIDS,
            welfare_status="해당없음", is_supported_single_parent=False)


def v(**kw):
    return evaluate(HouseholdProfile(**dict(BASE, **kw)), load_notice("N65"), "다자녀가구").verdict


def test_classification_sh_only():
    assert nc.classify(["2026년다자녀매입임대주택입주자모집공고(2026.5.29.)SH인터넷청약", "www.i-sh.co.kr"]) == ("SH", "다자녀 매입임대")
    assert X.choose_template("SH", "다자녀 매입임대") == "sh.multichild_rental" and "sh.multichild_rental" in draft.PASSING
    assert X.choose_template("LH", "다자녀 매입임대") is None


def test_third_rank_income_and_assets():
    assert v(monthly_income=6_161_541) == "ELIGIBLE" and v(monthly_income=6_161_542) == "INELIGIBLE"
    assert v(household_size=3, children_birth_dates=KIDS, marital_status="한부모", monthly_income=5_717_900) == "ELIGIBLE"
    assert v(total_assets=345_000_000) == "ELIGIBLE" and v(total_assets=345_000_001) == "INELIGIBLE"
    assert v(car_value=45_420_001) == "INELIGIBLE"
    newborn = KIDS + [date(2025, 1, 1)]                          # '23.3.28. 이후 출생 1명 + 이전 자녀 → 413,000,000
    assert v(household_size=5, children_birth_dates=newborn, total_assets=413_000_000) == "ELIGIBLE"
    assert v(household_size=5, children_birth_dates=newborn, total_assets=413_000_001) == "INELIGIBLE"


def test_welfare_ranks_skip_income_and_assets():
    assert v(welfare_status="차상위계층", monthly_income=20_000_000, total_assets=900_000_000) == "ELIGIBLE"
    assert v(is_supported_single_parent=True, marital_status="한부모", monthly_income=20_000_000) == "ELIGIBLE"


def test_common_requirements():
    assert v(children_birth_dates=[date(2012, 1, 1)]) == "INELIGIBLE"                      # 미성년 자녀 1명
    assert v(children_birth_dates=[date(2005, 1, 1), date(2012, 1, 1)]) == "INELIGIBLE"    # 한 명은 성년
    assert v(home_ownership="주택보유") == "INELIGIBLE"


def test_unseen_draft_builds_without_missing_quotes():
    d = draft.make_draft(sv.pdf_path("N65").read_bytes(), only=None, pages=sv.pdf_pages("N65"), exclude="N65")
    assert d.status == draft.OK and d.template == "sh.multichild_rental" and d.missing == [] and not d.held_fields
