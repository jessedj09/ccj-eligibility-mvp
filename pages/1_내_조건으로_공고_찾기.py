# -*- coding: utf-8 -*-
"""내 조건으로 공고 찾기 — 한 번 입력해 공고 26건의 모든 계층을 판정한다(D 단계).

판정은 src/matcher.py가 하고(같은 질문의 계층별 뜻은 rules/reference/input_scope.json), 이 화면은 입력과 표시만 한다.
"""
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from explainability import explain  # noqa: E402
from matcher import MasterProfile, match_all, missing_inputs  # noqa: E402
from profile_form import widget_state  # noqa: E402
from profile_io import ProfileFormatError, master_from_dict, master_to_dict  # noqa: E402
from notices_data import ALL_NOTICES  # noqa: E402
from rule_data import REGION_NONE, region_groups  # noqa: E402
from schedule import CLOSED, KST, OPEN, UPCOMING, load_schedules, now_kst, statuses  # noqa: E402
import whatif  # noqa: E402
from display_status import COMMON_NOTE  # noqa: E402

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
    known = st.checkbox(f"{label} 입력", key=f"{key}_known")
    return st.number_input(label, min_value=0, step=100_000, key=key, help=help, disabled=not known) if known else None


def region(label, key):
    v = st.selectbox(label, REGIONS, key=key, format_func=lambda n: f"경기 {n}" if GROUP_OF.get(n) == "경기도" else n)
    return None if v == UNKNOWN else v


with st.expander("📂 저장한 내 조건 불러오기 · 저장 안내"):
    st.caption("입력한 조건은 서버에 저장하지 않습니다(소득·자산 같은 개인정보). 아래 '내 조건 파일로 저장'으로 내려받은 파일을 "
               "여기서 다시 불러오면 입력란이 채워집니다. 같은 파일을 판정 API(/match)에 그대로 보낼 수도 있습니다.")
    up = st.file_uploader("내 조건 파일(.json)", type=["json"], key="m_upload")
    if up is not None and st.session_state.get("m_loaded") != up.file_id:
        try:
            # 위젯이 만들어지기 전에 session_state에 넣는다
            st.session_state.update(widget_state(master_from_dict(json.loads(up.getvalue().decode("utf-8"))), UNKNOWN))
            st.session_state["m_loaded"] = up.file_id
            st.rerun()
        except (ProfileFormatError, ValueError, UnicodeDecodeError) as e:
            st.error(f"불러오지 못했습니다: {e}")
    elif up is not None:
        st.success("불러온 조건으로 입력란을 채웠습니다. 필요하면 고친 뒤 판정하세요.")


# 기본값은 session_state에 둔다 — 위젯에 value=를 주면 불러오기(session_state로 값 넣기)와 충돌 경고가 난다
for _k, _v in (("m_birth", date(1996, 1, 1)), ("m_marriage", date(2022, 1, 1)), ("m_size", 1), ("m_kids", 0)):
    st.session_state.setdefault(_k, _v)

