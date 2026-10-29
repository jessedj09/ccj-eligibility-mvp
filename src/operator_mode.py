# -*- coding: utf-8 -*-
"""operator_mode.py — 운영자 미리보기 잠금(A2). 판정 로직 없음.

미등록 공고의 '검증 전 초안' 판정(src/draft.py)은 공개 전까지 운영자만 본다.
- 주소에 `?operator`가 있을 때만 사이드바에 비밀번호 입력란이 나온다(일반 사용자 화면에는 아무것도 보이지 않는다).
- 비밀번호는 Streamlit secrets `operator_password`(배포: 앱 설정 → Secrets, 로컬: .streamlit/secrets.toml — 커밋 금지)
  또는 환경변수 `CCJ_OPERATOR_PASSWORD`. 둘 다 없으면 운영자 모드를 켤 수 없다.
- 켜진 상태는 그 브라우저 세션(session_state)에만 남는다.
"""
import hmac
import os
from typing import Optional

import streamlit as st

KEY = "operator_on"
ENV = "CCJ_OPERATOR_PASSWORD"
PUBLIC_ENV = "CCJ_AUTO_JUDGE_PUBLIC"


def configured_password() -> Optional[str]:
    try:
        value = st.secrets.get("operator_password")
    except Exception:   # secrets 파일이 없으면 접근 자체가 예외(Streamlit 버전마다 종류가 다름)
        value = None
    return value or os.environ.get(ENV) or None


def auto_judge_public() -> bool:
    """자동 판정(v3 — 미등록 공고를 룰 엔진으로 자동 판정)을 일반 사용자에게 여는 스위치. 기본은 꺼짐(운영자만) — 베타 공개 기준
    (PRD v3 13절)을 충족하면 secrets `auto_judge_public = true` 또는 환경변수 CCJ_AUTO_JUDGE_PUBLIC=1로 켠다."""
    try:
        value = st.secrets.get("auto_judge_public")
    except Exception:
        value = None
    if value is None:
        value = os.environ.get(PUBLIC_ENV, "")
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def check(entered: str, expected: Optional[str]) -> bool:
    return bool(expected) and hmac.compare_digest(entered.encode("utf-8"), expected.encode("utf-8"))


def _unlock():
    if check(st.session_state.get("operator_pw", ""), configured_password()):
        st.session_state[KEY] = True


def _lock():
    st.session_state[KEY] = False


def sidebar_gate() -> bool:
    """사이드바에 잠금 상태를 그리고 운영자 모드인지 돌려준다. 주소에 ?operator가 없으면 아무것도 그리지 않는다.
    잠금·해제는 위젯 콜백으로 한다 — 화면 중간에 st.rerun()을 하면 아직 그리지 않은 아래 위젯(공고 고르는 방법 등)의
    값이 처음 값으로 돌아간다."""
    if st.session_state.get(KEY):
        with st.sidebar.expander("🔧 운영자 모드 켜짐", expanded=False):
            st.caption("미등록 공고를 올리면 '검증 전 초안' 판정을 미리 볼 수 있습니다(일반 사용자에게는 보이지 않음).")
            st.button("운영자 모드 끄기", key="operator_off", on_click=_lock)
        return True
    if "operator" not in st.query_params:
        return False
    with st.sidebar.expander("🔧 운영자", expanded=True):
        if not configured_password():
            st.caption(f"운영자 비밀번호가 설정되지 않았습니다(secrets `operator_password` 또는 환경변수 `{ENV}`).")
            return False
        if st.text_input("운영자 비밀번호", type="password", key="operator_pw", on_change=_unlock):
            st.error("비밀번호가 맞지 않습니다.")     # 맞으면 콜백이 먼저 켜서 위의 '켜짐' 쪽으로 간다
    return False
