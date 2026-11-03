# -*- coding: utf-8 -*-
"""golden_cases.py — 골든 스냅샷용 결정론적 입력 생성기.

골든 스냅샷은 "지금 규칙이 이 입력들에 이렇게 답한다"는 기록이다(tests/golden/*). 규칙을 의도적으로
바꾸면 `python tools/regen_golden.py`로 갱신하고 변경 내역을 검토한다.

설계 원칙:
- 입력은 **고정 숫자**(PDF 수치)로 만든다. 데이터의 한도에서 경계를 자동 파생하면 한도가 바뀔 때 입력도
  같이 움직여 오류를 못 잡는다.
- 난수는 직접 구현한 splitmix64를 쓴다(파이썬 `random`은 버전마다 같은 시드에서 결과가 달라질 수 있다).
- 공고일·컷오프 날짜는 PDF에서 손으로 계산한 리터럴이다(엔진 함수를 쓰지 않는다).
"""

from datetime import date
from typing import Dict, Iterator, List, Tuple

from rule_engine import HouseholdProfile

# 공고별 손계산 기준일(공고일, 혼인7년/6세이하 컷오프, 졸업 2년 컷오프, 미성년 경계=공고일 기준 만 19세가 되는 생일)
DATES = {
    "N1": dict(ann=date(2026, 7, 29), marriage=date(2019, 7, 29), child=date(2019, 7, 30),
               grad=date(2024, 7, 29), adult=date(2007, 7, 29)),
    "N2": dict(ann=date(2026, 7, 15), marriage=date(2019, 7, 15), child=date(2019, 7, 16),
               grad=date(2024, 7, 15), adult=date(2007, 7, 15)),
    "N3": dict(ann=date(2026, 8, 19), marriage=date(2019, 8, 19), child=date(2019, 8, 20),
               grad=date(2024, 8, 19), adult=date(2007, 8, 19)),
    # C1 추가 공고(LH 행복주택). 원문 날짜: N4 p.1 "2019.10.02. 이후 출생", N6 p.2 "2019.05.16. 이후 출생",
    # N7 p.1·p.5 "2019.6.29. 이후 혼인신고"·"2019.6.30. 이후 출생". 나머지는 LH 관행(공고일−7년 당일 / 다음 날)으로 손계산.
    "N4": dict(ann=date(2026, 10, 1), marriage=date(2019, 10, 1), child=date(2019, 10, 2),
               grad=date(2024, 10, 1), adult=date(2007, 10, 1)),
    "N5": dict(ann=date(2026, 8, 18), marriage=date(2019, 8, 18), child=date(2019, 8, 19),
               grad=date(2024, 8, 18), adult=date(2007, 8, 18)),
    "N6": dict(ann=date(2026, 5, 15), marriage=date(2019, 5, 15), child=date(2019, 5, 16),
               grad=date(2024, 5, 15), adult=date(2007, 5, 15)),
    "N7": dict(ann=date(2026, 6, 29), marriage=date(2019, 6, 29), child=date(2019, 6, 30),
               grad=date(2024, 6, 29), adult=date(2007, 6, 29)),
    "N8": dict(ann=date(2026, 9, 29), marriage=date(2019, 9, 29), child=date(2019, 9, 30),
               grad=date(2024, 9, 29), adult=date(2007, 9, 29)),
    # C2(1순위 지역만 모집). N10 p.1 "2019.05.16. 이후 출생".
    "N9": dict(ann=date(2026, 5, 7), marriage=date(2019, 5, 7), child=date(2019, 5, 8),
               grad=date(2024, 5, 7), adult=date(2007, 5, 7)),
    "N10": dict(ann=date(2026, 5, 15), marriage=date(2019, 5, 15), child=date(2019, 5, 16),
                grad=date(2024, 5, 15), adult=date(2007, 5, 15)),
    # B단계(2026-11-01) — 처음 보는 공고 검증용 등록. N27 p.1 "6세이하자녀(출생일2019.10.29.이후)", "청년 … 출생일
    # 1986.10.29.∼2007.10.28." 혼인 7년은 원문 날짜 없음 → LH 관행(공고일−7년 당일)으로 손계산.
    "N27": dict(ann=date(2026, 10, 28), marriage=date(2019, 10, 28), child=date(2019, 10, 29),
                grad=date(2024, 10, 28), adult=date(2007, 10, 28)),
    # N28 p.6 "*6세이하:2019.10.28.이후출생(태아포함)", "*혼인기간:2019.10.27.이후혼인신고".
    "N28": dict(ann=date(2026, 10, 27), marriage=date(2019, 10, 27), child=date(2019, 10, 28),
                grad=date(2024, 10, 27), adult=date(2007, 10, 27)),
    # C4a(LH 매입임대·든든전세). 원문 날짜: N13 p.3 "2019.6.25.~"·"’19.6.26 이후"·"’24.6.25이후", N14 p.3 "2019.9.17~"·
    # "‘19.9.18이후"·"‘24.9.17이후". newborn = 신생아 가구 기준일(공고일−2년, LH 원문).
    "N11": dict(ann=date(2026, 6, 25), marriage=date(2019, 6, 25), child=date(2019, 6, 26),
                grad=date(2024, 6, 25), adult=date(2007, 6, 25)),
    "N12": dict(ann=date(2026, 9, 17), marriage=date(2019, 9, 17), child=date(2019, 9, 18),
                grad=date(2024, 9, 17), adult=date(2007, 9, 17)),
    "N13": dict(ann=date(2026, 6, 25), marriage=date(2019, 6, 25), child=date(2019, 6, 26),
                grad=date(2024, 6, 25), adult=date(2007, 6, 25), newborn=date(2024, 6, 25)),
    "N14": dict(ann=date(2026, 9, 17), marriage=date(2019, 9, 17), child=date(2019, 9, 18),
                grad=date(2024, 9, 17), adult=date(2007, 9, 17), newborn=date(2024, 9, 17)),
    "N15": dict(ann=date(2026, 6, 25), marriage=date(2019, 6, 25), child=date(2019, 6, 26),
                grad=date(2024, 6, 25), adult=date(2007, 6, 25), newborn=date(2024, 6, 25)),
    # G2(2026-11-01) 처음 보는 공고 검증 — N29 p.3 "혼인신고일이2019.9.17~2026.9.17"·"'19.9.18이후출생"·"'24.9.17이후출생".
    "N29": dict(ann=date(2026, 9, 17), marriage=date(2019, 9, 17), child=date(2019, 9, 18),
                grad=date(2024, 9, 17), adult=date(2007, 9, 17), newborn=date(2024, 9, 17)),
    # G2 국민임대(N30 남양주마석·N31 김포) — 공고일만 쓴다(출산자녀 가산 기준일 2023.3.28.은 고정, 미성년 = 공고일−19년).
    "N30": dict(ann=date(2026, 9, 7), marriage=date(2019, 9, 7), child=date(2019, 9, 8),
                grad=date(2024, 9, 7), adult=date(2007, 9, 7)),
    "N31": dict(ann=date(2026, 9, 7), marriage=date(2019, 9, 7), child=date(2019, 9, 8),
                grad=date(2024, 9, 7), adult=date(2007, 9, 7)),
    "N32": dict(ann=date(2026, 9, 7), marriage=date(2019, 9, 7), child=date(2019, 9, 8),
                grad=date(2024, 9, 7), adult=date(2007, 9, 7)),
    # G5 SH 국민임대(N53 2026.08.20) — 공고일만 쓴다(출생자녀 가산 기준일 2023.3.28. 고정, 미성년 = 공고일−19년).
    "N53": dict(ann=date(2026, 8, 20), marriage=date(2019, 8, 20), child=date(2019, 8, 21),
                grad=date(2024, 8, 20), adult=date(2007, 8, 20)),
    # G5 SH 영구임대(N54 2025.11.13) — 공고일만 쓴다(출생자녀 기준일 2023.3.28. 고정).
    "N54": dict(ann=date(2025, 11, 13), marriage=date(2018, 11, 13), child=date(2018, 11, 14),
                grad=date(2023, 11, 13), adult=date(2006, 11, 13)),
    # G7 LH 선택형 공공임대(N57 뉴홈 4차 사전청약 2024.01.04.) — 혼인 7년·6세 이하·19세 미만 자녀는 공고일 기준.
    "N57": dict(ann=date(2024, 1, 4), marriage=date(2017, 1, 4), child=date(2017, 1, 5),
                grad=date(2022, 1, 4), adult=date(2005, 1, 4)),
    # G6 LH 나눔형(N56 뉴홈 4차 사전청약 2024.01.03.) — 혼인 7년·6세 이하 자녀는 공고일 기준.
    "N56": dict(ann=date(2024, 1, 3), marriage=date(2017, 1, 3), child=date(2017, 1, 4),
                grad=date(2022, 1, 3), adult=date(2005, 1, 3)),
    # G5 LH 고령자복지주택(N55 평택고덕 A-58 2026.08.20) — 공고일만 쓴다.
    "N55": dict(ann=date(2026, 8, 20), marriage=date(2019, 8, 20), child=date(2019, 8, 21),
                grad=date(2024, 8, 20), adult=date(2007, 8, 20)),
    # G2 영구임대(N33 양주회천 A25 2026.09.21, N34 부천시 2026.09.04) — 공고일만 쓴다(출생자녀 기준일 2023.3.28. 고정).
    "N33": dict(ann=date(2026, 9, 21), marriage=date(2019, 9, 21), child=date(2019, 9, 22),
                grad=date(2024, 9, 21), adult=date(2007, 9, 21)),
    "N34": dict(ann=date(2026, 9, 4), marriage=date(2019, 9, 4), child=date(2019, 9, 5),
                grad=date(2024, 9, 4), adult=date(2007, 9, 4)),
    # G2 통합공공임대(N35 평창장평 2026.10.30, N36 강서염창 2026.09.17) — N35 p.16 "6세이하자녀(2019.10.31.이후출생)",
    # N36 p.17 "(2019.9.18.이후출생)". 혼인 7년은 원문에 날짜가 없어 공고일−7년(당일 포함).
    "N35": dict(ann=date(2026, 10, 30), marriage=date(2019, 10, 30), child=date(2019, 10, 31),
                grad=date(2024, 10, 30), adult=date(2007, 10, 30)),
    "N36": dict(ann=date(2026, 9, 17), marriage=date(2019, 9, 17), child=date(2019, 9, 18),
                grad=date(2024, 9, 17), adult=date(2007, 9, 17)),
    # G4 공공임대 예비입주자 — 공고일만 쓴다(날짜 기준 조건 없음)
    **{nid: dict(ann=a, marriage=date(a.year - 7, a.month, a.day), child=date(a.year - 7, a.month, a.day),
                 grad=date(a.year - 2, a.month, a.day), adult=date(a.year - 19, a.month, a.day))
       for nid, a in (("N37", date(2026, 5, 28)), ("N38", date(2026, 6, 24)), ("N39", date(2026, 6, 10)),
                      ("N40", date(2026, 6, 19)), ("N41", date(2026, 9, 29)), ("N42", date(2025, 10, 28)),
                      ("N43", date(2026, 10, 22)), ("N44", date(2026, 6, 9)))},
    # G3 신혼희망타운 — 혼인 7년(공고일 당일 포함)·6세 이하(공고일−7년+1일, N46 p.11 "2019.09.18.~2026.09.18.")
    **{nid: dict(ann=a, marriage=date(a.year - 7, a.month, a.day), child=date(a.year - 7, a.month, a.day + 1),
                 grad=date(a.year - 2, a.month, a.day), adult=date(a.year - 19, a.month, a.day))
       for nid, a in (("N45", date(2026, 9, 8)), ("N46", date(2026, 9, 18)), ("N47", date(2026, 9, 29)),
                      ("N48", date(2026, 10, 30)))},
    # G3 LH 공공분양(N49 양주회천 A-26 2026.08.27, N50 안산신길2 B-1 2026.10.30) — 혼인 7년·6세 이하·19세 미만·2세 미만은 공고일에서
    **{nid: dict(ann=a, marriage=date(a.year - 7, a.month, a.day), child=date(a.year - 7, a.month, a.day + 1),
                 grad=date(a.year - 2, a.month, a.day), adult=date(a.year - 19, a.month, a.day + 1),
                 newborn=date(a.year - 2, a.month, a.day))
       for nid, a in (("N49", date(2026, 8, 27)), ("N50", date(2026, 10, 30)), ("N51", date(2026, 2, 27)),
                      ("N52", date(2026, 10, 16)))},
    "N16": dict(ann=date(2026, 5, 22), marriage=date(2019, 5, 22), child=date(2019, 5, 23),
                grad=date(2024, 5, 22), adult=date(2007, 5, 22)),
    "N17": dict(ann=date(2026, 10, 1), marriage=date(2019, 10, 1), child=date(2019, 10, 2),
                grad=date(2024, 10, 1), adult=date(2007, 10, 1)),
    # C4b(SH) — SH 원문 날짜(공고일−N년의 다음 날): SH21·SH22 p.12/p.6 "‘19. 10. 1.~"·"‘24. 10. 1. 이후"·"’07. 10. 1. 이후",
    # SH18 p.10 "’19. 08. 15.~"·"’24. 08. 15. 이후", SH19 p.9 "’19. 8. 25.~"·"’24. 8. 25. 이후". adult는 엔진의 미성년 경계(공고일 −19년).
    "N18": dict(ann=date(2026, 9, 30), marriage=date(2019, 10, 1), child=date(2019, 10, 1), grad=date(2024, 9, 30),
                adult=date(2007, 9, 30), newborn=date(2024, 10, 1), minor=date(2007, 10, 1)),
    "N19": dict(ann=date(2026, 9, 30), marriage=date(2019, 10, 1), child=date(2019, 10, 1), grad=date(2024, 9, 30),
                adult=date(2007, 9, 30), newborn=date(2024, 10, 1), minor=date(2007, 10, 1)),
    "N20": dict(ann=date(2026, 8, 14), marriage=date(2019, 8, 15), child=date(2019, 8, 15), grad=date(2024, 8, 14),
                adult=date(2007, 8, 14), newborn=date(2024, 8, 15)),
    "N21": dict(ann=date(2026, 8, 24), marriage=date(2019, 8, 25), child=date(2019, 8, 25), grad=date(2024, 8, 24),
                adult=date(2007, 8, 24), newborn=date(2024, 8, 25)),
    "N22": dict(ann=date(2026, 8, 28), marriage=date(2019, 8, 29), child=date(2019, 8, 29), grad=date(2024, 8, 28),
                adult=date(2007, 8, 28)),
    # C5b(SH 장기전세2·장기전세): 혼인 기준일은 원문(SH25 p.13 "2019. 4. 25. 이후", SH26 p.13 "2019. 8. 22. 이후")
    "N23": dict(ann=date(2026, 4, 24), marriage=date(2019, 4, 25), child=date(2019, 4, 25), grad=date(2024, 4, 24),
                adult=date(2007, 4, 24)),
    "N24": dict(ann=date(2026, 8, 21), marriage=date(2019, 8, 22), child=date(2019, 8, 22), grad=date(2024, 8, 21),
                adult=date(2007, 8, 21)),
    "N25": dict(ann=date(2025, 12, 15), marriage=date(2018, 12, 16), child=date(2018, 12, 16), grad=date(2023, 12, 15),
                adult=date(2006, 12, 15)),
    "N26": dict(ann=date(2026, 4, 27), marriage=date(2019, 4, 28), child=date(2019, 4, 28), grad=date(2024, 4, 27),
                adult=date(2007, 4, 27)),
}
# 지역 조건이 있는 공고와 계층별 지역 입력(원문 PDF의 순위 문구에서 손으로 옮김). 다른 공고에는 지역 입력을 넣지 않는다
# — 넣으면 기존 그룹의 입력·난수 소비가 바뀌어 골든 기록 전체가 달라진다.
REGION_FIELDS_BY_LAYER = {
    "N9": {"대학생": ["residence_area", "school_area"]},
    "N10": {"대학생": ["residence_area", "school_area"], "청년": ["residence_area", "income_base_area"],
            "신혼부부": ["residence_area", "income_base_area", "spouse_residence_area", "spouse_income_base_area"],
            "한부모": ["residence_area", "income_base_area"]},
}
# 산업단지근로자의 근무지(산업단지 소재지)는 지역 표준 이름이다 — 지역 풀을 같이 쓴다(기본값 서울)
REGION_FIELDS_BY_LAYER.setdefault("N6", {})["산업단지근로자"] = ["workplace_area"]
REGION_FIELDS_BY_LAYER["N16"] = {"일반": ["residence_area"]}     # 든든전세: 수도권 거주
REGION_FIELDS_BY_LAYER["N17"] = {"일반": ["residence_area"]}
REGION_FIELDS_BY_LAYER["N22"] = {"일반": ["residence_area"]}     # SH 장기미임대: 서울 주민등록

