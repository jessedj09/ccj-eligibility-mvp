# -*- coding: utf-8 -*-
"""
notices_data.py — 공고 규칙의 공개 진입점
=========================================
규칙 본체는 코드가 아니라 `rules/notices/*.json`(조건·결정표·출처·검수 상태)과
`rules/reference/*.json`(기준값 표)이고, 로더는 `src/rule_data.py`다 (설계: docs/06-rule-data-design.md).
이 파일은 앱·테스트가 쓰는 이름(N1/N2/N3, ALL_NOTICES, 공고일, 컷오프 상수)을 데이터에서 로드해 내보내는
얇은 호환 계층이다. 규칙을 고치려면 이 파일이 아니라 JSON을 고친다.
"""

from datetime import date

from rule_data import load_notice
from rule_engine import marriage_cutoff, young_child_cutoff

N1 = load_notice("N1")   # 서울공릉 신혼희망타운 행복주택 — 신혼부부·한부모
N2 = load_notice("N2")   # 서울관악봉천 행복주택 — 대학생
N3 = load_notice("N3")   # 서울번동3 행복주택 — 대학생·청년·신혼부부·한부모

ALL_NOTICES = {"N1": N1, "N2": N2, "N3": N3}

N1_ANNOUNCEMENT = N1.announcement_date
N2_ANNOUNCEMENT = N2.announcement_date
N3_ANNOUNCEMENT = N3.announcement_date

# 혼인기간 7년 / 6세 이하 자녀 컷오프 — 테스트가 데이터 규칙의 경계를 확인할 때 쓰는 기준 상수.
# N1은 원문 p.5가 날짜를 적어 둔 리터럴, N3는 원문에 날짜가 없어 N1 리터럴을 재현하는 같은 공식으로 도출.
N1_MARRIAGE_CUTOFF = date(2019, 7, 29)
N1_CHILD_CUTOFF = date(2019, 7, 30)
N3_MARRIAGE_CUTOFF = marriage_cutoff(N3_ANNOUNCEMENT)
N3_CHILD_CUTOFF = young_child_cutoff(N3_ANNOUNCEMENT)
