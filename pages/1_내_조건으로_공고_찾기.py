# -*- coding: utf-8 -*-
"""내 조건으로 공고 찾기 — 한 번 입력해 공고 26건의 모든 계층을 판정한다(D 단계).

판정은 src/matcher.py가 하고(같은 질문의 계층별 뜻은 rules/reference/input_scope.json), 이 화면은 입력과 표시만 한다.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from explainability import explain  # noqa: E402
from matcher import MasterProfile, match_all, missing_inputs  # noqa: E402
from notices_data import ALL_NOTICES  # noqa: E402
from rule_data import REGION_NONE, region_groups  # noqa: E402

st.set_page_config(page_title="내 조건으로 공고 찾기", page_icon="🔎", layout="wide")
st.title("🔎 내 조건으로 공고 찾기")
st.caption(f"한 번 입력하면 공고 {len(ALL_NOTICES)}건의 모든 계층·주택형을 판정합니다. 모르는 항목은 '모름'으로 두세요 — "
           "그 정보가 필요한 공고는 '추가 정보 필요'로 표시되고, 무엇을 더 입력하면 되는지 알려 드립니다.")

UNKNOWN = "모름"
REGIONS = [UNKNOWN, REGION_NONE] + [n for names in region_groups().values() for n in names]
GROUP_OF = {n: g for g, names in region_groups().items() for n in names}


def pick(label, options, key, help=None):
    v = st.selectbox(label, [UNKNOWN] + options, key=key, help=help)
    return None if v == UNKNOWN else v


def yes_no(label, key, help=None):
    v = st.selectbox(label, [UNKNOWN, "예", "아니오"], key=key, help=help)
    return {"예": True, "아니오": False}.get(v)


def amount(label, key, help=None):
    known = st.checkbox(f"{label} 입력", key=f"{key}_known", value=False)
    return st.number_input(label, min_value=0, step=100_000, key=key, help=help, disabled=not known) if known else None


def region(label, key):
    v = st.selectbox(label, REGIONS, key=key, format_func=lambda n: f"경기 {n}" if GROUP_OF.get(n) == "경기도" else n)
    return None if v == UNKNOWN else v


col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("기본")
    birth = st.date_input("생년월일", value=date(1996, 1, 1), min_value=date(1920, 1, 1), max_value=date.today(),
                          key="m_birth", help="공고마다 공고일 기준 만 나이로 계산합니다.")
    marital = st.selectbox("혼인 상태", ["미혼", "혼인중", "예비신혼", "한부모"], key="m_marital")
    marriage_date = None
    if marital == "혼인중":
        marriage_date = st.date_input("혼인신고일", value=date(2022, 1, 1), min_value=date(1970, 1, 1),
                                      max_value=date.today(), key="m_marriage")
    size = st.number_input("가구원수(무주택세대구성원 전원, 태아 포함)", min_value=1, max_value=10, value=1, key="m_size",
                           help="예비신혼부부는 혼인으로 구성될 세대 기준입니다.")
    head = pick("세대주/세대원(등본 기준)", ["세대주", "세대원"], "m_head")
    dual = st.checkbox("맞벌이(본인·배우자 모두 근로·사업소득)", key="m_dual")
    home_self = pick("본인 주택 소유", ["무주택", "주택보유"], "m_home_self")
    home_household = pick("세대 전원 주택 소유(세대원 중 한 명이라도 보유하면 '주택보유')", ["무주택", "주택보유"], "m_home_house")
with col2:
    st.subheader("소득·자산")
    income_household = amount("세대 월평균소득 합계(원)", "m_inc_house")
    income_self = amount("본인 월평균소득(원)", "m_inc_self", help="1인 가구면 세대 소득과 같으므로 비워 둬도 됩니다.")
    assets_household = amount("세대 총자산(원)", "m_ast_house")
    assets_self = amount("본인 총자산(원)", "m_ast_self")
    car_household = amount("세대 보유 자동차 중 가장 높은 차량가액(원, 없으면 0)", "m_car_house")
    car_self = amount("본인 자동차가액(원, 없으면 0)", "m_car_self")
    st.subheader("자녀(태아 포함)")
    n_kids = st.number_input("세대별 주민등록표에 등재된 미성년 자녀 수(태아 포함)", min_value=0, max_value=8, value=0, key="m_kids")
    kids = [st.date_input(f"자녀 {i + 1} 생년월일(태아는 출산예정일)", value=date(2024, 1, 1), min_value=date(1990, 1, 1),
                          max_value=date.today() + timedelta(days=300), key=f"m_kid_{i}") for i in range(int(n_kids))]
with col3:
    st.subheader("지역")
    residence = region("본인 거주지(주민등록)", "m_res")
    income_base = region("본인 소득 근거지(사업자등록증 소재지)", "m_incbase")
    school = region("재학 중인 대학 캠퍼스 소재지", "m_school")
    spouse_res = region("배우자(예비배우자) 거주지", "m_sp_res")
    spouse_inc = region("배우자(예비배우자) 소득 근거지", "m_sp_inc")

with st.expander("추가 정보(해당하는 것만) — 대학생·취업준비생, 복지 자격, 부모 정보, 주거약자, 특수 자격"):
    a, b, c = st.columns(3)
    with a:
        student = pick("재학 상태", ["재학중", "입학예정", "복학예정", "취업준비생", "해당없음"], "m_student")
        grad = st.date_input("대학·고등학교 졸업(중퇴)일", value=None, min_value=date(1990, 1, 1), max_value=date.today(),
                             key="m_grad")
        employed = yes_no("현재 취업 중", "m_employed")
        rookie = yes_no("사회초년생(소득활동 5년 이내 등) 해당", "m_rookie")
        owned5 = yes_no("본인·배우자가 최근 5년 안에 주택을 소유한 적 있음", "m_owned5")
    with b:
        welfare_opts = ["생계·의료·주거급여 수급자", "교육급여만 수급", "차상위계층", "해당없음"]
        welfare = pick("본인(가구) 복지 자격", welfare_opts, "m_welfare")
        parent_welfare = pick("부모 복지 자격", welfare_opts, "m_pwelfare")
        reg_parents = yes_no("부모와 같은 주민등록표에 등재", "m_regpar")
        supported_sp = yes_no("지원대상 한부모가족(증명서 발급 가능)", "m_supsp")
        benefit = pick("주거급여 수급", ["수급자", "수급권자", "해당없음"], "m_benefit")
        parents_count = pick("소득·자산 검증대상 부모 수", [0, 1, 2], "m_pcount")
        parents_income = amount("부모 월평균소득 합계(원)", "m_pinc")
        parents_assets = amount("부모 총자산 합계(원)", "m_past")
        parents_car = amount("부모 자동차 중 가장 높은 차량가액(원)", "m_pcar")
    with c:
        weak = pick("주거약자 유형(본인)", ["장애인", "국가유공자(상이 1~7급)", "보훈보상대상자(상이 1~7급)",
                                       "5·18민주화운동부상자(장해 1~14급)", "고엽제후유의증환자(경도 이상)",
                                       "국가유공자에 준하는 군경(상이 1~7급)", "해당없음"], "m_weak")
        workplace = pick("산업단지 근무처 유형", ["산업단지 입주기업", "산업단지 교육·연구기관", "경제자유구역 입주 중소기업",
                                           "해당없음"], "m_work")
        workplace_area = region("그 근무처 소재지", "m_workarea")
        affiliation = pick("근무처 소속 여부", ["소속", "비소속 1년 이상 근무(예정)", "비소속 1년 미만"], "m_affil")
        regional = pick("지역전략산업종사자 유형(부천)", ["콘텐츠산업 종사자", "전문예술법인·단체 종사자", "등록 예술인",
                                                 "부천시 추천자", "해당없음"], "m_regional")
        spouse_disabled = yes_no("배우자가 지적·정신장애인 또는 장애 정도가 심한 뇌병변장애인", "m_spdis")
        elderly_parent = yes_no("만 65세 이상 부모(배우자 부모 포함)를 같은 등본에서 1년 이상 부양", "m_eparent")
        veteran = yes_no("국가보훈부로부터 장기전세 우선공급 대상자 통보받음", "m_veteran")

if st.button("전체 공고 판정", type="primary", key="m_run"):
    st.session_state["m_judged"] = True

if st.session_state.get("m_judged"):
    master = MasterProfile(
        home_self=home_self, home_household=home_household, income_self=income_self, income_household=income_household,
        assets_self=assets_self, assets_household=assets_household, car_self=car_self, car_household=car_household,
        birth_date=birth,
        common=dict(marital_status=marital, marriage_date=marriage_date, household_size=int(size),
                    house_head_status=head, dual_income=dual, children_birth_dates=kids,
                    residence_area=residence, income_base_area=income_base, school_area=school,
                    spouse_residence_area=spouse_res, spouse_income_base_area=spouse_inc, workplace_area=workplace_area,
                    student_status=student, grad_or_dropout_date=grad, is_employed=employed, is_social_rookie=rookie,
                    owned_home_in_5y=owned5, welfare_status=welfare, parent_welfare_status=parent_welfare,
                    registered_with_parents=reg_parents, is_supported_single_parent=supported_sp,
                    housing_benefit_status=benefit, parents_count=parents_count, parents_monthly_income=parents_income,
                    parents_total_assets=parents_assets, parents_car_value=parents_car, housing_weak_type=weak,
                    industrial_workplace=workplace, industrial_affiliation=affiliation, regional_industry_type=regional,
                    disabled_spouse_qualifies=spouse_disabled, supports_elderly_parent_1y=elderly_parent,
                    veteran_priority_notified=veteran))
    matches = match_all(master, ALL_NOTICES)
    by = {v: [x for x in matches if x.verdict == v] for v in ("ELIGIBLE", "MANUAL_REVIEW", "NEEDS_INFO", "INELIGIBLE")}
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("✅ 신청 가능", len(by["ELIGIBLE"]))
    m2.metric("🔍 수동 확인 필요", len(by["MANUAL_REVIEW"]))
    m3.metric("⚠️ 추가 정보 필요", len(by["NEEDS_INFO"]))
    m4.metric("❌ 신청 불가", len(by["INELIGIBLE"]))
    st.caption("공고·계층(주택형) 단위로 셉니다. 신청 자격(필수요건)만 판정하며 순위·가점·추첨·당첨은 포함하지 않습니다. "
               "접수 기간이 지난 공고도 있으니 공고일과 원문을 확인하세요.")

    need = missing_inputs(matches)
    if need:
        st.info("이 정보를 더 입력하면 판정할 수 있는 공고가 늘어납니다: "
                + ", ".join(f"**{k}**({v}건)" for k, v in list(need.items())[:6]))

    def row(x, expanded=False):
        n = x.notice
        tracks = f" · 충족: {', '.join(x.result.eligible_tracks)}" if x.result.eligible_tracks else ""
        head_line = f"{n.notice_id} {n.title} — **{x.layer}**{tracks}"
        with st.expander(f"{n.meta.get('issuer', '')} {n.meta.get('program', '')} | 공고일 {n.announcement_date} | "
                         f"{n.title} · {x.layer}", expanded=expanded):
            st.markdown(head_line)
            exp = explain(x.result, n)
            for item in exp.failed:
                st.caption(f"❌ {item.description} (근거: {item.source_ref})")
            for item in exp.review:
                st.caption(f"🔍 {item.description} — {item.detail}")
            for item in exp.unknown:
                st.caption(f"⚠️ 정보 필요: {item.description}")
            for t in exp.tracks:
                if t.verdict == "ELIGIBLE":
                    st.caption(f"✅ {t.track_id}: {t.label}")
            for note in n.meta.get("notes", []):
                st.caption(f"📌 {note}")

    for verdict, title in (("ELIGIBLE", "✅ 신청 가능"), ("MANUAL_REVIEW", "🔍 수동 확인 필요"),
                           ("NEEDS_INFO", "⚠️ 추가 정보 필요"), ("INELIGIBLE", "❌ 신청 불가")):
        if not by[verdict]:
            continue
        st.subheader(f"{title} ({len(by[verdict])})")
        items = by[verdict]
        if verdict == "INELIGIBLE":
            with st.expander(f"신청 불가 {len(items)}건 펼쳐 보기"):
                for x in items:
                    exp = explain(x.result, x.notice)
                    reason = exp.failed[0].description if exp.failed else ""
                    st.caption(f"{x.notice.notice_id} {x.notice.title} · {x.layer} — {reason}")
        else:
            for x in items:
                row(x)