# --- C4a 사업별 입력 풀(원문 금액의 경계 ±1원을 손으로 적은 고정 값) --------------------------------------
PROGRAM_OF = {"N11": "youth_rental", "N12": "youth_rental", "N13": "newlywed_rental", "N14": "newlywed_rental",
              "N15": "newlywed_rental", "N16": "jeonse", "N17": "jeonse",
              "N18": "sh_newlywed", "N19": "sh_newlywed", "N20": "sh_newlywed", "N21": "sh_newlywed", "N22": "jeonse",
              "N23": "sh_jeonse2", "N24": "sh_jeonse2", "N25": "sh_jeonse", "N26": "sh_jeonse",
              "N29": "newlywed_rental", "N30": "national_rental", "N31": "national_rental",
              "N32": "national_rental", "N33": "permanent_rental", "N34": "permanent_rental",
              "N35": "integrated_rental", "N36": "integrated_rental",
              **{f"N{n}": "public_rental" for n in range(37, 45)},
              **{f"N{n}": "newlywed_town_sale" for n in range(45, 49)},
              "N49": "public_sale", "N50": "public_sale", "N51": "sh_land_sale", "N52": "sh_land_sale",
              "N53": "sh_national_rental", "N54": "sh_permanent_rental",
              "N55": "elderly_welfare", "N56": "share_sale",
              "N57": "select_rental"}
