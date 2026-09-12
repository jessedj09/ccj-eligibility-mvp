# -*- coding: utf-8 -*-
"""
app.py — 주거·복지 Eligibility 플랫폼 데모 UI (Streamlit)
==========================================================
사용자가 프로필을 입력하면 결정론적 Rule Engine(evaluate)으로 판정하고,
Explainability 레이어(explain)로 근거와 함께 화면에 보여준다.

이 파일은 판정 로직을 전혀 갖지 않는다 — src/rule_engine.py, src/explainability.py를
그대로 호출해서 결과를 렌더링만 한다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from rule_engine import HouseholdProfile, evaluate
from notices_data import ALL_NOTICES
from explainability import explain
from profiles_data import PROFILES

st.set_page_config(page_title="주거·복지 Eligibility 데모", page_icon="🏠")
st.title("🏠 주거·복지 Eligibility 판정 데모")
st.caption("LH 행복주택 공고 3건(N1/N2/N3) 대상 — 판정은 결정론적 Rule Engine이 수행합니다.")

PRESETS = {profile.profile_id: (profile, layer) for profile, layer in PROFILES}

VERDICT_STYLE = {
    "ELIGIBLE": ("✅", "success"),
    "INELIGIBLE": ("❌", "error"),
    "NEEDS_INFO": ("⚠️", "warning"),
    "NOT_OFFERED": ("➖", "info"),
}

with st.sidebar:
    st.header("공고 · 계층 선택")
    notice_id = st.selectbox(
        "공고", options=list(ALL_NOTICES.keys()),
        format_func=lambda nid: f"{nid} — {ALL_NOTICES[nid].title}",
    )
    notice = ALL_NOTICES[notice_id]
    layer = st.selectbox("계층", options=list(notice.layers.keys()))

    st.header("프로필")
    preset_id = st.selectbox("샘플 프로필(선택)", options=["직접 입력"] + list(PRESETS.keys()))

if preset_id != "직접 입력":
    preset_profile, preset_layer = PRESETS[preset_id]
else:
    preset_profile = None

def _default(field, fallback):
    return getattr(preset_profile, field) if preset_profile is not None else fallback

with st.form("profile_form"):
    col1, col2 = st.columns(2)
    with col1:
        age = st.number_input("나이", min_value=0, max_value=120, value=_default("age", 30))
        marital_status = st.selectbox(
            "혼인 상태", options=["미혼", "혼인중", "예비신혼", "한부모"],
            index=["미혼", "혼인중", "예비신혼", "한부모"].index(_default("marital_status", "미혼")),
        )
        home_ownership = st.selectbox(
            "주택 소유", options=["무주택", "주택보유"],
            index=["무주택", "주택보유"].index(_default("home_ownership", "무주택")),
        )
        house_head_status = st.selectbox(
            "세대주/세대원 (등본 기준)", options=["해당없음", "세대주", "세대원"],
            index=["해당없음", "세대주", "세대원"].index(_default("house_head_status", None) or "해당없음"),
        )
        household_size = st.number_input(
            "가구원수(판정 대상)", min_value=1, max_value=10, value=_default("household_size", 1),
        )
        dual_income = st.checkbox("맞벌이 여부", value=_default("dual_income", False))
    with col2:
        monthly_income = st.number_input(
            "월소득(원)", min_value=0, step=100_000, value=_default("monthly_income", 0),
        )
        total_assets = st.number_input(
            "총자산(원)", min_value=0, step=1_000_000, value=_default("total_assets", 0),
        )
        car_default = _default("car_value", 0)
        car_unknown = st.checkbox("자동차가액 확인불가", value=(car_default == "확인불가"))
        car_value = st.number_input(
            "자동차가액(원)", min_value=0, step=100_000,
            value=0 if car_unknown else (car_default if isinstance(car_default, int) else 0),
            disabled=car_unknown,
        )
        has_subscription_account = st.checkbox(
            "청약통장 가입 여부(현재)", value=_default("has_subscription_account", False),
        )
        young_child_count = st.number_input(
            "2023.3.28 이후 출생 자녀 수", min_value=0, max_value=10,
            value=_default("young_child_count", 0),
        )
        has_child_under_2 = st.checkbox(
            "2세 미만 자녀 있음(우선공급용)", value=_default("has_child_under_2", False),
        )

    submitted = st.form_submit_button("판정하기")

if submitted:
    profile = HouseholdProfile(
        profile_id=preset_id if preset_id != "직접 입력" else "직접입력",
        age=age,
        marital_status=marital_status,
        home_ownership=home_ownership,
        house_head_status=None if house_head_status == "해당없음" else house_head_status,
        household_size=household_size,
        monthly_income=monthly_income,
        total_assets=total_assets,
        car_value="확인불가" if car_unknown else car_value,
        has_subscription_account=has_subscription_account,
        has_child_under_2=has_child_under_2,
        dual_income=dual_income,
        young_child_count=young_child_count,
    )

    result = evaluate(profile, notice, layer)
    exp = explain(result, notice)

    icon, style = VERDICT_STYLE[exp.verdict]
    getattr(st, style)(f"{icon} {exp.headline}")

    if exp.matched:
        st.subheader("충족한 조건")
        for item in exp.matched:
            st.markdown(f"- {item.description} _(근거: {item.source_ref})_")

    if exp.failed:
        st.subheader("충족하지 못한 조건")
        for item in exp.failed:
            st.markdown(f"- {item.description} _(근거: {item.source_ref})_")

    if exp.unknown:
        st.subheader("확인이 필요한 조건")
        for item in exp.unknown:
            st.markdown(f"- {item.description} _(근거: {item.source_ref})_")

    if exp.notes:
        for note in exp.notes:
            st.caption(note)
