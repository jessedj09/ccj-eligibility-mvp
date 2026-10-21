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
              "N18": "sh_newlywed", "N19": "sh_newlywed", "N20": "sh_newlywed", "N21": "sh_newlywed", "N22": "jeonse"}
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
]

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
                                            ("parents_car", "parents_car_value")) if key in v})


# 통과 값에 가중해서 '모든 조건이 통과 근처'인 영역(경계가 실제로 판정을 가르는 영역)을 충분히 뽑는다
_PASS = {"marital": 0.8, "home": 0.8, "status": 0.7, "head": 0.7, "car": 0.85, "residence_area": 0.6}
RANDOM_PER_GROUP = 3500


def cases() -> Iterator[Tuple[str, str, HouseholdProfile]]:
    """(공고, 계층, 프로필) — 항상 같은 순서·같은 값."""
    for gi, (nid, layer) in enumerate(GROUPS):
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