CITY_OF = {"N33": "양주시", "N34": "부천시"}     # 영구임대 거주 요건 시(통과 쪽 기본값)
J2_INCOME = [None, 0, 1] + [v + d for v in (7_039_524, 9_802_115, 14_703_172, 8_799_405, 12_252_644, 18_653_970)
                            for d in (-1, 0, 1)] + [40_000_000]
JS_INCOME = [None, 0, 1] + [v + d for v in (4_004_031, 8_576_850, 9_393_693, 10_210_536, 11_435_801, 12_252_644,
                                            16_336_858, 3_778_072, 8_008_322, 5_397_246) for d in (-1, 0, 1)] + [40_000_000]
J_ASSETS = [None, 0, 1] + [v + d for v in (640_000_000, 662_000_000, 704_000_000, 728_000_000, 768_000_000, 794_000_000)
                           for d in (0, 1)]
J_CARS = [0, 1, "확인불가"] + [v + d for v in (45_420_000, 45_630_000, 49_960_000, 54_510_000) for d in (0, 1)]
SH_INCOME = [None, 0, 1] + [v + d for v in (4_693_016, 5_717_900, 7_351_586, 6_934_384, 8_212_778, 10_618_958,
                                            16_336_858, 12_878_142) for d in (-1, 0, 1)] + [90_000_000]
WELFARE = [None, "해당없음", "생계·의료·주거급여 수급자", "교육급여만 수급", "차상위계층"]
YR_OWN_INCOME = [None, 0, 1, 1_000_000, 4_576_035, 4_576_036, 4_576_037, 9_000_000]
YR_PARENT_INCOME = [None, 0, 1_000_000, 3_576_036, 3_576_037, 5_452_897, 5_452_898, 7_168_429, 7_168_430, 20_000_000]
YR_OWN_ASSETS = [None, 0, 1, 251_000_000, 251_000_001, 260_000_000, 345_000_001]
YR_PARENT_ASSETS = [None, 0, 85_000_000, 85_000_001, 300_000_000]
YR_PARENT_CAR = [None, 0, 45_420_000, 45_420_001]
NR_INCOME = [None, 0, 1] + [v + d for v in (3_432_027, 4_693_016, 5_717_900, 7_351_586, 10_618_958, 16_336_858)
                            for d in (-1, 0, 1)] + [50_000_000]
NR_ASSETS = [None, 0, 1] + [v + d for v in (345_000_000, 362_000_000, 379_000_000, 413_000_000, 431_000_000)
                            for d in (0, 1)]
# G2 국민임대: 70·80·90% 열(1~8인) 경계 ±1원, 자산·자동차 3단계 한도 경계
NAT_INCOME = [None, 0, 1] + [v + d for v in (3_432_027, 4_693_016, 5_279_643, 5_717_900, 6_534_743, 7_351_586,
                                            6_161_541, 7_921_982, 7_339_879, 9_436_987, 7_745_373, 9_958_337)
                             for d in (-1, 0, 1)] + [30_000_000]
NAT_ASSETS = [None, 0, 1] + [v + d for v in (345_000_000, 379_000_000, 413_000_000) for d in (0, 1)]
# G2 영구임대: 신분별 기준(50·70·100%)과 가산이 만드는 경계 ±1원(1·2·3·7인), 자산 3단계
PERM_INCOME = [None, 0, 1] + [v + d for v in (2_669_354, 3_432_027, 4_576_036, 3_519_762, 4_693_016, 6_452_897, 4_106_389,
                                              4_084_215, 5_717_900, 8_168_429, 4_901_057, 9_802_115, 5_242_771, 12_582_649)
                              for d in (-1, 0, 1)] + [30_000_000]
PERM_ASSETS = [None, 0, 1] + [v + d for v in (245_000_000, 270_000_000, 294_000_000) for d in (0, 1)]
# G5 SH 영구임대(N54 p.9~10): 70%(1인 90%·2인 80%, 출생자녀 가산) 경계 ±1원, 총자산 237·261·285백만, 자동차 4,563·5,020·5,476만
SHP_INCOME = [None, 0, 1] + [v + d for v in (3_238_348, 4_381_602, 4_929_303, 5_338_881, 6_101_578, 6_864_276, 7_304_587,
                                             9_391_612, 10_023_446) for d in (-1, 0, 1)] + [30_000_000]
# G5 LH 고령자복지주택(N55 p.6): 50%(1인 70%·2인 60%)·70%(1인 90%·2인 80%) 적용 금액 경계 ±1원(1·2·3·7인)
ELD_INCOME = [None, 0, 1] + [v + d for v in (2_669_354, 3_432_027, 3_519_762, 4_693_016, 4_084_215, 5_717_900, 5_242_771,
                                             7_339_879) for d in (-1, 0, 1)] + [30_000_000]
