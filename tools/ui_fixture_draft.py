# -*- coding: utf-8 -*-
"""화면 점검(tools/ui_smoke.py 17단계)용: 실제 app.py를 '미등록 공고를 올린 상태'로 실행한다.

AppTest는 파일 업로드를 흉내 낼 수 없어 두 가지만 바꿔 끼운다(앱 실행에는 쓰이지 않는다).
- 공고문 업로드 칸(key="notice_pdf")이 session_state["fixture_pdf"] 파일을 올린 것처럼 돌려준다.
- 식별을 '미등록'으로 바꾼다 — 등록 공고 원문을 새 공고로 취급해, 초안 판정을 등록 규칙 판정과 비교할 수 있게.
그 밖의 흐름(운영자 잠금·초안 만들기·판정·표시)은 app.py 그대로다. 공유 저장소는 쓰지 않는다(NullStore).
"""
import dataclasses
import hashlib
import runpy
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import notice_identify as ni  # noqa: E402
import source_verify as sv  # noqa: E402
import store  # noqa: E402

store.reset_store(store.NullStore())   # 점검은 운영 저장소(Neon)에 쓰지 않는다 — 등록 공고 원문을 미등록으로 취급하므로


class _Upload:
    def __init__(self, path: Path):
        self.file_id, self._data = f"fixture-{path.name}", path.read_bytes()

    def getvalue(self):
        return self._data


_real_uploader, _real_identify = st.file_uploader, ni.identify_pdf
pdf = Path(st.session_state["fixture_pdf"])


def _uploader(label, *args, **kwargs):
    if kwargs.get("key") == "notice_pdf":
        return _Upload(pdf)
    return _real_uploader(label, *args, **kwargs)


def _identify(data):
    """지문 일치(등록 공고)를 건너뛰고 미등록 공고가 거치는 텍스트 식별을 그대로 쓴다(접수기간 후보 등이 채워진다)."""
    got = ni.identify_pages(hashlib.sha256(data).hexdigest(), sv.extract_pages_bytes(data, label="<점검>", cache=False))
    return dataclasses.replace(got, status=ni.UNREGISTERED, notice_id=None, ambiguous=[],
                               reason="(화면 점검) 미등록 공고로 취급합니다.")


st.file_uploader, ni.identify_pdf = _uploader, _identify
try:
    runpy.run_path(str(ROOT / "app.py"), run_name="__main__")
finally:
    st.file_uploader, ni.identify_pdf = _real_uploader, _real_identify
