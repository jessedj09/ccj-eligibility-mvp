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
from rule_data import REGION_NONE, region_groups
from explainability import explain
from profiles_data import PROFILES
from schedule import load_schedules, status as schedule_status
from display_status import COMMON_NOTE, display, display_checks
from form_spec import C4_AMOUNTS, C4_BOOLS, C4_CHOICES, CHOICE_FIELDS, REGION_LABELS
from notice_identify import REGISTERED, SAME_NOTICE_OTHER_FILE, UNREGISTERED, identify_pdf
from upload_view import render_auto, render_draft, render_draft_refused, render_identified, render_not_judgeable
from operator_mode import auto_judge_public, sidebar_gate

REVIEW_BADGE = {
    "DRAFT": ("🟠 초안(DRAFT)", "규칙을 만든 쪽 외의 독립 검토를 아직 거치지 않았습니다. 참고용으로만 쓰세요."),
    "REVIEWED": ("🟡 검토됨(REVIEWED)", "독립 검토를 마쳤으나 아직 공개 확정 전입니다."),
    "PUBLISHED": ("🟢 확정(PUBLISHED)", "독립 검토를 마치고 공개 확정된 규칙입니다."),
    "RETIRED": ("⚪ 폐기(RETIRED)", "더 이상 쓰지 않는 규칙입니다."),
}

st.set_page_config(page_title="주거·복지 Eligibility 데모", page_icon="🏠")
st.title("🏠 주거·복지 Eligibility 판정 데모")
st.caption(f"LH·SH 공공임대 공고 {len(ALL_NOTICES)}건(행복주택·매입임대·든든전세·미리내집·장기전세 등)의 신청 자격을 "
           "공고문 원문 기준으로 판정합니다 — 판정은 결정론적 Rule Engine이 수행합니다. 공고는 목록에서 고르거나 공고문 PDF를 "
           "올려 고를 수 있습니다. 여러 공고를 한 번에 보려면 왼쪽 메뉴 '내 조건으로 공고 찾기'를 쓰세요. (지원 범위는 하단 안내 참조)")

PRESETS = {profile.profile_id: (profile, layer) for profile, layer in PROFILES}

VERDICT_STYLE = {
    "ELIGIBLE": ("✅", "success"),
    "INELIGIBLE": ("❌", "error"),
    "NEEDS_INFO": ("⚠️", "warning"),
    "MANUAL_REVIEW": ("🔍", "warning"),
    "NOT_OFFERED": ("➖", "info"),
}

main_notice = st.empty()   # 미지원 계층을 고르면 본문 맨 위에 안내를 띄우는 자리
upload_area = st.container()   # 공고문 PDF를 올렸을 때 식별 결과(본문 맨 위)


def _identify_upload(up):
    """올린 파일을 한 번만 읽는다(파일마다 session_state에 식별 결과를 둔다). 파일 자체는 저장하지 않는다."""
    done = st.session_state.setdefault("upload_ident", {})
    if up.file_id not in done:
        with st.spinner("공고문을 읽는 중입니다…"):
            done[up.file_id] = identify_pdf(up.getvalue())
    return done[up.file_id]


def _draft_upload(up, ident):
    """미등록 공고의 자동 분석(src/draft.py — 합격 사업만, AI 없음). 파일마다 한 번만 만든다.
    같은 공고를 이미 분석했으면 공유 저장소의 결과를 쓴다(src/analysis.py — 저장소가 없어도 결과는 같다)."""
    import analysis   # 추출기(tools/)는 자동 판정을 쓸 때만 불러온다 — 공개 화면의 시작 시간·실패 범위를 늘리지 않게
    done = st.session_state.setdefault("upload_draft", {})
    if up.file_id not in done:
        with st.spinner("공고문을 자동으로 분석하는 중입니다…"):
            done[up.file_id] = analysis.analyze(up.getvalue(), ident)
    return done[up.file_id]


operator = sidebar_gate()
auto_public = auto_judge_public()   # v3 자동 판정을 일반 사용자에게 열었는가(기본 꺼짐 — 베타 공개 기준 충족 후 켬)
current_draft = None   # 자동 분석한 초안(있으면 등록 규칙 대신 이것으로 판정)