# G6 LH 나눔형(N56): 2023년도 100·130·140%(3인 이하·4·8인) 경계 ±1원, 청년 본인 1인 140%, 총자산 379·289백만, 부모 1,083백만
SHARE_INCOME = [None, 0, 1] + [v + d for v in (6_509_452, 8_462_288, 9_113_233, 7_622_056, 9_908_673, 10_670_878, 10_023_933,
                                               13_031_113, 14_033_506) for d in (-1, 0, 1)] + [30_000_000]
SHARE_YOUTH_INCOME = [None, 0] + [4_695_438 + d for d in (-1, 0, 1)]
SHARE_ASSETS = [None, 0] + [v + d for v in (289_000_000, 379_000_000) for d in (0, 1)]
# G7 LH 선택형(N57): 1인 120%·2인 110·130·140·150%·3인 100·120·130·140%·8인 140% 경계 ±1원
SELECT_INCOME = [None, 0, 1] + [v + d for v in (4_024_661, 5_505_914, 6_506_989, 7_007_526, 7_508_064, 6_718_198, 8_061_838,
                                                8_733_657, 9_405_477, 14_033_506) for d in (-1, 0, 1)] + [30_000_000]
SHP_ASSETS = [None, 0, 1] + [v + d for v in (237_000_000, 261_000_000, 285_000_000) for d in (0, 1)]
SHP_CARS = [0, 1, "확인불가"] + [v + d for v in (45_630_000, 50_200_000, 54_760_000) for d in (0, 1)]
# G3 LH 공공분양: 2025 도시근로자 100~220%(3인 이하·4인·8인) 경계 ±1원, 부동산 3단계
SALE_INCOME_POOL = [None, 0, 1] + [v + d for v in (7_533_763, 8_287_139, 9_040_516, 9_793_892, 10_547_268, 11_300_645,
                                                  15_067_526, 15_820_902, 16_574_279, 10_562_642, 17_604_404, 22_129_638)
                                   for d in (-1, 0, 1)] + [40_000_000]
SH_ASSETS_POOL = [None, 0] + [v + d for v in (276_000_000, 311_000_000, 345_000_000, 362_000_000, 397_000_000, 431_000_000)
                              for d in (0, 1)]
SH_YOUTH_INCOME_POOL = [None, 0] + [v + d for v in (5_338_708, 5_720_045, 6_101_381) for d in (-1, 0, 1)] + [20_000_000]
SALE_RE_POOL = [None, 0] + [v + d for v in (215_500_000, 237_050_000, 258_600_000) for d in (0, 1)]
# G3 신혼희망타운: 2025 도시근로자 130·140·150·200·210·220%(3인 이하·4인·8인) 경계 ±1원, 총자산 3단계
NH_INCOME_POOL = [None, 0, 1] + [v + d for v in (9_793_892, 10_547_268, 11_300_645, 15_067_526, 15_820_902, 16_574_279,
                                                11_442_863, 17_604_404, 14_384_265, 22_129_638) for d in (-1, 0, 1)] + [40_000_000]
NH_ASSETS_POOL = [None, 0, 1] + [v + d for v in (362_000_000, 397_000_000, 431_000_000) for d in (0, 1)]
# G2 통합공공임대: 2026 기준중위소득 150~200% 열(가구원수·출산자녀·맞벌이 가산이 만드는 칸) 경계 ±1원
INT_INCOME = [None, 0, 1] + [v + d for v in (4_359_205, 6_718_867, 7_138_796, 7_978_655, 8_038_554, 8_574_458, 9_646_265,
                                            10_182_168, 9_742_107, 10_391_581, 11_041_055, 12_989_476, 14_272_725,
                                            15_711_522) for d in (-1, 0, 1)] + [40_000_000]


