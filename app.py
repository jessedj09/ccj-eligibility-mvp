# -*- coding: utf-8 -*-
"""app.py — 운영자(관리자) 화면 시작 파일(Streamlit). 공개 화면은 Next.js(web/)로 옮겼다(2026-10-31 결정 — Streamlit은 운영자 화면만).

2026-11-12 정리: 첫 화면은 '운영자 검토', 둘째는 '공고문 초안 미리보기'(미등록 공고 자동 분석 초안을 운영자가 미리 본다).
예전 '내 조건으로 공고 찾기'는 공개 화면 '자세히'(/find/all)로 옮겨 여기서는 뺐다.

운영자 확인(src/operator_mode.py):
- Streamlit Community Cloud(비공개 앱) — Streamlit에 로그인한 이메일이 secrets `operator_emails`에 있으면 비밀번호 없이 켜진다.
- 운영자 PC(`streamlit run app.py`) — 로그인 정보가 없으므로 비밀번호(secrets `operator_password` 또는 환경변수 CCJ_OPERATOR_PASSWORD).

Streamlit Cloud는 시작 파일을 바꾸면 앱을 다시 배포해야 하고 주소가 바뀌므로 시작 파일 이름(app.py)은 그대로 둔다.
"""
import streamlit as st

st.navigation([
    st.Page("ops/review.py", title="운영자 검토", icon="🔧", default=True),
    st.Page("ops/preview.py", title="공고문 초안 미리보기", icon="📄"),
]).run()