with st.sidebar:
    st.header("공고 · 계층 선택")
    pick_mode = st.radio("공고 고르는 방법", ["목록에서 고르기", "공고문 PDF 올리기"], key="pick_mode", horizontal=True)
    if pick_mode == "공고문 PDF 올리기":
        # 주요 기능1 기본형(P0, docs/09): 업로드 → 등록 공고 식별 → 등록 공고면 그 공고로 판정, 아니면 판정하지 않고 안내
        up = st.file_uploader("공고문 PDF", type=["pdf"], key="notice_pdf",
                              help="LH 청약플러스·SH 인터넷청약에서 내려받은 입주자모집공고문 PDF. 올린 파일은 저장하지 않습니다.")
        if up is None:
            upload_area.info("왼쪽에서 공고문 PDF를 올리면 등록된(검증된) 공고인지 확인하고, 맞으면 바로 판정합니다.")
            st.stop()
        ident = _identify_upload(up)
        if ident.status == REGISTERED:
            notice_id = ident.notice_id
        elif ident.status == SAME_NOTICE_OTHER_FILE:
            confirmed = st.checkbox(f"등록 공고 {ident.notice_id} 원문 기준으로 판정하기", key=f"confirm_{up.file_id}",
                                    help="같은 공고를 다시 내려받은 파일이면 결과가 같습니다. 정정 공고면 다를 수 있습니다.")
            if not confirmed:
                with upload_area:
                    st.info(f"📄 {ident.reason} 같은 공고가 맞으면 왼쪽의 '원문 기준으로 판정하기'를 체크하세요.")
                st.stop()
            notice_id = ident.notice_id
        else:
            d = _draft_upload(up, ident) if (operator or auto_public) and ident.status == UNREGISTERED else None
            if d is None or d.notice is None:   # 자동 판정을 열지 않았거나 판정 불가(대상 아닌 사업·핵심 빈칸 보류 등)
                with upload_area:
                    render_not_judgeable(ident)
                    if d is not None and operator:
                        render_draft_refused(d)
                st.stop()
            current_draft, notice_id = d, d.notice.notice_id
        with upload_area:
            if current_draft is not None:
                (render_draft if operator else render_auto)(current_draft, ident)
            else:
                render_identified(ident)
    else:
        notice_id = st.selectbox(
            "공고", options=list(ALL_NOTICES.keys()),
            format_func=lambda nid: f"{nid} — {ALL_NOTICES[nid].title}",
        )
    notice = current_draft.notice if current_draft is not None else ALL_NOTICES[notice_id]
    program = " · ".join(x for x in (notice.meta.get("issuer"), notice.meta.get("program")) if x)
    st.caption(f"{program + ' / ' if program else ''}입주자모집공고일: {notice.announcement_date} "
               f"(혼인기간·자녀연령·졸업경과 등은 이 날짜 기준으로 계산합니다)")
    sched_status = schedule_status(notice_id)
    st.caption(f"청약 접수: **{sched_status.text}** (한국 시간, 공고문 원문 기준)")
    sched = load_schedules().get(notice_id)
    if sched and sched.note:
        st.caption(f"🗓️ {sched.note}")
    if current_draft is not None:
        import grading
        if operator:
            labels = ", ".join(f"{k} {grading.GRADE_LABEL[g.grade]}" for k, g in grading.grades(current_draft).items())
            st.caption(f"규칙 검수 상태: **🟠 자동 분석(운영자 보기)** — 계층 등급: {labels}")
        if grading.layers_may_be_missing(current_draft):
            st.caption("이 공고의 일부 계층(주거약자형 등)은 자동으로 읽지 못했을 수 있습니다 — 목록에 없는 계층은 공고 원문을 확인하세요.")
    else:
        label, hint = REVIEW_BADGE[notice.meta["review"]["status"]]
        st.caption(f"규칙 검수 상태: **{label}** — {hint}")
    unsupported = {u["name"]: u for u in notice.meta.get("unsupported_layers", [])}
    layer = st.selectbox(
        "계층", options=list(notice.layers.keys()) + list(unsupported),
        format_func=lambda name: f"{name} (아직 지원 안 함)" if name in unsupported else name,
    )
    if layer in unsupported:
        u = unsupported[layer]
        where = f" (공고문 p.{u['page']})" if u.get("page") else ""
        main_notice.info(f"**{layer}** 계층은 이 공고에 있지만{where} 아직 판정을 지원하지 않습니다. "
                         f"{u['note']}")
        st.stop()

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