col1, col2, col3 = st.columns(3)
with col1:
    st.subheader("기본")
    birth = st.date_input("생년월일", min_value=date(1920, 1, 1), max_value=date.today(),
                          key="m_birth", help="공고마다 공고일 기준 만 나이로 계산합니다.")
    marital = st.selectbox("혼인 상태", ["미혼", "혼인중", "예비신혼", "한부모"], key="m_marital")
    marriage_date = None
    if marital == "혼인중":
        marriage_date = st.date_input("혼인신고일", min_value=date(1970, 1, 1),
                                      max_value=date.today(), key="m_marriage")
    size = st.number_input("가구원수(무주택세대구성원 전원, 태아 포함)", min_value=1, max_value=10, key="m_size",
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
    n_kids = st.number_input("세대별 주민등록표에 등재된 미성년 자녀 수(태아 포함)", min_value=0, max_value=8, key="m_kids")
    for i in range(int(n_kids)):
        st.session_state.setdefault(f"m_kid_{i}", date(2024, 1, 1))
    kids = [st.date_input(f"자녀 {i + 1} 생년월일(태아는 출산예정일)", min_value=date(1990, 1, 1),
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

b1, b2 = st.columns([1, 3])
with b1:
    if st.button("전체 공고 판정", type="primary", key="m_run"):
        st.session_state["m_judged"] = True
with b2:
    st.download_button("💾 내 조건 파일로 저장", key="m_save", file_name="내조건.json", mime="application/json",
                       data=json.dumps(master_to_dict(master), ensure_ascii=False, indent=2),
                       help="이 기기에 파일로만 저장됩니다. 다음에 위 '저장한 내 조건 불러오기'로 다시 채울 수 있습니다.")

if st.session_state.get("m_judged"):
    all_matches = match_all(master, ALL_NOTICES)

    # D2: 접수 상태 — 자격 판정과 별개로, 기준 시각에 접수 중·예정인 공고만 볼 수 있다.
    st.subheader("접수 상태")
    s1, s2 = st.columns([1, 2])
    with s1:
        today = now_kst().date()
        on = st.date_input("기준일", value=today, key="m_at",
                           help="오늘이면 지금 시각, 다른 날이면 그날 12:00(한국 시간) 기준으로 접수 상태를 봅니다.")
    with s2:
        view = st.radio("보기", ["접수 중·예정 공고만", "전체 공고(마감 포함)"], key="m_view", horizontal=True)
    at = now_kst() if on == today else datetime.combine(on, time(12, 0), tzinfo=KST)
    stat = statuses(list(ALL_NOTICES), at)
    count = {c: sum(1 for s in stat.values() if s.code == c) for c in (OPEN, UPCOMING, CLOSED)}
    st.caption(f"{at:%Y.%m.%d. %H:%M} 기준 — 🟢 접수 중 {count[OPEN]}건 · 🗓️ 접수 예정 {count[UPCOMING]}건 · "
               f"⚫ 마감 {count[CLOSED]}건 (보유 공고 {len(ALL_NOTICES)}건, 접수기간은 공고문 원문 기준)")
    only_open = view.startswith("접수 중")
    matches = [x for x in all_matches if not only_open or stat[x.notice.notice_id].applicable]
    if only_open and not matches:
        st.info("이 기준일에 접수 중이거나 접수 예정인 공고가 없습니다 — 보유한 공고는 모두 접수가 끝났습니다. "
                "'전체 공고(마감 포함)'로 바꾸면 마감된 공고의 판정 결과도 볼 수 있고, 새 공고가 추가되면 여기에 표시됩니다.")
    order = {OPEN: 0, UPCOMING: 1, CLOSED: 2}
    matches.sort(key=lambda x: (order.get(stat[x.notice.notice_id].code, 3),
                                stat[x.notice.notice_id].window.start if stat[x.notice.notice_id].window else at))
    by = {v: [x for x in matches if x.verdict == v] for v in ("ELIGIBLE", "MANUAL_REVIEW", "NEEDS_INFO", "INELIGIBLE")}
    # 화면은 지원 가능 / 보류 / 지원 불가 3상태(PRD v2.1 F18) — 보류는 원인(추가 정보 필요·수동 확인 필요)을 나눠 보인다
    hold = len(by["NEEDS_INFO"]) + len(by["MANUAL_REVIEW"])
    m1, m2, m3 = st.columns(3)
    m1.metric("✅ 지원 가능", len(by["ELIGIBLE"]))
    m2.metric("🟡 보류", hold)
    m3.metric("❌ 지원 불가", len(by["INELIGIBLE"]))
    st.caption(f"보류 {hold}건 = ⚠️ 추가 정보 필요 {len(by['NEEDS_INFO'])}건(더 입력하면 판정) · "
               f"🔍 수동 확인 필요 {len(by['MANUAL_REVIEW'])}건(원문·기관 확인). 공고·계층(주택형) 단위로 셉니다. "
               "신청 자격(필수요건)만 판정하며 순위·가점·추첨·당첨은 포함하지 않습니다. "
               "접수 일정은 공고 이후 바뀔 수 있으니 신청 전 원문과 공지사항을 확인하세요.")

    need = missing_inputs(matches)
    if need:
        st.info("이 정보를 더 입력하면 판정할 수 있는 공고가 늘어납니다: "
                + ", ".join(f"**{k}**({v}건)" for k, v in list(need.items())[:6]))

    def row(x, expanded=False):
        n = x.notice
        tracks = f" · 충족: {', '.join(x.result.eligible_tracks)}" if x.result.eligible_tracks else ""
        head_line = f"{n.notice_id} {n.title} — **{x.layer}**{tracks}"
        s = stat[n.notice_id]
        with st.expander(f"{s.text.split(' — ')[0]} | {n.meta.get('issuer', '')} {n.meta.get('program', '')} | "
                         f"{n.title} · {x.layer}", expanded=expanded):
            st.markdown(head_line)
            st.caption(f"{s.text} (공고일 {n.announcement_date})")
            sched = load_schedules().get(n.notice_id)
            if sched and len(sched.windows) > 1:
                st.caption("접수 일정: " + " / ".join(f"{w.label} {w.start:%m.%d.} {w.start:%H:%M}~{w.end:%m.%d.} {w.end:%H:%M}"
                                                    for w in sched.windows))
            if sched and sched.note:
                st.caption(f"🗓️ {sched.note}")
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

    st.caption(COMMON_NOTE)
    for verdict, title in (("ELIGIBLE", "✅ 지원 가능"), ("NEEDS_INFO", "🟡 보류 — ⚠️ 추가 정보 필요(더 입력하면 판정)"),
                           ("MANUAL_REVIEW", "🟡 보류 — 🔍 수동 확인 필요(원문·기관 확인)"), ("INELIGIBLE", "❌ 지원 불가")):
        if not by[verdict]:
            continue
        st.subheader(f"{title} ({len(by[verdict])})")
        items = by[verdict]
        if verdict == "INELIGIBLE":
            with st.expander(f"지원 불가 {len(items)}건 펼쳐 보기"):
                for x in items:
                    exp = explain(x.result, x.notice)
                    reason = exp.failed[0].description if exp.failed else ""
                    st.caption(f"{stat[x.notice.notice_id].text.split(' — ')[0]} {x.notice.notice_id} "
                               f"{x.notice.title} · {x.layer} — {reason}")
        else:
            for x in items:
                row(x)

    # ---- What-if (PRD v2.1 F19): 무엇을 바꾸면 지원 가능해지나 — 판정은 같은 엔진, 입력만 바꿔 다시 판정 ----
    st.divider()
    st.subheader("🔀 What-if — 무엇을 바꾸면 지원 가능해지나")
    st.caption(whatif.CAVEAT)
    keep = (lambda x: stat[x.notice.notice_id].applicable) if only_open else None
    if only_open and not matches:
        st.info("지금 접수 중·예정인 공고가 없어 비교할 대상이 없습니다. 위 '보기'에서 '전체 공고(마감 포함)'를 고르면 "
                "마감된 공고로 비교해 볼 수 있습니다.")
    tab_near, tab_scn = st.tabs(["조건 하나만 부족한 공고", "시나리오로 비교"])
    with tab_near:
        near = whatif.near_misses(master, matches)
        if not near:
            st.info("걸린 조건이 하나뿐인 '지원 불가' 공고가 없습니다.")
        else:
            st.caption(f"'지원 불가' 중 걸린 조건이 하나뿐인 공고·계층 {len(near)}건 — 금액 한도로 풀 수 있는 것부터 보입니다. "
                       "한도는 판정 엔진으로 직접 확인한 값(원 단위)입니다.")
            for n in near[:40]:
                x = n.match
                st.markdown(f"**{x.notice.notice_id} {x.notice.title} · {x.layer}** — 이 조건만 해결되면 **{n.after}**")
                st.caption(f"걸린 조건: {n.description}")
                for t in n.thresholds:
                    band = (f", {t.review_limit:,}원 이하면 수동 확인(원문 해석에 따라 다름)" if t.review_limit else "")
                    st.caption(f"💡 {t.label}({t.scope}) 현재 {t.current:,}원 → **{t.limit:,}원 이하**면 이 조건 충족 "
                               f"(차이 {t.gap:,}원){band}")
    with tab_scn:
        scenario = st.radio("시나리오", ["혼인신고를 하면", "예비신혼부부로 신청하면", "거주지를 옮기면", "세대를 분리하면"],
                            key="w_scn", horizontal=True)
        change = None
        if scenario in ("혼인신고를 하면", "예비신혼부부로 신청하면"):
            st.caption("가정: 본인·배우자(·본인 자녀)로 새 세대를 꾸리고(부모 세대에서 분리) 같은 곳에 삽니다. "
                       "세대 소득·자산은 본인+배우자, 주택은 둘 중 하나라도 있으면 보유로 봅니다.")
            w1, w2 = st.columns(2)
            with w1:
                w_date = (st.date_input("혼인신고일", value=now_kst().date(), key="w_mdate")
                          if scenario == "혼인신고를 하면" else None)
                w_sp_unknown = st.checkbox("배우자 소득·자산 모름", key="w_sp_unknown")
                w_sp_income = None if w_sp_unknown else st.number_input("배우자 월평균소득(원)", min_value=0, step=100_000,
                                                                       key="w_sp_inc")
            with w2:
                w_sp_assets = None if w_sp_unknown else st.number_input("배우자 총자산(원)", min_value=0, step=1_000_000,
                                                                       key="w_sp_ast")
                w_sp_car = None if w_sp_unknown else st.number_input("배우자 자동차가액(원, 없으면 0)", min_value=0,
                                                                    step=1_000_000, key="w_sp_car")
                w_sp_home = st.checkbox("배우자가 주택 보유", key="w_sp_home")
                w_dual = st.checkbox("맞벌이(본인·배우자 모두 소득)", key="w_dual")
            change = lambda m: whatif.marry(m, w_date, w_sp_income, w_sp_assets, w_sp_car, w_sp_home, w_dual,  # noqa: E731
                                            prenuptial=scenario == "예비신혼부부로 신청하면")
        elif scenario == "거주지를 옮기면":
            w_region = st.selectbox("옮길 거주지(주민등록)", [r for r in REGIONS if r not in (UNKNOWN, REGION_NONE)],
                                    key="w_region", format_func=lambda n: f"경기 {n}" if GROUP_OF.get(n) == "경기도" else n)
            change = lambda m: whatif.move(m, w_region)  # noqa: E731
        else:
            st.caption("가정: 부모 세대에서 분리해 본인(과 본인 자녀)으로 세대를 꾸리고 세대주가 됩니다. 세대 소득·자산·주택은 "
                       "본인 것만 봅니다(대학생 계층의 부모 소득은 등본과 무관하게 계속 합산).")
            change = whatif.separate_household
        if st.button("이 시나리오로 다시 판정", key="w_run"):
            st.session_state["w_done"] = True
        if st.session_state.get("w_done"):
            res = whatif.run_scenario(scenario, master, change, ALL_NOTICES, keep=keep)
            c1, c2, c3 = st.columns(3)
            for col, k, label in ((c1, "ELIGIBLE", "✅ 지원 가능"), (c2, "HOLD", "🟡 보류"), (c3, "INELIGIBLE", "❌ 지원 불가")):
                col.metric(label, res.after[k], delta=res.after[k] - res.before[k])
            st.caption(f"'{scenario}' 전후 비교 — 지금 {res.before['ELIGIBLE']}건 → {res.after['ELIGIBLE']}건 지원 가능"
                       + (" (접수 중·예정 공고만)" if only_open else ""))
            if res.gained:
                st.markdown(f"**새로 지원 가능 {len(res.gained)}건**")
                for x in res.gained:
                    st.caption(f"✅ {x.notice.notice_id} {x.notice.title} · {x.layer}")
            if res.lost:
                st.markdown(f"**지원 가능에서 빠지는 {len(res.lost)}건**")
                after = {(y.notice.notice_id, y.layer): y for y in match_all(change(master), ALL_NOTICES)}
                for x in res.lost:
                    y = after[(x.notice.notice_id, x.layer)]
                    why = explain(y.result, y.notice)
                    reason = why.failed[0].description if why.failed else why.headline
                    st.caption(f"❌ {x.notice.notice_id} {x.notice.title} · {x.layer} — {reason}")
            if not res.gained and not res.lost:
                st.info("이 시나리오로는 지원 가능한 공고가 바뀌지 않습니다.")
