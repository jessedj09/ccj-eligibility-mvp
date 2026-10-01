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
}
GROUPS: List[Tuple[str, str]] = [
    ("N1", "신혼부부"), ("N1", "한부모"), ("N2", "대학생"),
    ("N3", "대학생"), ("N3", "청년"), ("N3", "신혼부부"), ("N3", "한부모"),
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
        "youngest": [None] + _around(d["child"]) + [date(2000, 1, 1), date(2030, 1, 1)],
        "marriage": [None] + _around(d["marriage"]) + [date(2000, 1, 1), date(2025, 6, 1)],
    }


def _attributes(layer: str, pools) -> Dict[str, Tuple[list, object]]:
    """계층별 (값 풀, 기준 프로필의 기본값). 기본값은 '모든 조건이 통과'하는 쪽."""
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
        children_birth_dates=v["kids"], young_child_count=v["count"])


# 통과 값에 가중해서 '모든 조건이 통과 근처'인 영역(경계가 실제로 판정을 가르는 영역)을 충분히 뽑는다
_PASS = {"marital": 0.8, "home": 0.8, "status": 0.7, "head": 0.7, "car": 0.85}
RANDOM_PER_GROUP = 3500


def cases() -> Iterator[Tuple[str, str, HouseholdProfile]]:
    """(공고, 계층, 프로필) — 항상 같은 순서·같은 값."""
    for gi, (nid, layer) in enumerate(GROUPS):
        attrs = _attributes(layer, _pools(nid))
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