for note in notice.meta.get("notes", []):
    st.caption(f"📌 {note}")

def scope_caption(field):
    """같은 입력이라도 계층마다 뜻이 다르다(예: 주택 소유 — 대학생은 본인, 신혼부부는 세대 전원). 선택한 계층에서
    이 입력을 읽는 조건의 설명(규칙 데이터의 note)을 입력란 아래에 그대로 보여 준다."""
    notes = []
    for c in notice.layers[layer].conditions:
        if field in c.inputs and c.note not in notes:
            notes.append(c.note)
    if notes:
        st.caption("이 계층 기준: " + " / ".join(notes))


col1, col2 = st.columns(2)
with col1:
    # 나이는 공고일 기준 만 나이다. 생년월일로 받으면 생일 경계(하루 차이)를 엔진 쪽에서 정확히 계산한다.
    age_mode = st.radio("나이 입력 방식", ["생년월일", "만 나이"], horizontal=True,
                        index=0 if preset_profile is None else 1)
    if age_mode == "생년월일":
        birth_date = st.date_input("생년월일", value=date(1996, 1, 1), min_value=date(1900, 1, 1),
                                   max_value=date.today(), key="birth_date")
        ann = notice.announcement_date
        age = ann.year - birth_date.year - ((ann.month, ann.day) < (birth_date.month, birth_date.day))
        st.caption(f"공고일({ann}) 기준 만 {age}세로 판정합니다.")
    else:
        age = st.number_input("나이(공고일 기준 만 나이)", min_value=0, max_value=120, value=_default("age", 30))
    scope_caption("age")
    marital_status = st.selectbox(
        "혼인 상태", options=["미혼", "혼인중", "예비신혼", "한부모"],
        index=["미혼", "혼인중", "예비신혼", "한부모"].index(_default("marital_status", "미혼")),
    )
    home_ownership = st.selectbox(
        "주택 소유", options=["무주택", "주택보유"],
        index=["무주택", "주택보유"].index(_default("home_ownership", "무주택")),
    )
    scope_caption("home_ownership")
    household_size = st.number_input(
        "가구원수(판정 대상)", min_value=1, max_value=10, value=_default("household_size", 1),
        help="신혼부부는 부부 2인 이상입니다. 예비신혼부부는 신청자 본인과 예비배우자, 공고일 기준 동일 세대에 "
             "등재된 직계존속·비속을 포함한 '혼인으로 구성될 세대' 기준이며 2인 이상입니다. "
             "한부모는 본인과 자녀를 포함합니다.",
    )
    dual_income = st.checkbox("맞벌이 여부", value=_default("dual_income", False))

    layer_inputs = notice.layers[layer].inputs
    house_head_status = None
    if "house_head_status" in layer_inputs:
        hh = st.selectbox(
            "세대주/세대원 (등본 기준)", options=["모름(미확인)", "세대주", "세대원"],
            index=["모름(미확인)", "세대주", "세대원"].index(
                _default("house_head_status", None) or "모름(미확인)"),
        )
        house_head_status = None if hh == "모름(미확인)" else hh

    is_social_rookie = None
    if "is_social_rookie" in layer_inputs:
        rookie = st.selectbox(
            "사회초년생 해당 여부(19~39세가 아닐 때만 의미 있음)",
            options=["모름", "예", "아니오"],
            index=["모름", "예", "아니오"].index(
                {True: "예", False: "아니오", None: "모름"}[_default("is_social_rookie", None)]),
        )
        is_social_rookie = {"모름": None, "예": True, "아니오": False}[rookie]

    student_status, grad_or_dropout_date = None, None
    if "student_status" in layer_inputs:
        options = ["모름", "재학중", "입학예정", "복학예정", "취업준비생"]
        student_status_label = st.selectbox(
            "재학 상태", options=options,
            index=options.index(_default("student_status", None) or "모름"),
        )
        student_status = None if student_status_label == "모름" else student_status_label
    if "grad_or_dropout_date" in layer_inputs and (
            student_status == "취업준비생" or "student_status" not in layer_inputs):
        grad_or_dropout_date = st.date_input(
            "대학·고등학교 졸업(또는 중퇴)일",
            value=_default("grad_or_dropout_date", None) or date.today(),
            min_value=date(1990, 1, 1), max_value=date.today(),
        )

    marriage_date = None
    if "marriage_date" in layer_inputs and marital_status == "혼인중":
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
    scope_caption("monthly_income")
    total_assets = _amount_input("총자산(원)", "total_assets", "assets_input")
    scope_caption("total_assets")
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

