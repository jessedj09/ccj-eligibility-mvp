# -*- coding: utf-8 -*-
"""화면 점검(tools/ui_smoke.py 15단계)용 고정 화면: 업로드 식별 결과 하나를 그린다.

AppTest는 파일 업로드를 흉내 낼 수 없어, 식별 결과(session_state["fixture_status"])를 직접 만들어
화면 그리기 함수(src/upload_view.py)에 넣는다. 앱 실행에는 쓰이지 않는다.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from notice_identify import Identification  # noqa: E402
from upload_view import render_identified, render_not_judgeable  # noqa: E402

REASONS = {"UNREGISTERED": "아직 등록되지 않은 공고입니다.",
           "UNREADABLE": "글자를 읽을 수 없는 PDF입니다(스캔 이미지일 수 있음).",
           "SAME_NOTICE_OTHER_FILE": "공고일과 사업 유형이 등록 공고 N4와 같지만 파일이 다릅니다.",
           "REGISTERED": "등록 공고 N4의 원문과 같은 파일입니다."}
status = st.session_state.get("fixture_status", "UNREGISTERED")
ident = Identification(status, "N4" if status in ("SAME_NOTICE_OTHER_FILE", "REGISTERED") else None,
                       reason=REASONS[status], issuer="LH", program="청년매입임대", announcement="2026-12-01",
                       windows=[{"start": "2026-12-10T10:00", "end": "2026-12-12T16:00", "page": 5}],
                       similar=["N11", "N12"] if status == "UNREGISTERED" else [])
if status in ("UNREGISTERED", "UNREADABLE"):
    render_not_judgeable(ident)
else:
    render_identified(ident)