def _program_attributes(program: str, layer: str, pools) -> Dict[str, Tuple[list, object]]:
    if program == "youth_rental":
        attrs = {
            "home": (["무주택", "주택보유"], "무주택"), "marital": (["미혼", "혼인중", "한부모"], "미혼"),
            "size": ([1], 1), "kids": ([[]], []), "count": ([0], 0),
            "income": (YR_OWN_INCOME, 1), "assets": (YR_OWN_ASSETS, 1), "car": (CARS, 0),
            "welfare": (WELFARE, "해당없음"), "parent_welfare": (WELFARE, "해당없음"),
            "registered": ([None, True, False], True), "supported": ([None, False, True], False),
            "parents_count": ([None, 0, 1, 2], 2), "parents_income": (YR_PARENT_INCOME, 1_000_000),
            "parents_assets": (YR_PARENT_ASSETS, 0), "parents_car": (YR_PARENT_CAR, 0),
        }
        if layer == "청년":
            attrs["age"] = ([18, 19, 29, 30, 39, 40], 25)
        elif layer == "대학생":
            attrs.update(age=([17, 18, 19, 25, 40, 45], 18), status=(STATUSES, "재학중"))
        else:
            attrs.update(age=([18, 19, 39, 40, 45], 40), grad=(pools["grad"], pools["grad"][2]),
                         employed=([None, False, True], False))
        return attrs
    if program in ("newlywed_rental", "sh_newlywed"):
        return {
            "home": (["무주택", "주택보유"], "무주택"), "marital": (MARITALS, "혼인중"), "size": (SIZES + [6], 3),
            "kids": (pools["kids"], []), "count": (COUNTS, 0), "dual": ([True, False], False),
            "income": (SH_INCOME if program == "sh_newlywed" else NR_INCOME, 1), "assets": (NR_ASSETS, 1),
            "car": (CARS, 0), "marriage": (pools["marriage"], date(2025, 1, 1)), "has_children": (HAS_CHILDREN, None),
            "youngest": (pools["youngest"], None), "welfare": (WELFARE, "해당없음"),
            "supported": ([None, False, True], False),
        }
    if program in ("sh_jeonse2", "sh_jeonse"):
        attrs = {
            "home": (["무주택", "주택보유"], "무주택"), "marital": (MARITALS, "혼인중"), "size": (SIZES + [6], 3),
            "kids": (pools["kids"], []), "count": (COUNTS, 0), "dual": ([True, False], False),
            "income": (J2_INCOME if program == "sh_jeonse2" else JS_INCOME, 1), "assets": (J_ASSETS, 1),
            "car": (J_CARS, 0), "age": ([17, 18, 19, 40, 64, 65], 33),
            "residence_area": ([None, "서울특별시", "의정부시", "고양시", "부산광역시"], "서울특별시"),
        }
        if program == "sh_jeonse2":
            attrs.update(marriage=(pools["marriage"], date(2025, 1, 1)), owned5=([None, False, True], False))
        return attrs
    if program == "permanent_rental":
        tri = ([None, False, True], False)
        return {
            "home": (["무주택", "주택보유"], "무주택"), "marital": (MARITALS, "혼인중"),
            "age": ([17, 18, 19, 40, 64, 65, 70], 70 if "주거약자" in layer else 40),
            "size": ([1, 2, 3, 4, 7, 8], 3), "kids": (pools["kids"], []), "count": (COUNTS, 0),
            "income": (PERM_INCOME, 1), "assets": (PERM_ASSETS, 1), "car": (CARS, 0),
            "welfare": (WELFARE, "해당없음"), "supported": tri, "weak": (WEAK, "해당없음"), "spouse_dis": tri,
            "lmr": tri, "merit": tri, "defector": tri, "facility": tri, "eparent0": tri,
        }
    if program == "public_rental":     # G4: 소득·자산을 보지 않는다 — 흔들어도 판정이 바뀌지 않는지 함께 기록
        tri = ([None, False, True], False)
        return {
            "home": (["무주택", "주택보유"], "무주택"), "marital": (MARITALS, "미혼"), "age": ([17, 18, 19, 40, 70], 40),
            "size": ([1, 3], 1), "kids": (pools["kids"][:3], []), "count": (COUNTS[:1], 0),
            "income": ([None, 0, 90_000_000], 1), "assets": ([None, 0, 900_000_000], 1), "car": (CARS[:3], 0),
            "residence_area": ([None, "서울특별시", "인천광역시", "고양시", "가평군", "부산광역시", "강원특별자치도", "해당없음"],
                               "서울특별시"),
            "account": ([True, False], True), "submonths": ([0, 5, 6, 12, 24], 12), "subcount": ([0, 5, 6, 12, 24], 12),
            "rewin": tri,
        }
    if program == "sh_land_sale":   # G3-3: 총자산·청년 본인 소득·부모 자산·투기과열 1순위
        attrs = _program_attributes("public_sale", layer, pools)
        tri = ([None, False, True], False)
        attrs.update(assets=(SH_ASSETS_POOL, 1), realestate=([None], None), selfown=tri, won5=tri,
                     parents_assets=([None, 0, 1_035_000_000, 1_035_000_001], 0))
        if layer == "청년":
            attrs.update(marital=(MARITALS, "미혼"), age=([18, 19, 39, 40], 30), size=([1, 2, 3], 1),
                         income=(SH_YOUTH_INCOME_POOL, 1))
        return attrs
    if program == "public_sale":   # G3: 유형별 소득 비율·맞벌이 200%·출산 가산, 부동산·자동차, 유형 요건
        tri = ([None, False, True], False)
        attrs = {
            "home": (["무주택", "주택보유"], "무주택"), "age": ([17, 19, 33, 66], 33), "marital": (MARITALS, "혼인중"),
            "size": ([1, 2, 3, 4, 8, 9], 3), "kids": (pools["kids"], []), "count": (COUNTS[:1], 0),
            "dual": ([True, False], False), "income": (SALE_INCOME_POOL, 1), "assets": ([None, 0], 0),
            "car": (CARS, 0), "realestate": (SALE_RE_POOL, 0),
            "marriage": (pools["marriage"], date(2025, 1, 1)), "has_children": (HAS_CHILDREN, None),
            "youngest": (pools["youngest"], None), "head": (HEADS, "세대주"),
            "residence_area": ([None, "서울특별시", "고양시", "부산광역시", "해당없음"], "서울특별시"),
            "account": ([True, False], True), "submonths": ([0, 5, 6, 11, 12, 24], 24), "subcount": ([0, 5, 6, 11, 12, 24], 24),
            "rewin": tri, "special": tri, "everown": tri, "tax5": ([None, False, True], True),
            "eparent3": ([None, False, True], True), "deposit": ([None, 0, 5_999_999, 6_000_000, 20_000_000], 10_000_000),
        }
        if layer == "다자녀가구":
            attrs["kids"] = (pools["kids"], [AFTER, BEFORE_MINOR])
        elif layer == "신생아":
            attrs["kids"] = (pools["kids"], [AFTER2])
        elif layer == "신혼부부":
            attrs["marital"] = (MARITALS, "혼인중")
        return attrs
    if program == "newlywed_town_sale":   # G3: 3인 이하 한 칸·맞벌이 200%·출산 가산 경계, 저축 6개월·6회
        tri = ([None, False, True], False)
        return {
            "home": (["무주택", "주택보유"], "무주택"), "age": ([17, 18, 19, 33], 33),
            "marital": (MARITALS, {"신혼부부": "혼인중", "예비신혼부부": "예비신혼", "한부모": "한부모"}[layer]),
            "size": ([1, 2, 3, 4, 8, 9], 3), "kids": (pools["kids"], [AFTER] if layer == "한부모" else []),
            "count": (COUNTS[:1], 0), "dual": ([True, False], False),
            "income": (NH_INCOME_POOL, 1), "assets": (NH_ASSETS_POOL, 1), "car": (CARS[:3], 0),
            "marriage": (pools["marriage"], date(2025, 1, 1)), "has_children": (HAS_CHILDREN, None),
            "youngest": (pools["youngest"], None),
            "residence_area": ([None, "서울특별시", "고양시", "부산광역시", "해당없음"], "서울특별시"),
            "account": ([True, False], True), "submonths": ([0, 5, 6, 24], 12), "subcount": ([0, 5, 6, 24], 12),
            "rewin": tri, "special": tri,
        }
    if program == "integrated_rental":
        attrs = {
            "home": (["무주택", "주택보유"], "무주택"), "size": ([1, 2, 3, 4, 7, 8, 9], 3),
            "kids": (pools["kids"], []), "count": (COUNTS, 0),
            "income": (INT_INCOME, 1), "assets": (NAT_ASSETS, 1), "car": (CARS, 0),
        }
        if layer == "청년":
            attrs.update(marital=(MARITALS, "미혼"), age=([17, 18, 19, 39, 40], 30), head=(HEADS, "세대주"),
                         size=([1, 2, 3, 4, 7, 8, 9], 1))
        elif layer in ("신혼부부", "한부모"):
            attrs.update(marital=(MARITALS, "혼인중" if layer == "신혼부부" else "한부모"), age=([17, 18, 19, 40], 33),
                         dual=([True, False], False), marriage=(pools["marriage"], date(2025, 1, 1)),
                         has_children=(HAS_CHILDREN, None), youngest=(pools["youngest"], None))
            if layer == "한부모":     # 6세 이하 자녀가 통과 쪽 기본값
                attrs["kids"] = (pools["kids"], [AFTER])
        else:
            attrs.update(marital=(MARITALS, "혼인중"),
                         age=([17, 18, 19, 40, 64, 65, 70], 70 if layer == "고령자" else 40))
        return attrs
    if program == "national_rental":
        return {
            "home": (["무주택", "주택보유"], "무주택"), "marital": (MARITALS, "혼인중"),
            "age": ([17, 18, 19, 40, 64, 65, 70], 70 if "고령자" in layer else 40),
            "size": ([1, 2, 3, 4, 6, 7, 8, 9], 3), "kids": (pools["kids"], []), "count": (COUNTS, 0),
            "income": (NAT_INCOME, 1), "assets": (NAT_ASSETS, 1), "car": (CARS, 0),
        }
    return {   # jeonse — 소득·자산 요건이 없으므로 아무 값이나 넣어도 판정이 바뀌지 않는지 기록
        "home": (["무주택", "주택보유"], "무주택"), "marital": (MARITALS, "미혼"), "age": ([17, 18, 19, 40], 40),
        "size": (SIZES, 3), "kids": (pools["kids"], None), "count": (COUNTS, 0),
        "income": ([None, 0, 90_000_000], 1), "assets": ([None, 0, 900_000_000], 1), "car": (CARS, 0),
    }