# 지역 — 선택한 공고·계층의 조건이 지역 필드를 읽을 때만 묻는다(예: 1순위 지역만 모집하는 공고)
# 항목 이름·선택지는 src/form_spec.py 한 곳에 둔다(공개 화면 Next.js도 판정 API /form으로 같은 정의를 받는다)
region_fields = [f for f in REGION_LABELS if f in notice.layers[layer].inputs]
regions = {}
if region_fields:
    st.subheader("지역")
    st.caption("이 공고는 순위 지역(서울특별시·연접 시 등)이 신청 자격을 가릅니다. 시·군 단위로 골라 주세요. "
               "'해당없음'은 그런 곳이 없다는 뜻입니다(예: 소득이 없어 소득 근거지가 없음, 대학생이 아님).")
    region_options = ["모름", REGION_NONE] + [n for names in region_groups().values() for n in names]
    group_of = {n: g for g, names in region_groups().items() for n in names}
    for f in region_fields:
        choice = st.selectbox(
            REGION_LABELS[f], options=region_options, key=f"region_{f}",
            format_func=lambda n: f"경기 {n}" if group_of.get(n) == "경기도" else n,
        )
        regions[f] = None if choice == "모름" else choice

# 계층 전용 선택 항목 — 선택한 계층의 조건이 읽을 때만 묻는다(C3: 산업단지근로자·주거급여수급자·지역전략산업종사자)
choice_fields = [f for f in CHOICE_FIELDS if f in notice.layers[layer].inputs]
choices = {}
if choice_fields:
    st.subheader(f"{layer} 요건")
    for f in choice_fields:
        label, opts = CHOICE_FIELDS[f]
        picked = st.selectbox(label, options=["모름"] + opts, key=f"choice_{f}")
        choices[f] = None if picked == "모름" else picked
    if "regional_industry_type" in choice_fields:
        st.caption("콘텐츠산업 종사자·부천시 추천자는 신청 후 부천시가 자격을 확인하므로 '수동 확인'으로 표시됩니다.")

# C4(매입임대 등): 복지 자격·부모 정보·취업 여부 — 순위·유형 판정에 쓰는 항목
c4_fields = [f for f in list(C4_CHOICES) + list(C4_BOOLS) + ["parents_count"] + list(C4_AMOUNTS)
             if f in notice.layers[layer].inputs]
