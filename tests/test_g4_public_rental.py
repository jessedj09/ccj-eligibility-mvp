# -*- coding: utf-8 -*-
"""test_g4_public_rental.py — G4: 공공임대(10년·분양전환·50년) 예비입주자 판정 틀(lh.public_rental, N37~N44).

기준은 원문에서 손으로 옮겼다:
- 파주운정3 A12(N37) p.1 "모집공고일현재수도권에거주(주민등록표등본기준)하는무주택세대구성원인성년자", "청약저축가입여부,소득및자산
  기준충족여부와는상관없으며", "(재당첨제한자추후계약체결불가)".
- 오산운암6(N39) p.3 "현재주택건설지역(경기도,서울특별시,인천광역시)에거주하는무주택세대구성원", p.5 "2순위…주택청약종합저축
  (청약저축포함)에가입되어있고1순위에해당되지아니하는자" — 통장이 없으면 신청할 수 없다.
- 구리갈매 S1(N43) p.6 "2순위입주자저축…에가입하여6월이경과된분으로서…6회이상납입한자", p.5 재당첨 제한 기간 중이면 신청 불가.
- 대전천동(N41) p.1 "현재국내에거주하는성년자인무주택세대구성원", 과거 당첨 사실 여부 불문. 동해천곡5(N44) 거주 요건 없음.
"""
import sys
from pathlib import Path

import draft
import pytest
import source_verify as sv
from rule_data import load_notice
from rule_engine import HouseholdProfile, evaluate

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import sheet_extract as X  # noqa: E402


def v(nid, **kw):
    base = dict(profile_id="T", age=40, marital_status="미혼", home_ownership="무주택", residence_area="고양시",
                has_subscription_account=True, subscription_months=12, subscription_payment_count=12, rewin_restricted=False)
    base.update(kw)
    return evaluate(HouseholdProfile(**base), load_notice(nid), "일반").verdict


@pytest.mark.parametrize("nid", [f"N{n}" for n in range(37, 45)])
def test_basic_eligible_and_home_owner_is_not(nid):
    assert v(nid) == "ELIGIBLE"
    assert v(nid, home_ownership="주택보유") == "INELIGIBLE"
    assert v(nid, age=18) == "MANUAL_REVIEW"          # 미성년 예외(자녀 있는 미성년 세대주 등)는 화면이 묻지 않는다


@pytest.mark.parametrize("nid", ["N37", "N38", "N39", "N40", "N42", "N43"])
def test_capital_region_only(nid):
    assert v(nid, residence_area="서울특별시") == v(nid, residence_area="가평군") == "ELIGIBLE"
    assert v(nid, residence_area="부산광역시") == "INELIGIBLE"
    assert v(nid, residence_area=None) == "NEEDS_INFO"


@pytest.mark.parametrize("nid", ["N41", "N44"])
def test_no_region_requirement(nid):
    assert v(nid, residence_area="부산광역시") == v(nid, residence_area=None) == "ELIGIBLE"


def test_subscription_requirements():
    for nid in ("N37", "N38", "N40", "N41", "N42"):               # 청약저축 가입 여부와 관계없이
        assert v(nid, has_subscription_account=False, subscription_months=0, subscription_payment_count=0) == "ELIGIBLE"
    for nid in ("N39", "N44"):                                     # 2순위도 가입은 필요
        assert v(nid, has_subscription_account=False) == "INELIGIBLE"
        assert v(nid, subscription_months=0, subscription_payment_count=0) == "ELIGIBLE"
    assert v("N43", subscription_months=6, subscription_payment_count=6) == "ELIGIBLE"     # 2순위 6개월·6회
    assert v("N43", subscription_months=5, subscription_payment_count=6) == "INELIGIBLE"
    assert v("N43", subscription_months=6, subscription_payment_count=5) == "INELIGIBLE"
    assert v("N43", has_subscription_account=False) == "INELIGIBLE"


def test_rewin_restriction_only_where_the_notice_says_so():
    for nid in ("N37", "N38", "N40", "N42", "N43"):
        assert v(nid, rewin_restricted=True) == "INELIGIBLE"
        assert v(nid, rewin_restricted=None) == "NEEDS_INFO"
    for nid in ("N39", "N41", "N44"):                              # 50년 공공임대·과거 당첨 사실 불문
        assert v(nid, rewin_restricted=True) == v(nid, rewin_restricted=None) == "ELIGIBLE"


def test_template_choice_and_first_tenant_notice_is_blocked():
    assert X.choose_template("LH", "공공임대주택") == "lh.public_rental"
    assert X.choose_template("SH", "공공임대주택") is None
    assert X.variant_notice("lh.public_rental", ["양주옥정10년공공임대주택리츠예비입주자모집"]) is None
    assert "최초 입주자 모집" in X.variant_notice("lh.public_rental", ["○○지구10년공공임대주택입주자모집공고(특별공급·일반공급)"])


@pytest.mark.parametrize("nid,region,account,rewin", [
    ("N37", "수도권", None, True), ("N38", "수도권", None, True), ("N39", "수도권", "가입", False),
    ("N43", "수도권", {"months": 6, "count": 6}, True), ("N44", None, "가입", False), ("N41", None, None, False),
])
def test_extractor_reads_region_account_and_rewin(nid, region, account, rewin):
    f = X.extract(sv.pdf_pages(nid))["fields"]
    assert (f["residence"].status, f["residence"].value) == (X.FILLED, region)
    assert (f["account"].status, f["account"].value) == (X.FILLED, account)
    assert (f["rewin_quote"].status == X.FILLED) == rewin


def test_public_rental_is_auto_judged_for_new_uploads():
    """G4: 처음 보는 공고 5건 위험 0 — 새 업로드 자동 판정(PASSING). 등록 공고 원문을 처음 보는 공고처럼 판정해도 등록 규칙과 같다."""
    assert "lh.public_rental" in draft.PASSING
    d = draft.make_draft(sv.pdf_path("N38").read_bytes())
    assert d.status == draft.OK and d.template == "lh.public_rental"
    reg = load_notice("N38")
    for kw in (dict(), dict(home_ownership="주택보유"), dict(residence_area="부산광역시"), dict(rewin_restricted=True)):
        p = HouseholdProfile(**dict(dict(profile_id="T", age=40, marital_status="미혼", home_ownership="무주택",
                                         residence_area="고양시", rewin_restricted=False), **kw))
        assert draft.judge(d, p, "일반")[0] == evaluate(p, reg, "일반").verdict