# 서울·연접(통과) / 경기 비연접·지방(불충족) / 해당없음 / 모름. 손으로 고른 고정 값.
REGIONS = [None, "서울특별시", "고양시", "인천광역시", "수원시", "의왕시", "부산광역시", "해당없음"]
GROUPS: List[Tuple[str, str]] = [
    ("N1", "신혼부부"), ("N1", "한부모"), ("N2", "대학생"),
    ("N3", "대학생"), ("N3", "청년"), ("N3", "신혼부부"), ("N3", "한부모"),
    # C1 — 뒤에 덧붙여야 기존 그룹의 난수 시드(그룹 순번)가 바뀌지 않는다
    ("N4", "신혼부부"), ("N4", "한부모"), ("N5", "대학생"), ("N5", "청년"),
    ("N6", "대학생"), ("N6", "청년"), ("N6", "신혼부부"), ("N6", "한부모"),
    ("N7", "신혼부부"), ("N7", "한부모"), ("N8", "신혼부부"), ("N8", "한부모"),
    # C2
    ("N9", "대학생"), ("N10", "대학생"), ("N10", "청년"), ("N10", "신혼부부"), ("N10", "한부모"),
    # C3 — 새 계층
    ("N6", "고령자"), ("N9", "고령자"), ("N10", "고령자"), ("N6", "산업단지근로자"),
    ("N10", "주거급여수급자"), ("N5", "지역전략산업종사자"),
    # C4a — 순위·유형 트랙
    ("N11", "청년"), ("N11", "대학생"), ("N11", "취업준비생"), ("N12", "청년"), ("N12", "대학생"), ("N12", "취업준비생"),
    ("N13", "신혼·신생아"), ("N14", "신혼·신생아"), ("N15", "신혼·신생아"), ("N16", "일반"), ("N17", "일반"),
    # C4b — SH
    ("N18", "신혼·신생아"), ("N19", "신혼·신생아"), ("N20", "신혼·신생아"), ("N21", "신혼·신생아"), ("N22", "일반"),
    # C5a — 주거약자용 주택형(기본 계층 + 주거약자 조건)
    ("N4", "신혼부부(주거약자용)"), ("N4", "한부모(주거약자용)"), ("N7", "신혼부부(주거약자용)"), ("N7", "한부모(주거약자용)"),
    ("N8", "신혼부부(주거약자용)"), ("N8", "한부모(주거약자용)"), ("N5", "주거약자(26A1/B1형)"),
    # C5b — SH 장기전세2·장기전세(면적별 변형 계층)
    ("N23", "신혼부부(전용 60㎡ 이하)"), ("N23", "신혼부부(전용 60㎡ 초과)"),
    ("N24", "신혼부부(전용 60㎡ 이하)"), ("N24", "신혼부부(주거약자형·전용 60㎡ 이하)"), ("N24", "신혼부부(전용 60㎡ 초과)"),
    ("N25", "일반(전용 60㎡ 이하)"), ("N25", "일반(주거약자형·전용 60㎡ 이하)"), ("N25", "일반(전용 60㎡ 초과)"),
    ("N26", "일반(전용 60㎡ 이하)"), ("N26", "일반(주거약자형·전용 60㎡ 이하)"), ("N26", "일반(전용 60㎡ 초과)"),
    # C5c — 장기전세 우선공급(서울시 매입형 60㎡ 이하)
    ("N25", "일반(우선공급·장애인)"), ("N25", "일반(우선공급·노부모부양)"), ("N25", "일반(우선공급·2자녀이상)"),
    ("N25", "일반(우선공급·국가유공자)"),
    ("N26", "일반(우선공급·고령자)"), ("N26", "일반(우선공급·장애인)"), ("N26", "일반(우선공급·노부모부양)"),
    ("N26", "일반(우선공급·2자녀이상)"), ("N26", "일반(우선공급·국가유공자)"),
    # E1 — 공릉·봉천 주거약자용 주택(C5a 누락분)
    ("N1", "신혼부부(주거약자용)"), ("N1", "한부모(주거약자용)"), ("N2", "대학생(주거약자용)"),
    # B단계 — 처음 보는 공고 검증(초안은 등록 전에 docs/draft-checks에 얼림)
    ("N27", "대학생"), ("N27", "청년"), ("N27", "신혼부부"), ("N27", "한부모"), ("N27", "고령자"), ("N27", "주거급여수급자"),
    ("N28", "신혼부부"), ("N28", "한부모"), ("N28", "신혼부부(주거약자용)"), ("N28", "한부모(주거약자용)"),
    # G2 — 처음 보는 공고 검증(초안은 docs/draft-checks/X-*.draft.json)
    ("N29", "신혼·신생아"),
    ("N30", "일반"), ("N31", "일반"), ("N32", "일반"), ("N32", "일반(고령자 주택형)"),
    ("N33", "일반"), ("N33", "일반(주거약자용)"), ("N34", "일반"),
    ("N35", "청년"), ("N35", "신혼부부"), ("N35", "한부모"), ("N35", "고령자"), ("N35", "일반"),
    ("N36", "청년"), ("N36", "신혼부부"), ("N36", "한부모"), ("N36", "고령자"), ("N36", "일반"),
    *[(f"N{n}", "일반") for n in range(37, 45)],
    *[(f"N{n}", layer) for n in range(45, 49) for layer in ("신혼부부", "예비신혼부부", "한부모")],
    *[("N49", layer) for layer in ("다자녀가구", "노부모부양", "생애최초", "신혼부부", "신생아", "일반공급(전용 60㎡ 이하)",
                                   "일반공급(전용 60㎡ 초과)")],
    *[("N50", layer) for layer in ("다자녀가구", "노부모부양", "생애최초", "신혼부부", "신생아", "일반공급(전용 60㎡ 초과)")],
    *[(nid, layer) for nid in ("N51", "N52") for layer in ("청년", "신혼부부", "생애최초", "신생아", "일반공급")],
    ("N53", "일반"), ("N53", "일반(주거약자용)"), ("N54", "일반"), ("N55", "고령자"),
    *[("N56", layer) for layer in ("청년", "신혼부부", "생애최초", "일반공급")],
    *[("N57", layer) for layer in ("청년", "다자녀가구", "노부모부양", "생애최초", "신혼부부", "일반공급")],
]
WEAK = [None, "해당없음", "장애인", "국가유공자(상이 1~7급)", "고엽제후유의증환자(경도 이상)"]

INCOMES = [
    0, 1, 1_000_000, 3_000_000, 4_576_035, 4_576_036,
    4_576_037, 5_000_000, 6_452_896, 6_452_897, 6_452_898, 7_039_523,
    7_039_524, 7_039_525, 7_626_150, 7_626_151, 7_626_152, 8_168_428,
    8_168_429, 8_168_430, 8_212_777, 8_212_778, 8_212_779, 8_802_201,
    8_802_202, 8_802_203, 8_985_271, 8_985_272, 8_985_273, 9_326_984,
    9_326_985, 9_326_986, 9_682_421, 9_682_422, 9_682_423, 9_802_114,
    9_802_115, 9_802_116, 9_906_262, 9_906_263, 9_906_264, 10_259_683,
    10_259_684, 10_259_685, 10_485_540, 10_485_541, 10_485_542, 10_562_641,
    10_562_642, 10_562_643, 10_618_957, 10_618_958, 10_618_959, 10_896_888,
    10_896_889, 10_896_890, 11_064_818, 11_064_819, 11_064_820, 11_192_381,
    11_192_382, 11_192_383, 11_435_800, 11_435_801, 11_435_802, 11_442_862,
    11_442_863, 11_442_864, 11_476_166, 11_476_167, 11_476_168, 11_887_515,
    11_887_516, 11_887_517, 12_055_444, 12_055_445, 12_055_446, 12_125_080,
    12_125_081, 12_125_082, 12_323_082, 12_323_083, 12_323_084, 12_466_793,
    12_466_794, 12_466_795, 12_878_141, 12_878_142, 12_878_143, 13_046_071,
    13_046_072, 13_046_073, 13_057_778, 13_057_779, 13_057_780, 13_457_419,
    13_457_420, 13_457_421, 13_868_767, 13_868_768, 13_868_769, 14_036_697,
    14_036_698, 14_036_699, 14_448_045, 14_448_046, 14_448_047, 15_027_323,
    15_027_324, 15_027_325, 20_000_000,
]
SIZES = [1, 2, 3, 4, 5, 7]
ASSETS = [None, 0] + [v + d for v in (108_000_000, 119_000_000, 130_000_000, 251_000_000, 276_000_000,
                                      301_000_000, 345_000_000, 379_000_000, 413_000_000) for d in (-1, 0, 1)]