if c4_fields:
    st.subheader("추가 자격 정보")
    st.caption("순위·유형마다 필요한 정보가 다릅니다. 모르는 항목은 '모름'으로 두면 그 순위는 '추가 정보 필요'로 표시됩니다.")
    for f in c4_fields:
        if f in C4_CHOICES:
            label, opts = C4_CHOICES[f]
            picked = st.selectbox(label, options=["모름"] + opts, key=f"c4_{f}")
            choices[f] = None if picked == "모름" else picked
        elif f in C4_BOOLS:
            picked = st.selectbox(C4_BOOLS[f], options=["모름", "예", "아니오"], key=f"c4_{f}")
            choices[f] = {"모름": None, "예": True, "아니오": False}[picked]
        elif f == "parents_count":
            picked = st.selectbox("소득·자산 검증대상 부모 수", options=["모름", 0, 1, 2], key="c4_parents_count")
            choices[f] = None if picked == "모름" else int(picked)
        else:
            choices[f] = _amount_input(C4_AMOUNTS[f], f, f"c4_{f}")

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
        **regions,
        **choices,
    )

    errors = validate_profile(profile)
    if errors:
        st.error("입력값을 확인해주세요:")
        for e in errors:
            st.markdown(f"- {e}")
    else:
        checks = []
        if current_draft is not None:   # 자동 분석 공고: 결론이 확실하지 않은 곳에 따라 갈리는 사용자만 보류(v3 ③, src/grading.py)
            import grading
            result, checks = grading.judge(current_draft, profile, layer)
        else:
            result = evaluate(profile, notice, layer)
        exp = explain(result, notice)

        # 화면은 지원 가능 / 보류(원인) / 지원 불가 3상태로 보인다(PRD v2.1 F18). 엔진 판정은 5상태 그대로.
        icon, style = VERDICT_STYLE[exp.verdict]
        shown = display_checks(len(checks)) if checks else display(exp.verdict)
        getattr(st, style)(f"{icon} {shown.title} · {exp.headline}")
        st.caption(shown.todo)
        for c in checks:
            st.markdown(f"- 🔍 {c.text}")
        st.caption(COMMON_NOTE)
        if current_draft is not None and operator:
            from draft import NOTE
            st.caption(f"🟠 {NOTE}")
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

        if exp.tracks:
            st.subheader("순위·유형별 결과")
            ok = exp.eligible_tracks
            st.caption("충족한 순위·유형: " + (", ".join(ok) if ok else "없음")
                       + " — 하나 이상 충족하면 이 조건은 충족입니다(순위는 경쟁 시 선정 순서이며 신청 시 직접 고릅니다).")
            for t in exp.tracks:
                t_icon = VERDICT_STYLE[t.verdict][0]
                st.markdown(f"- {t_icon} **{t.track_id}** — {t.label}")
                for item in t.failed:
                    st.caption(f"　불충족: {item.description} (근거: {item.source_ref})")
                for item in t.unknown:
                    st.caption(f"　정보 필요: {item.description}")
                for item in t.review:
                    st.caption(f"　수동 확인: {item.description} — {item.detail}")

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
        "- 신청 자격(필수요건)만 판정합니다. 서류심사, 경쟁 시 선정(순위·추첨·배점), 최종 당첨 여부는 계산하지 않습니다. "
        "순위·유형이 있는 공고는 충족한 순위·유형을 함께 보여 주지만, 그 순위 안의 경쟁 결과는 알 수 없습니다.\n"
        "- 우선공급 배점(청약저축 납입횟수 등)은 이 화면에서 산출하지 않습니다.\n"
        "- 공통 결격사유(다른 공공임대 중복 입주·불법 전대 이력 등)와 신혼희망타운 우선공급의 지역 자격은 판정하지 않고 "
        "공고 유의사항으로만 안내합니다.\n"
        "- 접수기간은 공고문 원문 기준이며 공고 후 바뀔 수 있습니다.\n"
        "- 청년계층 '사회초년생' 세부요건(소득활동기간 5년 이내, 예술인 인증 등 증빙)은 "
        "자기신고 사실로만 처리하며 세부 증빙을 검증하지 않습니다.\n"
        "- 원문 표에 없는 조합(예: 대학생·청년 2인 가구 + 출생자녀)이나 해석이 갈리는 조건은 "
        "임의로 통과/탈락시키지 않고 '수동 확인 필요(MANUAL_REVIEW)'로 표시합니다 — 자세한 "
        "내용은 docs/rule-coverage-matrix.md를 참고하세요.\n"
        "- 번동3(N3)의 혼인기간·자녀연령 기준일은 원문에 날짜가 없어 N1 원문과 같은 공식으로 "
        "공고일에서 도출했습니다.\n"
        "- 최종 신청 전 반드시 LH 청약플러스·SH 인터넷청약의 원문 공고문으로 재확인하시기 바랍니다."
    )
