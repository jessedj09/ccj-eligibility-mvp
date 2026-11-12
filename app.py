# -*- coding: utf-8 -*-
"""app.py — 운영자(관리자) 화면 시작 파일(Streamlit). 공개 화면은 Next.js(web/)로 옮겼다(2026-10-31 결정 — Streamlit은 운영자 화면만).

2026-11-12 정리: 첫 화면은 '운영자 검토', 둘째는 '공고문 초안 미리보기'(미등록 공고 자동 분석 초안을 운영자가 미리 본다).
예전 '내 조건으로 공고 찾기'는 공개 화면 '자세히'(/find/all)로 옮겨 여기서는 뺐다.

운영자 확인(src/operator_mode.py): 비밀번호(secrets `operator_password` 또는 환경변수 CCJ_OPERATOR_PASSWORD). Streamlit Cloud는
비공개 앱(Sharing: Only specific people)으로 두어 Streamlit 로그인 + 비밀번호로 이중 잠금. 로그인 이메일로 켜는 방식은 Streamlit 1.42.0부터
Community Cloud 계정 이메일을 받을 수 없어 쓰지 않는다(2026-11-13).

Streamlit Cloud는 시작 파일을 바꾸면 앱을 다시 배포해야 하고 주소가 바뀌므로 시작 파일 이름(app.py)은 그대로 둔다.
"""
import streamlit as st

st.navigation([
    st.Page("ops/review.py", title="운영자 검토", icon="🔧", default=True),
    st.Page("ops/preview.py", title="공고문 초안 미리보기", icon="📄"),
]).run()
