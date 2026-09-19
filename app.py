# -*- coding: utf-8 -*-
"""
app.py — 주거·복지 Eligibility 플랫폼 데모 UI (Streamlit)
==========================================================
사용자가 프로필을 입력하면 결정론적 Rule Engine(evaluate)으로 판정하고,
Explainability 레이어(explain)로 근거와 함께 화면에 보여준다.

이 파일은 판정 로직을 전혀 갖지 않는다 — src/rule_engine.py, src/explainability.py를
그대로 호출해서 결과를 렌더링만 한다. (MVP0.1: 계층별 필수 입력 분기, 미입력/모름과
실제 0 구분, 입력 검증을 추가했다.)
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from rule_engine import HouseholdProfile, evaluate, validate_profile
from notices_data import ALL_NOTICES
from explainability import explain
from profiles_data import PROFILES

st.set_page_config(page_title="주거·복지 Eligibility 데모", page_icon="🏠")
st.title("🏠 주거·복지 Eligibility 판정 데모")
st.caption("LH 행복주택 공고 3건(N1/N2/N3) 대상 — 판정은 결정론적 Rule Engine이 수행합니다. "
           "(MVP0.1 — 지원 범위는 하단 안내 참조)")

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
    st.caption(f"입주자모집공고일: {notice.announcement_date} "
               f"(혼인기간·자녀연령·졸업경과 등은 이 날짜 기준으로 계산합니다)")
    layer = st.selectbox("계층", options=list(notice.layers.keys()))

    st.header("프로필")
    preset_options = ["직접 입력"] + [pid for pid, (_, l) in PRESETS.items() if l == layer]
    other_presets = [pid for pid, (_, l) in PRESETS.items() if l != layer]
    preset_id = st.selectbox("샘플 프로필(선택)", options=preset_options)
    if other_presets:
        st.caption(f"※ 다른 계층용 샘플({', '.join(other_presets)})은 계층 불일치로 목록에서 "
                   f"제외했습니다. 계층 선택 자체가 자격 충족을 의미하지 않습니다 — 아래 조건은 "
                   f"모두 실제로 검사됩니다.")

if preset_id != "직접 입력":
    preset_profile, _preset_layer = PRESETS[preset_id]
else:
    preset_profile = None


def _default(field, fallback):
    return getattr(preset_profile, field) if preset_profile is not None else fallback


def _amount_input(label, field, key):
    """미입력(모름)과 실제 0원을 구분하는 금액 입력 위젯."""
    default_value = _default(field, None)
    unknown_default = default_value is None and preset_profile is not None
    unknown = st.checkbox(f"{label} 모름(미입력)", value=unknown_default, key=f"{key}_unknown")
    amount = st.number_input(
        label, min_value=0, step=100_000,
        value=default_value if isinstance(default_value, int) else 0,
        disabled=unknown, key=key,
    )
    return None if unknown else amount


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
        household_size = st.number_input(
            "가구원수(판정 대상)", min_value=1, max_value=10, value=_default("household_size", 1),
        )
        dual_income = st.checkbox("맞벌이 여부", value=_default("dual_income", False))

        house_head_status = None
        if layer == "청년":
            hh = st.selectbox(
                "세대주/세대원 (등본 기준)", options=["모름(미확인)", "세대주", "세대원"],
                index=["모름(미확인)", "세대주", "세대원"].index(
                    _default("house_head_status", None) or "모름(미확인)"),
            )
            house_head_status = None if hh == "모름(미확인)" else hh

        is_social_rookie = None
        if layer == "청년":
            rookie = st.selectbox(
                "사회초년생 해당 여부(19~39세가 아닐 때만 의미 있음)",
                options=["모름", "예", "아니오"],
                index=["모름", "예", "아니오"].index(
                    {True: "예", False: "아니오", None: "모름"}[_default("is_social_rookie", None)]),
            )
            is_social_rookie = {"모름": None, "예": True, "아니오": False}[rookie]

        student_status, grad_or_dropout_date = None, None
        if layer == "대학생":
            options = ["모름", "재학중", "입학예정", "복학예정", "취업준비생"]
            student_status_label = st.selectbox(
                "재학 상태", options=options,
                index=options.index(_default("student_status", None) or "모름"),
            )
            student_status = None if student_status_label == "모름" else student_status_label
            if student_status == "취업준비생":
                grad_or_dropout_date = st.date_input(
                    "대학·고등학교 졸업(또는 중퇴)일",
                    value=_default("grad_or_dropout_date", None) or date.today(),
                )

        marriage_date, youngest_child_birth_date = None, None
        if layer in ("신혼부부", "한부모"):
            if layer == "신혼부부" and marital_status == "혼인중":
                marriage_known = st.checkbox(
                    "혼인일을 알고 있음", value=_default("marriage_date", None) is not None)
                if marriage_known:
                    marriage_date = st.date_input(
                        "혼인신고일", value=_default("marriage_date", None) or date.today())
            child_known = st.checkbox(
                "막내 자녀 생년월일(태아 포함 시 출산예정일)을 알고 있음",
                value=_default("youngest_child_birth_date", None) is not None)
            if child_known:
                youngest_child_birth_date = st.date_input(
                    "막내 자녀 생년월일/출산예정일",
                    value=_default("youngest_child_birth_date", None) or date.today())

    with col2:
        monthly_income = _amount_input("월소득(원)", "monthly_income", "income_input")
        total_assets = _amount_input("총자산(원)", "total_assets", "assets_input")
        car_default = _default("car_value", 0)
        car_unknown = st.checkbox("자동차가액 확인불가", value=(car_default == "확인불가"))
        car_value = st.number_input(
            "자동차가액(원)", min_value=0, step=100_000,
            value=0 if car_unknown else (car_default if isinstance(car_default, int) else 0),
            disabled=car_unknown,
        )
        has_subscription_account = st.checkbox(
            "청약통장 가입 여부(현재)", value=_default("has_subscription_account", False))
        st.caption("미가입이어도 대부분의 계층은 '입주 전까지'만 가입하면 되므로 현재 자격에는 "
                   "영향이 없습니다(우선공급 배점에는 영향 가능).")
        young_child_count = st.number_input(
            "2023.3.28 이후 출생 자녀 수(가산 소득·자산 기준용)", min_value=0, max_value=10,
            value=_default("young_child_count", 0),
        )
        has_child_under_2 = st.checkbox(
            "2세 미만 자녀 있음(우선공급 대상 여부 참고용 — 이 계산기는 우선공급 배점을 "
            "산출하지 않습니다)",
            value=_default("has_child_under_2", False),
        )

    submitted = st.form_submit_button("판정하기")

if submitted:
    profile = HouseholdProfile(
        profile_id=preset_id if preset_id != "직접 입력" else "직접입력",
        age=age,
        marital_status=marital_status,
        home_ownership=home_ownership,
        house_head_status=house_head_status,
        household_size=household_size,
        monthly_income=monthly_income,
        total_assets=total_assets,
        car_value="확인불가" if car_unknown else car_value,
        has_subscription_account=has_subscription_account,
        has_child_under_2=has_child_under_2,
        dual_income=dual_income,
        young_child_count=young_child_count,
        is_social_rookie=is_social_rookie,
        student_status=student_status,
        grad_or_dropout_date=grad_or_dropout_date,
        marriage_date=marriage_date,
        youngest_child_birth_date=youngest_child_birth_date,
    )

    errors = validate_profile(profile)
    if errors:
        st.error("입력값을 확인해주세요:")
        for e in errors:
            st.markdown(f"- {e}")
    else:
        result = evaluate(profile, notice, layer)
        exp = explain(result, notice)

        icon, style = VERDICT_STYLE[exp.verdict]
        getattr(st, style)(f"{icon} {exp.headline}")
        if exp.score is not None:
            st.caption(f"참고: 확인된 필수조건 중 {exp.score}%를 충족했습니다 "
                       f"(불충족 조건이 하나라도 있으면 신청 자체가 불가하므로, 100% 미만이면 "
                       f"이미 INELIGIBLE 또는 NEEDS_INFO 상태입니다).")

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

st.divider()
with st.expander("이 계산기가 지원하는 범위 / 지원하지 않는 범위"):
    st.markdown(
        "- 서류심사, 경쟁 시 선정(순위·추첨·배점), 최종 당첨 여부는 계산하지 않습니다.\n"
        "- 우선공급 배점(청약저축 납입횟수 등)은 이 화면에서 산출하지 않습니다.\n"
        "- 청년계층 '사회초년생' 세부요건(소득활동기간 5년 이내, 예술인 인증 등 증빙)은 "
        "자기신고 사실로만 처리하며 세부 증빙을 검증하지 않습니다.\n"
        "- 번동3(N3)의 혼인기간 7년/자녀 6세 이하 기준일은 원문에 리터럴 날짜가 없어 "
        "공고일 기준 근사치로 계산합니다 — 자세한 내용은 "
        "docs/rule-coverage-matrix.md를 참고하세요.\n"
        "- 최종 신청 전 반드시 LH 청약플러스 원문 공고문으로 재확인하시기 바랍니다."
    )
