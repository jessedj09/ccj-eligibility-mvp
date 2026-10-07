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
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import streamlit as st

from rule_engine import HouseholdProfile, evaluate, validate_profile
from notices_data import ALL_NOTICES
from explainability import explain
from profiles_data import PROFILES

REVIEW_BADGE = {
    "DRAFT": ("🟠 초안(DRAFT)", "규칙을 만든 쪽 외의 독립 검토를 아직 거치지 않았습니다. 참고용으로만 쓰세요."),
    "REVIEWED": ("🟡 검토됨(REVIEWED)", "독립 검토를 마쳤으나 아직 공개 확정 전입니다."),
    "PUBLISHED": ("🟢 확정(PUBLISHED)", "독립 검토를 마치고 공개 확정된 규칙입니다."),
    "RETIRED": ("⚪ 폐기(RETIRED)", "더 이상 쓰지 않는 규칙입니다."),
}

st.set_page_config(page_title="주거·복지 Eligibility 데모", page_icon="🏠")
st.title("🏠 주거·복지 Eligibility 판정 데모")
st.caption("LH 행복주택 공고 3건(N1/N2/N3) 대상 — 판정은 결정론적 Rule Engine이 수행합니다. "
           "(MVP0.1 — 지원 범위는 하단 안내 참조)")

PRESETS = {profile.profile_id: (profile, layer) for profile, layer in PROFILES}

VERDICT_STYLE = {
    "ELIGIBLE": ("✅", "success"),
    "INELIGIBLE": ("❌", "error"),
    "NEEDS_INFO": ("⚠️", "warning"),
    "MANUAL_REVIEW": ("🔍", "warning"),
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
    review_status = notice.meta["review"]["status"]
    label, hint = REVIEW_BADGE[review_status]
    st.caption(f"규칙 검수 상태: **{label}** — {hint}")
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
        help="신혼부부는 부부 2인 이상입니다. 예비신혼부부는 신청자 본인과 예비배우자, 공고일 기준 동일 세대에 "
             "등재된 직계존속·비속을 포함한 '혼인으로 구성될 세대' 기준이며 2인 이상입니다. "
             "한부모는 본인과 자녀를 포함합니다.",
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
                min_value=date(1990, 1, 1), max_value=date.today(),
            )

    marriage_date = None
    if layer == "신혼부부" and marital_status == "혼인중":
        marriage_known = st.checkbox(
            "혼인일을 알고 있음", value=_default("marriage_date", None) is not None)
        if marriage_known:
            marriage_date = st.date_input(
                "혼인신고일", value=_default("marriage_date", None) or date.today(),
                min_value=date(1980, 1, 1), max_value=date.today())

    # 자녀: 생년월일 목록만 받고, 출생자녀 가산 수·6세 이하 여부·자녀 유무는 엔진이 계산한다.
    preset_dates = _default("children_birth_dates", None)
    if preset_dates is None:
        yd = _default("youngest_child_birth_date", None)
        preset_dates = [yd] if yd is not None else []
    has_kids = st.selectbox(
        "자녀(태아 포함) — 세대별 주민등록표에 등재된 미성년 자녀", ["없음", "있음"],
        index=1 if preset_dates else 0)
    children_birth_dates = []
    if has_kids == "있음":
        n_children = int(st.number_input(
            "자녀 수", min_value=1, max_value=8, value=max(1, len(preset_dates))))
        for i in range(n_children):
            default_d = preset_dates[i] if i < len(preset_dates) else date.today()
            children_birth_dates.append(st.date_input(
                f"자녀 {i + 1} 생년월일(태아는 출산예정일)", value=default_d,
                min_value=date(1990, 1, 1), max_value=date.today() + timedelta(days=300),
                key=f"child_date_{i}"))
    st.caption("출생자녀 가산은 공고문 기준대로 자동 계산합니다: 2023.3.28. 이후 출생(입양·태아 포함) "
               "자녀가 1명이라도 있으면 그 이전에 태어난 기존 미성년 자녀도 합산해 최대 2명, "
               "이후 출생 자녀가 없으면 0명입니다. 가산 기준일 이후 출생 여부와 미성년 여부는 "
               "선택한 공고의 공고일로 판단합니다.")

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

if st.button("판정하기", type="primary"):
    st.session_state["judged"] = True

if st.session_state.get("judged"):
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
        dual_income=dual_income,
        is_social_rookie=is_social_rookie,
        student_status=student_status,
        grad_or_dropout_date=grad_or_dropout_date,
        marriage_date=marriage_date,
        children_birth_dates=children_birth_dates,
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
                       f"이미 INELIGIBLE·MANUAL_REVIEW·NEEDS_INFO 상태입니다).")

        if exp.matched:
            st.subheader("충족한 조건")
            for item in exp.matched:
                st.markdown(f"- {item.description} _(근거: {item.source_ref})_")

        if exp.failed:
            st.subheader("충족하지 못한 조건")
            for item in exp.failed:
                st.markdown(f"- {item.description} _(근거: {item.source_ref})_")

        if exp.review:
            st.subheader("자동 확정이 어려운 조건 (수동 확인 필요)")
            st.caption("정보를 더 입력해도 해결되지 않는 항목입니다. 사유가 `INPUT_INCONSISTENT`이면 입력(가구원수·자녀 등)을 "
                       "고쳐 다시 판정하세요. 그 밖에는 원문 해석이 갈리거나 자기신고로만 처리하는 항목이라 "
                       "LH 청약플러스·고객센터 등으로 직접 확인해야 합니다.")
            for item in exp.review:
                st.markdown(f"- {item.description} _(근거: {item.source_ref})_")
                st.caption(f"사유 `{item.code}`: {item.detail}")

        if exp.unknown:
            st.subheader("추가로 입력하면 판정할 수 있는 조건")
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
        "- 원문 표에 없는 조합(예: 대학생·청년 2인 가구 + 출생자녀)이나 해석이 갈리는 조건은 "
        "임의로 통과/탈락시키지 않고 '수동 확인 필요(MANUAL_REVIEW)'로 표시합니다 — 자세한 "
        "내용은 docs/rule-coverage-matrix.md를 참고하세요.\n"
        "- 번동3(N3)의 혼인기간·자녀연령 기준일은 원문에 날짜가 없어 N1 원문과 같은 공식으로 "
        "공고일에서 도출했습니다.\n"
        "- 최종 신청 전 반드시 LH 청약플러스 원문 공고문으로 재확인하시기 바랍니다."
    )
