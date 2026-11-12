# -*- coding: utf-8 -*-
"""운영자 검토(C8) — 운영자 화면 첫 화면(app.py가 메뉴를 정한다, 2026-11-12). 공유 저장소(Neon)의 작업 대기열·사업별 자동 판정 상태·이용 집계를 본다.

- 잠금: 운영자 모드(src/operator_mode.py — Cloud는 로그인 이메일, 운영자 PC는 비밀번호)가 켜져 있어야 보인다.
- 자동 분석이 넘긴 공고(review·register·enhance)를 보고, PDF를 내려받아 docs/08 절차로 등록하거나, 판정할 수 없는 공고는 사유와 함께
  닫는다. 사업별 자동 판정은 B2 비교에서 위험이 나오면 저절로 멈추고(tools/draft_compare.py --record), 다시 켜는 것은 여기서만.
- 지금 모집 중인 공고(공공데이터포털 수집, docs/12): 판정 틀이 있는데 분석 전인 공고를 찾아 공고문을 올린다.
- 판정 로직 없음. 사용자 조건·판정 결과는 저장소에 없다(이용 집계는 날짜별 건수만).
"""
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import draft  # noqa: E402
from operator_mode import sidebar_gate  # noqa: E402
from store import NullStore, get_store  # noqa: E402

st.set_page_config(page_title="운영자 검토", page_icon="🔧", layout="wide")
st.title("🔧 운영자 검토")

if not sidebar_gate(always=True):
    st.info("운영자 전용 화면입니다. Streamlit Cloud에서는 운영자 이메일(secrets `operator_emails`)로 로그인하면 바로 열리고, "
            "운영자 PC에서는 왼쪽에 운영자 비밀번호를 넣으세요.")
    st.stop()

store = get_store()
if type(store) is NullStore:
    st.warning("공유 저장소(DATABASE_URL)에 접속할 수 없습니다 — 운영자 PC의 .streamlit/secrets.toml을 확인하세요.")
    st.stop()

KIND_LABEL = {"review": "운영자 검토", "register": "등록", "enhance": "보강(LLM 작업기)", "reference": "기준표 후보(연도 전환)"}
STATUS_LABEL = {"pending": "대기", "running": "진행 중", "done": "완료", "failed": "실패·닫음"}

# ---- 1. 사업별 자동 판정 상태 ----
st.subheader("사업별 자동 판정")
st.caption("B2 비교(등록 전에 얼린 초안 ↔ 등록 판정)를 `python tools/draft_compare.py <초안> --record`로 더한다. 위험이 1건이라도 "
           "나오면 그 사업은 저절로 멈추고, 업로드한 사용자에게는 '정확도 점검 중'으로 안내한다. 위험의 원인을 고치고 다시 비교한 뒤에만 다시 켠다.")
rows = {r["program"]: r for r in store.program_health()}
names = dict(zip(draft.PASSING, draft.passing_programs()))
for t in draft.PASSING:
    r = rows.get(t, {})
    paused = bool(r.get("demoted_at"))
    c1, c2, c3 = st.columns([3, 5, 2])
    c1.markdown(f"**{names[t]}**  \n`{t}`")
    c2.caption(f"비교 {r.get('compared', 0):,} · 같음 {r.get('same', 0):,} · 주의 {r.get('cautious', 0):,} · "
               f"**위험 {r.get('danger', 0):,}**" + (f" — 멈춤 {r['demoted_at']:%Y-%m-%d %H:%M}" if paused else " — 판정 중"))
    if paused:
        if c3.button("다시 켜기", key=f"resume_{t}"):
            store.set_demoted(t, False)
            st.rerun()
    elif c3.button("멈추기", key=f"pause_{t}"):
        store.set_demoted(t, True)
        st.rerun()

# ---- 2. 작업 대기열 ----
st.subheader("작업 대기열")
f1, f2 = st.columns(2)
kind = f1.selectbox("종류", ["전체"] + list(KIND_LABEL), format_func=lambda k: KIND_LABEL.get(k, k), key="q_kind")
status = f2.selectbox("상태", ["pending", "전체", "running", "failed", "done"], format_func=lambda s: STATUS_LABEL.get(s, s),
                      key="q_status")
jobs = store.list_jobs(kind=None if kind == "전체" else kind, status=None if status == "전체" else status)
if not jobs:
    st.info("해당하는 작업이 없습니다.")
