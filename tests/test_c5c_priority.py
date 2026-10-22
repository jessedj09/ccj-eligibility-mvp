# -*- coding: utf-8 -*-
"""test_c5c_priority.py — 장기전세 우선공급(서울시 매입형 60㎡ 이하) — N25 49차, N26 50차.

원문: SH24 p.28·29 / SH23 p.27·28 — "일반공급과 동일하게 무주택, 소득, 총자산 및 자동차 기준을 충족"(소득 105%·맞벌이 140%)하고
- 고령자(50차만): 만 65세 이상[1961.04.27. 이전 출생]인 2인 이하 무주택 세대구성원(2인 = 신청자·배우자)
- 장애인: 장애인등록증 교부자(지적·정신·심한 뇌병변장애인은 그 배우자 포함)
- 노부모부양자: 만 65세 이상 직계존속을 같은 등본에서 1년 이상 부양, 피부양자·그 배우자도 무주택
- 2자녀이상: 미성년자(50차 2007.4.28. / 49차 2006.12.16. 이후 출생, 태아 포함) 2명 이상이 같은 등본에
- 국가유공자 등: 국가보훈부가 선정·통보한 사람 → 신청 시점엔 확인 불가(SELF_REPORT_UNVERIFIED)
"""

import json
from datetime import date

import pytest
from rule_data import RULES_DIR, load_notice
from rule_engine import HouseholdProfile, evaluate


def run(nid, kind, **kw):
    base = dict(profile_id="T", age=40, marital_status="혼인중", home_ownership="무주택", household_size=3,
                monthly_income=1_000_000, total_assets=10_000_000, car_value=0, children_birth_dates=[],
                residence_area="서울특별시")
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), f"일반(우선공급·{kind})")


def v(*a, **kw):
    return run(*a, **kw).verdict


@pytest.mark.parametrize("nid", ["N25", "N26"])
def test_priority_layers_are_general_60_conditions_plus_one(nid):
    doc = json.loads((RULES_DIR / "notices" / f"{nid}.json").read_text(encoding="utf-8"))
    base = doc["layers"]["일반(전용 60㎡ 이하)"]["conditions"]
    kinds = [k for k in doc["layers"] if k.startswith("일반(우선공급·")]
    assert len(kinds) == (5 if nid == "N26" else 4)
    for k in kinds:
        assert doc["layers"][k]["conditions"][:-1] == base
    assert not doc["unsupported_layers"]


@pytest.mark.parametrize("nid", ["N25", "N26"])
def test_disabled(nid):
    assert v(nid, "장애인", housing_weak_type="장애인") == "ELIGIBLE"
    assert v(nid, "장애인", housing_weak_type="해당없음", disabled_spouse_qualifies=True) == "ELIGIBLE"
    assert v(nid, "장애인", housing_weak_type="해당없음", disabled_spouse_qualifies=False) == "INELIGIBLE"
    assert v(nid, "장애인", housing_weak_type="국가유공자(상이 1~7급)", disabled_spouse_qualifies=False) == "INELIGIBLE"
    assert v(nid, "장애인") == "NEEDS_INFO"


@pytest.mark.parametrize("nid", ["N25", "N26"])
def test_elderly_parent_support(nid):
    assert v(nid, "노부모부양", supports_elderly_parent_1y=True) == "ELIGIBLE"
    assert v(nid, "노부모부양", supports_elderly_parent_1y=False) == "INELIGIBLE"


@pytest.mark.parametrize("nid,minor", [("N26", date(2007, 4, 28)), ("N25", date(2006, 12, 16))])
def test_two_or_more_minor_children(nid, minor):
    from datetime import timedelta
    kids = lambda *ds: dict(children_birth_dates=list(ds), household_size=2 + len(ds))
    assert v(nid, "2자녀이상", **kids(date(2015, 1, 1), minor)) == "ELIGIBLE"
    assert v(nid, "2자녀이상", **kids(date(2015, 1, 1), minor - timedelta(days=1))) == "INELIGIBLE"   # 성년 자녀
    assert v(nid, "2자녀이상", **kids(date(2015, 1, 1), date(2026, 12, 1))) == "ELIGIBLE"            # 태아 포함
    assert v(nid, "2자녀이상", **kids(date(2015, 1, 1))) == "INELIGIBLE"
    assert v(nid, "2자녀이상", children_birth_dates=None) == "NEEDS_INFO"


@pytest.mark.parametrize("nid", ["N25", "N26"])
def test_veteran_is_always_manual_review_when_claimed(nid):
    r = run(nid, "국가유공자", veteran_priority_notified=True)
    assert r.verdict == "MANUAL_REVIEW" and {x.code for x in r.review_reasons.values()} == {"SELF_REPORT_UNVERIFIED"}
    assert v(nid, "국가유공자", veteran_priority_notified=False) == "INELIGIBLE"


def test_elderly_only_in_50th_and_two_person_rule():
    assert "일반(우선공급·고령자)" not in load_notice("N25").layers
    assert v("N26", "고령자", age=65, household_size=1, marital_status="미혼") == "ELIGIBLE"
    assert v("N26", "고령자", age=65, household_size=2) == "ELIGIBLE"                     # 신청자+배우자
    assert v("N26", "고령자", age=64, household_size=1) == "INELIGIBLE"
    assert v("N26", "고령자", age=70, household_size=3) == "INELIGIBLE"                   # 2인 초과
    r = run("N26", "고령자", age=70, household_size=2, marital_status="한부모")
    assert r.verdict == "MANUAL_REVIEW"                                                  # 배우자 아닌 2인


@pytest.mark.parametrize("nid", ["N25", "N26"])
def test_priority_still_needs_general_income_assets(nid):
    limit = {"N25": 8_008_322, "N26": 8_576_850}[nid]                    # 3인 105%
    assert v(nid, "노부모부양", supports_elderly_parent_1y=True, monthly_income=limit) == "ELIGIBLE"
    assert v(nid, "노부모부양", supports_elderly_parent_1y=True, monthly_income=limit + 1) == "INELIGIBLE"
    assert v(nid, "노부모부양", supports_elderly_parent_1y=True, residence_area="고양시") == "INELIGIBLE"
