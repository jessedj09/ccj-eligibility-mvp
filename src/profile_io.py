# -*- coding: utf-8 -*-
"""profile_io.py — 입력 프로필 ↔ JSON (D2b).

"내 조건" 저장 파일과 판정 API 요청 본문이 같은 형식이다. 서버는 프로필을 저장하지 않는다 — 소득·자산 같은 개인정보라
파일은 사용자가 내려받아 갖고 있다가 다시 불러온다.

형식(SCHEMA "ccj-profile/1"):
    {"schema": "ccj-profile/1",
     "master": {MasterProfile의 범위별 항목 — home_self, income_household, birth_date, …},
     "common": {그 밖의 HouseholdProfile 항목 — marital_status, household_size, children_birth_dates, …}}
날짜는 "YYYY-MM-DD" 문자열. master는 모름이면 키를 빼거나 null, common의 null은 "모름"으로 그대로 전달된다.
"""
import dataclasses
import typing
from datetime import date
from typing import Any, Dict

from matcher import MasterProfile
from rule_engine import HouseholdProfile

SCHEMA = "ccj-profile/1"

MASTER_FIELDS = tuple(f.name for f in dataclasses.fields(MasterProfile) if f.name != "common")
HOUSEHOLD_FIELDS = tuple(f.name for f in dataclasses.fields(HouseholdProfile))
# MasterProfile이 범위별로 따로 받거나 매처가 계층마다 계산하는 값 — common에 넣으면 모호하므로 거절한다
DERIVED = ("home_ownership", "monthly_income", "total_assets", "car_value")


class ProfileFormatError(ValueError):
    pass


def _date_kind(cls, name: str) -> str:
    """필드 타입이 날짜인지("date"), 날짜 목록인지("list"), 아닌지("")."""
    hint = str(typing.get_type_hints(cls)[name])
    if "List[datetime.date]" in hint:
        return "list"
    return "date" if "datetime.date" in hint else ""


def _dump(v: Any) -> Any:
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, list):
        return [_dump(x) for x in v]
    return v


def _load(cls, name: str, v: Any, where: str) -> Any:
    kind = _date_kind(cls, name)
    if v is None or not kind:
        return v
    try:
        if kind == "list":
            if not isinstance(v, list):
                raise TypeError
            return [date.fromisoformat(x) for x in v]
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        raise ProfileFormatError(f"{where}.{name}: 날짜는 'YYYY-MM-DD' 형식이어야 합니다 — {v!r}") from None


def master_to_dict(m: MasterProfile) -> Dict[str, Any]:
    master = {k: _dump(getattr(m, k)) for k in MASTER_FIELDS if getattr(m, k) is not None}
    # common은 모름(null)도 그대로 둔다 — 기본값이 None이 아닌 항목(가구원수 1, 맞벌이 False 등)과 섞이지 않게
    common = {k: _dump(v) for k, v in m.common.items()}
    return {"schema": SCHEMA, "master": master, "common": common}


def master_from_dict(d: Dict[str, Any]) -> MasterProfile:
    if not isinstance(d, dict) or d.get("schema") != SCHEMA:
        raise ProfileFormatError(f"프로필 파일 형식이 아닙니다(schema가 '{SCHEMA}'여야 함)")
    master, common = d.get("master") or {}, d.get("common") or {}
    extra = set(d) - {"schema", "master", "common"}
    if extra:
        raise ProfileFormatError(f"알 수 없는 항목: {sorted(extra)}")
    bad = set(master) - set(MASTER_FIELDS)
    if bad:
        raise ProfileFormatError(f"master에 알 수 없는 항목: {sorted(bad)}")
    bad = set(common) - set(HOUSEHOLD_FIELDS)
    if bad:
        raise ProfileFormatError(f"common에 알 수 없는 항목: {sorted(bad)}")
    clash = set(common) & set(DERIVED)
    if clash:
        raise ProfileFormatError(f"common의 {sorted(clash)}는 master의 본인·세대 항목(home_self, income_household 등)으로 "
                                 "넣어야 합니다 — 계층마다 범위가 달라 매처가 계산합니다")
    kw = {k: _load(MasterProfile, k, v, "master") for k, v in master.items()}
    kw["common"] = {k: _load(HouseholdProfile, k, v, "common") for k, v in common.items()}
    return MasterProfile(**kw)


def household_from_dict(d: Dict[str, Any]) -> HouseholdProfile:
    """공고·계층 하나를 판정할 때의 프로필(HouseholdProfile 필드 그대로). 판정 API /evaluate용."""
    if not isinstance(d, dict):
        raise ProfileFormatError("profile은 객체여야 합니다")
    bad = set(d) - set(HOUSEHOLD_FIELDS)
    if bad:
        raise ProfileFormatError(f"알 수 없는 항목: {sorted(bad)}")
    kw = {k: _load(HouseholdProfile, k, v, "profile") for k, v in d.items()}
    kw.setdefault("profile_id", "api")
    try:
        return HouseholdProfile(**kw)
    except TypeError as e:
        raise ProfileFormatError(f"필수 항목이 빠졌습니다: {e}") from None