for j in jobs:
    title = j["title"] or j["program"] or "(사업 미확인)"
    head = (f"#{j['id']} · {KIND_LABEL.get(j['kind'], j['kind'])} · {STATUS_LABEL.get(j['status'], j['status'])} | "
            f"{j['issuer'] or ''} {title} · 공고일 {j['announcement_date'] or '?'}")
    with st.expander(head):
        st.caption(f"원문 지문 `{j['sha256'][:16]}…` · 처음 본 날 {j['first_seen']:%Y-%m-%d %H:%M} · 우선순위 {j['priority']} · "
                   f"시도 {j['attempts']}회" + (f" · 메모: {j['error']}" if j["error"] else ""))
        snap = store.latest_snapshot(j["sha256"])
        if snap:
            st.markdown(f"**자동 분석**: `{snap.get('status')}` · 사업 `{snap.get('template') or '-'}` · {snap.get('reason') or ''}")
            held = {k: v for k, v in (snap.get("held_conditions") or {}).items() if v}
            if held:
                st.caption("보류 조건: " + " / ".join(f"{k}: {', '.join(x.split('-', 1)[-1] for x in v)}" for k, v in held.items()))
            if snap.get("held_fields"):
                st.caption("보류 빈칸: " + ", ".join(snap["held_fields"]))
            for p, t in (snap.get("unclassified") or [])[:8]:
                st.caption(f"미분류 문장 p.{p}: {t[:90]}")
            for line in (snap.get("stale") or [])[:4]:
                st.caption(f"기준 연도 다름: {line}")
        else:
            st.caption("저장된 분석이 없습니다.")
        if j["has_pdf"]:
            if st.button("PDF 불러오기", key=f"pdf_{j['id']}"):
                st.session_state[f"pdf_{j['sha256']}"] = store.get_pdf(j["sha256"])
            data = st.session_state.get(f"pdf_{j['sha256']}")
            if data:
                st.download_button("PDF 내려받기", data, file_name=f"{j['sha256'][:12]}.pdf", mime="application/pdf",
                                   key=f"dl_{j['id']}")
            st.caption("등록: PDF를 `sample_lh/`·`sample_sh/`에 넣고 docs/08 절차대로(등록 전에 `notice_intake.py --save-draft`로 초안을 얼린다).")
            if j["kind"] == "reference" and data:
                if st.button("기준표 후보 만들기", key=f"refc_{j['id']}"):
                    import pdf_tables as P
                    import reference_candidates as R
                    refs = P.load_references()
                    st.session_state[f"refc_{j['sha256']}"] = [(c, R.to_reference(c, refs[c.ref_id], f"업로드 {j['sha256'][:12]}"))
                                                               for c in R.candidates(data, refs=refs)]
                cands = st.session_state.get(f"refc_{j['sha256']}")
                if cands == []:
                    st.caption("후보 없음 — 등록 기준표 칸 구성과 맞는 다른 연도 표를 찾지 못했습니다(원문 확인).")
                for c, doc in cands or []:
                    import json
                    import reference_candidates as R
                    st.text(R.describe(c))
                    st.download_button(f"후보 JSON 내려받기 — {doc['id']}", json.dumps(doc, ensure_ascii=False, indent=1),
                                       file_name=f"{doc['id']}.candidate.json", mime="application/json",
                                       key=f"refdl_{j['id']}_{c.ref_id}")
                st.caption("새 기준표 등록: 후보를 원문과 대조 → docs/08 '새 기준표 등록'(status·candidate 표시를 지우고 successor_of를 남긴 채 "
                           "rules/reference/에 넣고, 공고를 등록해 cited_pages를 채운다). 등록되면 같은 연도 새 공고는 그 표로 판정된다.")
        else:
            st.caption("보관된 PDF 없음(보관 기간 14일이 지났거나 LH·SH 공고가 아님).")
        if j["status"] in ("pending", "running", "failed"):
            note = st.text_input("메모(닫는 사유·등록 번호 등)", key=f"note_{j['id']}")
            b1, b2 = st.columns(2)
            if b1.button("완료(등록·검토 끝)", key=f"done_{j['id']}"):
                store.close_job(j["id"], "done", note)
                st.rerun()
            if b2.button("닫기(판정할 수 없음)", key=f"fail_{j['id']}"):
                store.close_job(j["id"], "failed", note or "운영자가 닫음")
                st.rerun()

# ---- 3. 지금 모집 중인 공고(공공데이터포털 수집 — docs/12) ----
st.subheader("지금 모집 중인 공고")
st.caption("`python tools/collect_live_notices.py`(예약 작업 collect-live-notices, 3시간마다)가 LH·청약홈에서 모은 마감 안 된 공고. "
           "'판정 틀 있음'인데 등록되지 않은 공고는 공식 링크에서 공고문을 내려받아 올리면 모두 판정받는다(PDF 자동 내려받기 안 함).")
ROUTE_LABEL = {"registered": "등록 공고", "template": "판정 틀 있음(분석 전)", "unsupported": "판정 안 하는 사업"}
import live_notices as LN  # noqa: E402
live = LN.merge_duplicates(store.live_notices(open_only=True))     # 정정공고·LH와 청약홈의 같은 공고는 한 줄로
if live:
    pick = st.multiselect("갈래", list(ROUTE_LABEL), default=["template", "registered"], format_func=ROUTE_LABEL.get, key="live_route")
    shown = [r for r in live if r["route"] in pick]
    st.caption(f"마감 안 된 공고 {len(live)}건 중 {len(shown)}건")
    st.dataframe([{"갈래": ROUTE_LABEL.get(r["route"], r["route"]), "기관": r["issuer"], "사업": r["program"] or r["kind"],
                   "공고명": r["title"], "지역": r["region"], "접수": f"{r['window_start'] or '?'} ~ {r['window_end'] or '?'}",
                   "상태": r["status"], "등록": r["registered_id"] or "",
                   "묶인 공고": ", ".join(f"{x['source']} {x['status'] or ''}".strip() for x in r["related"]),
                   "링크": r["url"]} for r in shown],
                 column_config={"링크": st.column_config.LinkColumn("링크", display_text="공식 공고")},
                 hide_index=True, use_container_width=True)
else:
    st.caption("모은 공고가 없습니다 — 예약 작업이 아직 돌지 않았거나 저장소에 넣지 않았습니다.")

# ---- 4. 이용 집계 ----
st.subheader("이용 집계(최근 14일)")
usage = store.usage(14)
if usage:
    st.table([{"날짜": str(u["day"]), "업로드": u["uploads"], "판정": u["judged"], "판정 못 함": u["unjudged"]} for u in usage])
else:
    st.caption("집계가 없습니다.")