CARS = [0, 1, "확인불가"] + [v + d for v in (45_420_000, 49_960_000, 54_510_000) for d in (-1, 0, 1)]
COUNTS = [0, 1, 2, 3]
STATUSES = [None, "재학중", "입학예정", "복학예정", "취업준비생", "해당없음"]
HEADS = [None, "세대주", "세대원", "기타"]
ROOKIES = [None, True, False]
AGES = [18, 19, 30, 39, 40, 45]
MARITALS = ["미혼", "혼인중", "예비신혼", "한부모"]
HAS_CHILDREN = [None, True, False]
AFTER, AFTER2, BEFORE_MINOR = date(2024, 1, 1), date(2025, 6, 1), date(2015, 5, 5)


class Rng:
    """splitmix64 — 파이썬 버전과 무관하게 항상 같은 수열."""

    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def _next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def choice(self, seq):
        return seq[self._next() % len(seq)]

    def chance(self, p: float) -> bool:
        return (self._next() % 10_000) < int(p * 10_000)


def _around(d: date) -> List[date]:
    from datetime import timedelta
    return [d - timedelta(days=1), d, d + timedelta(days=1)]


def _pools(nid: str) -> Dict[str, list]:
    from datetime import timedelta
    d = DATES[nid]
    return {
        "kids": [None, [], [AFTER], [AFTER, BEFORE_MINOR], [BEFORE_MINOR], [AFTER, AFTER2, BEFORE_MINOR],
                 [AFTER, d["adult"]], [AFTER, d["adult"] + timedelta(days=1)],
                 [date(2023, 3, 28)], [date(2023, 3, 27)]],
        "grad": [None] + _around(d["grad"]) + [date(2000, 1, 1), d["ann"]],
        "youngest": [None] + _around(d["child"]) + [date(2000, 1, 1), date(2030, 1, 1)]
                    + (_around(d["newborn"]) if "newborn" in d else []) + (_around(d["minor"]) if "minor" in d else []),
        "marriage": [None] + _around(d["marriage"]) + [date(2000, 1, 1), date(2025, 6, 1)],
    }


def _attributes(layer: str, pools, nid: str = "") -> Dict[str, Tuple[list, object]]:
    """계층별 (값 풀, 기준 프로필의 기본값). 기본값은 '모든 조건이 통과'하는 쪽."""
    if PROGRAM_OF.get(nid) == "sh_land_sale":
        return _program_attributes("sh_land_sale", layer, pools)
    if PROGRAM_OF.get(nid) == "public_sale":                # G3: 일반공급(전용 60㎡ 이하/초과)도 사업 전용 풀
        return _program_attributes("public_sale", layer, pools)
    if PROGRAM_OF.get(nid) == "select_rental":              # G7: SH 토지임대부 풀(청년·다자녀·노부모 입력 포함) + 선택형 금액 경계
        attrs = _program_attributes("sh_land_sale", layer, pools)
        attrs.update(assets=(SHARE_ASSETS, 1), marriage=(pools["marriage"], date(2022, 1, 1)),
                     parents_assets=([None, 0, 1_083_000_000, 1_083_000_001], 0),
                     income=(SHARE_YOUTH_INCOME if layer == "청년" else SELECT_INCOME, 1))
        if layer == "다자녀가구":
            attrs.update(kids=(pools["kids"], [date(2010, 1, 1), date(2012, 1, 1), date(2015, 1, 1)]), size=([2, 3, 5, 8], 5))
        return attrs
    if PROGRAM_OF.get(nid) == "share_sale":                 # G6: SH 토지임대부 풀(청년·부모 자산 등) + 나눔형 금액 경계
        attrs = _program_attributes("sh_land_sale", layer, pools)
        attrs.update(assets=(SHARE_ASSETS, 1), marriage=(pools["marriage"], date(2022, 1, 1)),
                     parents_assets=([None, 0, 1_083_000_000, 1_083_000_001], 0),
                     income=(SHARE_YOUTH_INCOME if layer == "청년" else SHARE_INCOME, 1))
        return attrs
    if PROGRAM_OF.get(nid) == "elderly_welfare":            # G5: 영구임대 신분 풀 + 65세 경계 + 50·70% 적용 금액(기본은 3순위 일반)
        attrs = _program_attributes("permanent_rental", layer, pools)
        attrs.update(age=([17, 19, 40, 64, 65, 70], 70), income=(ELD_INCOME, 1), size=([1, 2, 3, 7, 8], 2))
        return attrs
    if PROGRAM_OF.get(nid) == "sh_permanent_rental":        # G5: LH 영구임대 풀 + SH 금액 경계 + 서울 거주
        attrs = _program_attributes("permanent_rental", layer, pools)
        attrs.update(income=(SHP_INCOME, 1), assets=(SHP_ASSETS, 1), car=(SHP_CARS, 0),
                     residence_area=([None, "서울특별시", "고양시", "부산광역시", "해당없음"], "서울특별시"),
                     weak=(WEAK, "장애인"))     # 2순위(일반 50%)가 없어 기본은 1순위 바목(장애인, 소득·자산 확인)
        return attrs
    if PROGRAM_OF.get(nid) == "sh_national_rental":         # G5: 국민임대 풀 + 서울 거주(상계장암 인근 시는 확인 필요) + 주거약자
        attrs = _program_attributes("national_rental", layer, pools)
        attrs["residence_area"] = ([None, "서울특별시", "의정부시", "포천시", "수원시", "부산광역시", "해당없음"], "서울특별시")
        if "주거약자" in layer:
            attrs["weak"] = (WEAK, "장애인")
        return attrs
    if PROGRAM_OF.get(nid) == "national_rental":            # G2: 변형 계층(고령자 주택형)도 사업 전용 풀
        return _program_attributes("national_rental", layer, pools)
    if PROGRAM_OF.get(nid) == "permanent_rental":           # G2: 거주 요건 시는 공고마다 다르다
        attrs = _program_attributes("permanent_rental", layer, pools)
        attrs["residence_area"] = ([None, "양주시", "부천시", "서울특별시", "해당없음"], CITY_OF[nid])
        return attrs
    if PROGRAM_OF.get(nid) in ("sh_jeonse2", "sh_jeonse"):   # C5b: 사업 전용 풀(변형 계층 공통) + 주거약자형이면 주거약자
        attrs = _program_attributes(PROGRAM_OF[nid], layer, pools)
        if "주거약자" in layer:
            attrs["weak"] = (WEAK, "장애인")
        if "우선공급" in layer:   # C5c: 유형별 입력(통과 쪽 기본값)
            attrs["weak"] = (WEAK, "장애인")
            attrs["spouse_dis"] = ([None, False, True], False)
            attrs["eparent"] = ([None, False, True], True)
            attrs["veteran"] = ([None, False, True], False)
            if "2자녀" in layer:
                attrs["kids"] = (pools["kids"], [AFTER, BEFORE_MINOR])
            if "고령자" in layer:
                attrs["age"] = ([40, 64, 65, 70], 70)
        return attrs
    if "(" in layer:                  # 주택형 변형 계층(C5): 기본 계층 입력 + 주거약자 유형·나이
        base = layer.split("(")[0]
        bases = ["지역전략산업종사자", "청년", "대학생"] if base == "주거약자" else [base]
        attrs = {}
        for b in bases:
            for k, val in _layer_attributes(b, pools).items():
                attrs.setdefault(k, val)
        attrs["weak"] = (WEAK, "장애인")
        attrs.setdefault("age", ([30, 64, 65, 70], 33))
    else:
        attrs = (_program_attributes(PROGRAM_OF[nid], layer, pools) if nid in PROGRAM_OF
                 else _layer_attributes(layer, pools))
    for i, f in enumerate(REGION_FIELDS_BY_LAYER.get(nid, {}).get(layer, [])):
        attrs[f] = (REGIONS, "서울특별시" if i == 0 else None)   # 기본: 본인 거주지만 서울, 나머지 모름
    return attrs


