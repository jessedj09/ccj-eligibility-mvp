# -*- coding: utf-8 -*-
"""upload_view.py — 공고 업로드 식별 결과를 화면에 그린다(공고 업로드 판정 P0). 판정 로직 없음.

화면(app.py)과 화면 점검(tools/ui_smoke.py — AppTest는 파일 업로드를 흉내 낼 수 없어 식별 결과를 직접 넣어 그린다)이 함께 쓴다.
"""
import streamlit as st

from notice_identify import REGISTERED, SAME_NOTICE_OTHER_FILE, UNREADABLE, Identification
from rule_data import load_notice

NOT_JUDGED = ("검증된 규칙이 없는 공고는 판정하지 않습니다 — 확인되지 않은 조건으로 틀린 '지원 가능'을 보여 주지 않기 위해서입니다.")


def render_candidates(ident: Identification) -> None:
    """공고문에서 자동으로 찾은 후보(판정에는 쓰지 않음)."""
    rows = []
    if ident.issuer or ident.program:
        rows.append(f"- 발행 기관·사업 유형(추정): **{ident.issuer or '알 수 없음'} · {ident.program or '알 수 없음'}**")
    rows.append(f"- 공고일(후보): **{ident.announcement or '찾지 못함'}**")
    if ident.windows:
        spans = " / ".join(f"{w['start'].replace('T', ' ')} ~ {w['end'].replace('T', ' ')} (p.{w['page']})"
                           for w in ident.windows[:3])
        rows.append(f"- 청약 접수기간(후보): {spans}")
    else:
        rows.append("- 청약 접수기간(후보): 찾지 못함")
    st.markdown("\n".join(rows))
    if ident.similar:
        st.caption("같은 사업의 등록 공고(같은 공고가 아니므로 이 공고의 판정에 쓰지 않습니다): "
                   + ", ".join(f"{n} {load_notice(n).title}" for n in ident.similar))
    if ident.ambiguous:
        st.caption("공고일·사업 유형이 같은 등록 공고: " + ", ".join(f"{n} {load_notice(n).title}" for n in ident.ambiguous)
                   + " — 그중 하나라면 '목록에서 고르기'로 선택하세요.")
    st.caption("위 정보는 공고문에서 자동으로 찾은 후보입니다. 신청 전 공고 원문을 확인하세요.")


def render_not_judgeable(ident: Identification) -> None:
    """미등록·읽을 수 없는 공고 — 판정하지 않고 안내만."""
    st.subheader("📄 아직 판정할 수 없는 공고")
    st.info(f"{ident.reason} {NOT_JUDGED}")
    if ident.status == UNREADABLE:
        return
    render_candidates(ident)
    st.caption("이 공고의 등록을 원하면 공고명과 공고일을 운영자에게 알려 주세요. 등록되면 같은 파일을 올렸을 때 바로 판정됩니다.")


FIELD_ICON = {"filled": "✅", "held": "⏸️", "absent": "➖"}


def render_draft_details(d) -> None:
    """초안 추출 내역(운영자용) — 빈칸별 값·근거 쪽, 찾지 못한 인용문, 기준표 연도, 새 제한 문구."""
    import draft
    with st.expander("초안 추출 내역(운영자용) — 채운 값·보류·근거 쪽"):
        for path, f in draft.field_rows(d.fields):
            value = f["value"] if isinstance(f["value"], str) else str(f["value"])
            where = f" (p.{f['page']})" if f["page"] else ""
            st.caption(f"{FIELD_ICON[f['status']]} `{path}` {value[:80]}{where} — {f['how']}")
        plain = [m for m in d.missing if m not in d.stale]
        if plain:
            st.markdown(f"**원문에서 찾지 못한 인용문 {len(plain)}개** (그 조건은 보류)")
            for m in plain[:10]:
                st.caption(m)
        if d.stale:
            st.markdown(f"**기준표 연도가 다른 조건 {len(d.stale)}개** (보류)")
            for m in d.stale[:10]:
                st.caption(m)
        if d.restrictions:
            st.markdown(f"**규칙에 없는 지역·모집 제한 문구 {len(d.restrictions)}개** ('지원 가능'을 '수동 확인'으로 낮춤)")
            for page, text in d.restrictions[:10]:
                st.caption(f"p.{page} {text}")
        st.caption("등록하려면 `python tools/notice_intake.py <공고문.pdf> --draft`로 같은 내역과 생성 스크립트 항목을 받는다"
                   "(docs/08).")


def render_draft(d, ident: Identification = None) -> None:
    """운영자 미리보기(A2): 미등록 공고를 자동 추출 초안 규칙으로 판정할 때 본문 맨 위 안내."""
    held = sum(len(v) for v in d.held_conditions.values())
    st.warning("🟠 **검증 전 초안 — 운영자 미리보기.** 등록되지 않은 공고를 자동으로 읽은 초안 규칙으로 판정합니다. "
               "일반 사용자에게는 보이지 않습니다.")
    rows = [f"- 사업 유형: **{d.program}** (템플릿 `{d.template}`) · 공고일 **{d.announcement_date}**",
            f"- 보류된 조건 {held}개 · 규칙에 없는 제한 문구 {len(d.restrictions)}개 — 판정에 쓰이면 '지원 가능'을 "
            "'수동 확인'으로 낮춥니다."]
    if ident is not None and ident.windows:     # 초안은 접수기간 데이터(schedules.json)가 없다 — 후보만 보인다
        rows.append("- 청약 접수기간(후보): " + " / ".join(
            f"{w['start'].replace('T', ' ')} ~ {w['end'].replace('T', ' ')} (p.{w['page']})" for w in ident.windows[:3]))
    st.markdown("\n".join(rows))
    render_draft_details(d)


def render_draft_refused(d) -> None:
    """운영자 미리보기: 초안 판정을 할 수 없는 이유(판정하지 않음)."""
    st.caption(f"🔧 운영자 미리보기: 초안 판정을 하지 않습니다 — {d.reason}")
    if d.fields:
        render_draft_details(d)


def render_identified(ident: Identification) -> None:
    """등록 공고로 식별됐을 때 본문 맨 위 안내."""
    n = load_notice(ident.notice_id)
    if ident.status == REGISTERED:
        st.caption(f"📄 올린 공고문 = 등록 공고 **{ident.notice_id} {n.title}** (원문 파일 일치) — 검증된 규칙으로 판정합니다.")
    elif ident.status == SAME_NOTICE_OTHER_FILE:
        st.info(f"📄 {ident.reason} 아래 판정은 **등록된 원문({ident.notice_id})** 기준입니다 — 정정 공고라면 결과가 다를 수 있으니 "
                "바뀐 조건이 없는지 원문을 확인하세요.")