def _layer_attributes(layer: str, pools) -> Dict[str, Tuple[list, object]]:
    if layer == "주거급여수급자":   # 원문에 소득·자산 조항 없음 — 다른 항목도 함께 흔들어 영향이 없는지 기록
        return {"home": (["무주택", "주택보유"], "무주택"), "size": (SIZES, 3),
                "income": (INCOMES, 1), "assets": ([None, 0, 1_000_000_000], 1), "car": (CARS, 0),
                "kids": (pools["kids"], None), "count": (COUNTS, 0), "marital": (MARITALS, "미혼"),
                "benefit": ([None, "수급자", "수급권자", "해당없음"], "수급자")}
    common = {
        "home": (["무주택", "주택보유"], "무주택"),
        "size": (SIZES, 3), "kids": (pools["kids"], None), "count": (COUNTS, 0),
        "income": (INCOMES, 1), "assets": (ASSETS, 1), "car": (CARS, 0),
    }
    if layer == "대학생":
        return {**common, "marital": (["미혼", "혼인중"], "미혼"), "status": (STATUSES, "재학중"),
                "grad": (pools["grad"], None)}
    if layer == "청년":
        return {**common, "marital": (["미혼", "혼인중"], "미혼"), "age": (AGES, 30),
                "head": (HEADS, "세대주"), "rookie": (ROOKIES, None)}
    if layer == "고령자":
        return {**common, "marital": (MARITALS, "혼인중"), "age": ([64, 65, 66, 80], 70),
                "dual": ([True, False], False)}
    if layer == "산업단지근로자":
        return {**common, "marital": (MARITALS, "미혼"), "dual": ([True, False], False),
                "workplace": ([None, "산업단지 입주기업", "산업단지 교육·연구기관", "경제자유구역 입주 중소기업", "해당없음"],
                              "산업단지 입주기업"),
                "affiliation": ([None, "소속", "비소속 1년 이상 근무(예정)", "비소속 1년 미만"], "소속")}
    if layer == "지역전략산업종사자":
        return {**common, "marital": (MARITALS, "미혼"), "age": (AGES, 30), "dual": ([True, False], False),
                "rtype": ([None, "콘텐츠산업 종사자", "전문예술법인·단체 종사자", "등록 예술인", "부천시 추천자", "해당없음"],
                          "등록 예술인")}
    default_marital = "혼인중" if layer == "신혼부부" else "한부모"
    return {**common, "marital": (MARITALS, default_marital), "dual": ([True, False], False),
            "has_children": (HAS_CHILDREN, None), "youngest": (pools["youngest"], None),
            "marriage": (pools["marriage"], date(2025, 1, 1))}


def _profile(layer: str, v: Dict[str, object], tag: str) -> HouseholdProfile:
    return HouseholdProfile(
        tag, v.get("age", 22 if layer == "대학생" else 33), v["marital"], v["home"],
        house_head_status=v.get("head"), household_size=v["size"], monthly_income=v["income"],
        total_assets=v["assets"], car_value=v["car"], dual_income=v.get("dual", False),
        is_social_rookie=v.get("rookie"), student_status=v.get("status"),
        grad_or_dropout_date=v.get("grad"), marriage_date=v.get("marriage"),
        has_children=v.get("has_children"), youngest_child_birth_date=v.get("youngest"),
        children_birth_dates=v["kids"], young_child_count=v["count"],
        **{f: v[f] for f in ("residence_area", "school_area", "income_base_area", "spouse_residence_area",
                             "spouse_income_base_area", "workplace_area") if f in v},
        **{field: v[key] for key, field in (("workplace", "industrial_workplace"),
                                            ("affiliation", "industrial_affiliation"),
                                            ("benefit", "housing_benefit_status"),
                                            ("rtype", "regional_industry_type"),
                                            ("welfare", "welfare_status"), ("parent_welfare", "parent_welfare_status"),
                                            ("registered", "registered_with_parents"),
                                            ("supported", "is_supported_single_parent"),
                                            ("employed", "is_employed"), ("parents_count", "parents_count"),
                                            ("parents_income", "parents_monthly_income"),
                                            ("parents_assets", "parents_total_assets"),
                                            ("parents_car", "parents_car_value"),
                                            ("weak", "housing_weak_type"),
                                            ("owned5", "owned_home_in_5y"),
                                            ("spouse_dis", "disabled_spouse_qualifies"),
                                            ("eparent", "supports_elderly_parent_1y"),
                                            ("veteran", "veteran_priority_notified"),
                                            ("lmr", "livelihood_medical_recipient"), ("merit", "merit_person"),
                                            ("defector", "north_korean_defector"), ("facility", "child_facility_leaver"),
                                            ("eparent0", "supports_elderly_parent"), ("rewin", "rewin_restricted"),
                                            ("special", "past_special_supply"), ("realestate", "real_estate_value"),
                                            ("everown", "household_ever_owned_home"), ("deposit", "subscription_deposit"),
                                            ("tax5", "income_tax_5y"), ("eparent3", "supports_elderly_parent_3y"),
                                            ("selfown", "self_ever_owned_home"), ("won5", "household_won_5y"),
                                            ("account", "has_subscription_account"),
                                            ("submonths", "subscription_months"),
                                            ("subcount", "subscription_payment_count")) if key in v})


# 통과 값에 가중해서 '모든 조건이 통과 근처'인 영역(경계가 실제로 판정을 가르는 영역)을 충분히 뽑는다
_PASS = {"marital": 0.8, "home": 0.8, "status": 0.7, "head": 0.7, "car": 0.85, "residence_area": 0.6}
RANDOM_PER_GROUP = 3500


def cases(only=None) -> Iterator[Tuple[str, str, HouseholdProfile]]:
    """(공고, 계층, 프로필) — 항상 같은 순서·같은 값. only=[(공고, 계층), …]이면 그 그룹만 만든다(그룹의 난수 시드는
    GROUPS 안의 위치로 정해지므로 전체를 만들 때와 같은 입력이 나온다)."""
    for gi, (nid, layer) in enumerate(GROUPS):
        if only is not None and (nid, layer) not in only:
            continue
        attrs = _attributes(layer, _pools(nid), nid)
        base = {k: default for k, (_pool, default) in attrs.items()}
        n = 0
        # 1) 한 번에 한 항목만 풀 전체를 훑는다(기준 프로필 대비)
        for key, (pool, _d) in attrs.items():
            for value in pool:
                yield nid, layer, _profile(layer, {**base, key: value}, f"S{gi}-{n}")
                n += 1
        # 2) 가구원수 × 자녀 × 맞벌이/세대 구분 × 자산·소득 결합(결정표 영역)
        for size in SIZES:
            for kids in attrs["kids"][0]:
                for count in COUNTS[:3]:
                    for assets in attrs["assets"][0][::4]:
                        yield nid, layer, _profile(layer, {**base, "size": size, "kids": kids, "count": count,
                                                           "assets": assets}, f"T{gi}-{n}")
                        n += 1
        # 3) 가중 무작위
        rng = Rng(20261100 + gi)
        for i in range(RANDOM_PER_GROUP):
            values = {}
            for key, (pool, default) in attrs.items():
                p = _PASS.get(key)
                values[key] = default if (p is not None and rng.chance(p) and default in pool) else rng.choice(pool)
            yield nid, layer, _profile(layer, values, f"R{gi}-{i}")
