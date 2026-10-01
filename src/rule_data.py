# -*- coding: utf-8 -*-
"""
rule_data.py — JSON 규칙 파일을 NoticeRuleSet으로 로드하는 로더 + 조건식 컴파일러 (B단계 P1)
==============================================================================================
설계: docs/06-rule-data-design.md. 규칙(조건·기준값·결정표·출처)은 `rules/` 아래 JSON에 있고, 이 모듈은
그것을 **기존과 같은 RuleCondition/NoticeRuleSet 객체**로 만들어 준다. 그래서 evaluate()/explain()/
화면은 바뀌지 않는다.

닫힌 연산자 집합만 허용한다(임의 코드 실행 없음). 새 연산자가 필요하면 이 파일과 테스트를 고쳐야 한다.
값 영역: True / False / None(정보 부족) / ReviewNeeded(해석 미확정).
"""

import dataclasses
import json
import operator
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from rule_engine import (
    HouseholdProfile, LayerRuleSet, NoticeRuleSet, RuleCondition, ReviewNeeded,
    REVIEW_AMBIGUOUS_SOURCE, resolve_interpretations, years_before, bonus_child_count,
)

RULES_DIR = Path(__file__).resolve().parent.parent / "rules"
LAYERS = ("대학생", "청년", "신혼부부", "한부모")
REVIEW_STATUSES = ("DRAFT", "REVIEWED", "PUBLISHED", "RETIRED")
CTX_KEYS = ("announcement_date",)


class RuleDataError(ValueError):
    """규칙 데이터 파일의 구조·참조 오류(로드 시점에 발생시켜 런타임 오판정을 막는다)."""


# ---------------------------------------------------------------------------
# 기준값 표 (reference/)
# ---------------------------------------------------------------------------
class ReferenceTable:
    def __init__(self, doc: Dict[str, Any]):
        self.id = doc["id"]
        self._table = {int(size): {int(r): v for r, v in row.items()}
                       for size, row in doc["table"].items()}
        self._adder = doc.get("per_person_adder_7plus", 0)

    def lookup(self, household_size: int, ratio_pct: int) -> Optional[int]:
        """rule_engine.income_threshold와 같은 규칙: 7인 이상은 6인 기준 + 1인당 가산액."""
        base = self._table.get(min(household_size, 6), {}).get(ratio_pct)
        if base is None:
            return None
        return base + self._adder * (household_size - 6) if household_size > 6 else base


@lru_cache(maxsize=None)
def load_reference(ref_id: str) -> ReferenceTable:
    path = RULES_DIR / "reference" / f"{ref_id}.json"
    if not path.exists():
        raise RuleDataError(f"기준값 표 '{ref_id}'가 없습니다: {path}")
    return ReferenceTable(json.loads(path.read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# 평가 환경과 센티널
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class _Env:
    profile: Any
    ctx: Dict[str, Any]
    terms: Any = None       # 결정표 선택 결과: dict | None(입력 미확인) | _NoRow


@dataclasses.dataclass(frozen=True)
class _NoRow:
    """결정표에 해당 행이 없음 — 비교 연산자가 만나면 ReviewNeeded로 바뀐다."""
    code: str
    detail: str


def _to_review(v):
    return ReviewNeeded(v.code, v.detail) if isinstance(v, _NoRow) else v


def _operands(values):
    """None(정보 부족)이 NoRow(표에 없음)보다 우선한다 — 기존 규칙과 같은 우선순위."""
    if any(v is None for v in values):
        return None, None
    for v in values:
        if isinstance(v, (_NoRow, ReviewNeeded)):
            return None, _to_review(v)
    return values, None


def _combine_any(values):
    if any(v is True for v in values):
        return True
    reviews = [v for v in values if isinstance(v, ReviewNeeded)]
    if reviews:
        return reviews[0]
    return None if any(v is None for v in values) else False


def _combine_all(values):
    if any(v is False for v in values):
        return False
    reviews = [v for v in values if isinstance(v, ReviewNeeded)]
    if reviews:
        return reviews[0]
    return None if any(v is None for v in values) else True


def _resolve_readings(results: Dict[str, Any], detail: str):
    """여러 해석(reading)의 결과를 합친다. 정보 부족 > 표에 없음 > (일치→확정 / 불일치→해석 미확정)."""
    values = list(results.values())
    if len(values) == 1:
        return values[0]
    if any(v is None for v in values):
        return None
    for v in values:
        if isinstance(v, ReviewNeeded):
            return v
    return resolve_interpretations(results, detail)


# ---------------------------------------------------------------------------
# 결정표 (원문 표를 행 단위로 그대로 옮긴 것)
# ---------------------------------------------------------------------------
def _match_spec(spec: Any, value: int) -> bool:
    if spec == "any":
        return True
    if isinstance(spec, int):
        return value == spec
    if isinstance(spec, str) and spec.endswith("+") and spec[:-1].isdigit():
        return value >= int(spec[:-1])
    raise RuleDataError(f"결정표 행 조건 표기가 올바르지 않습니다: {spec!r} (any / 정수 / 'N+' 만 허용)")


class DecisionTable:
    def __init__(self, name: str, doc: Dict[str, Any], compile_input: Callable):
        self.name = name
        self.columns: List[str] = list(doc["columns"])
        self.outputs: List[str] = list(doc["outputs"])
        self.readings: List[str] = list(doc.get("readings") or [""])
        self.rows: List[Dict[str, Any]] = doc["rows"]
        no_row = doc.get("no_row", {})
        self.no_row = _NoRow(no_row.get("code", REVIEW_AMBIGUOUS_SOURCE),
                             no_row.get("detail", "원문 표에 없는 조합"))
        self.inputs = {c: compile_input(doc["inputs"][c], f"tables.{name}.inputs.{c}")
                       for c in self.columns}
        for i, row in enumerate(self.rows):
            for c in self.columns:
                if c not in row["when"]:
                    raise RuleDataError(f"tables.{name}.rows[{i}]에 열 '{c}' 조건이 없습니다")
                _match_spec(row["when"][c], 0)
            if len(row["out"]) != len(self.outputs):
                raise RuleDataError(f"tables.{name}.rows[{i}].out 길이가 outputs와 다릅니다")
            for r in row.get("readings", []):
                if r not in self.readings:
                    raise RuleDataError(f"tables.{name}.rows[{i}]가 선언되지 않은 reading '{r}'를 씁니다")

    def select(self, env: _Env, reading: str):
        values = {c: self.inputs[c](env) for c in self.columns}
        if any(v is None for v in values.values()):
            return None
        for row in self.rows:
            if row.get("readings") and reading not in row["readings"]:
                continue
            if all(_match_spec(row["when"][c], values[c]) for c in self.columns):
                return dict(zip(self.outputs, row["out"]))
        return self.no_row


# ---------------------------------------------------------------------------
# 조건식 컴파일러
# ---------------------------------------------------------------------------
_PROFILE_FIELDS = {f.name for f in dataclasses.fields(HouseholdProfile)}


def _fn_child_bonus_count(env: _Env):
    p, ann = env.profile, env.ctx["announcement_date"]
    if p.children_birth_dates is not None:
        return bonus_child_count(p.children_birth_dates, ann)
    return p.young_child_count


def _fn_years_before(env: _Env, d, n):
    return None if d is None or isinstance(d, _NoRow) else years_before(d, n)


# 허용 목록(whitelist) 함수: 이름 → (구현, 인자 개수). 데이터는 이 목록 밖의 함수를 부를 수 없다.
FUNCTIONS = {
    "child_bonus_count": (_fn_child_bonus_count, 0),
    "years_before": (_fn_years_before, 2),
}


class _Compiler:
    def __init__(self, table_outputs: Optional[List[str]] = None):
        self.table_outputs = table_outputs  # 이 조건이 쓰는 결정표의 출력 이름(term 검증용)

    def compile(self, node: Any, path: str) -> Callable[[_Env], Any]:
        if not isinstance(node, dict):
            return lambda env, v=node: v           # 상수(숫자·문자열·불리언·null·목록)
        builders = {
            "var": self._var, "ctx": self._ctx, "date": self._date, "fn": self._fn,
            "lookup": self._lookup, "term": self._term,
            "eq": self._cmp, "ne": self._cmp, "lte": self._cmp, "gte": self._cmp,
            "in": self._in, "between": self._between, "all": self._logic, "any": self._logic,
        }
        companions = {"var": {"unknown_values"}, "fn": {"args"}}
        ops = [k for k in node if k in builders]
        if len(ops) != 1:
            raise RuleDataError(
                f"{path}: 연산자는 정확히 하나여야 합니다(허용: {sorted(builders)}): {sorted(node)}")
        op = ops[0]
        extra = set(node) - {op, "review_if_true"} - companions.get(op, set())
        if extra:
            raise RuleDataError(f"{path}: '{op}'에 허용되지 않는 키 {sorted(extra)}")
        fn = builders[op](op, node, path)
        if "review_if_true" in node:
            spec = node["review_if_true"]
            inner = fn
            code, detail = spec["code"], spec["detail"]
            def fn(env, inner=inner, code=code, detail=detail):
                value = inner(env)
                return ReviewNeeded(code, detail) if value is True else value
        return fn

    # --- 값 ---
    def _var(self, op, node, path):
        name = node["var"]
        if name not in _PROFILE_FIELDS:
            raise RuleDataError(f"{path}: 프로필에 없는 변수 '{name}'")
        unknown = list(node.get("unknown_values", []))
        def f(env):
            v = getattr(env.profile, name)
            return None if unknown and v in unknown else v
        return f

    def _ctx(self, op, node, path):
        key = node["ctx"]
        if key not in CTX_KEYS:
            raise RuleDataError(f"{path}: 알 수 없는 컨텍스트 '{key}' (허용: {CTX_KEYS})")
        return lambda env: env.ctx[key]

    def _date(self, op, node, path):
        try:
            d = date.fromisoformat(node["date"])
        except (TypeError, ValueError):
            raise RuleDataError(f"{path}: 날짜 형식이 올바르지 않습니다: {node['date']!r}")
        return lambda env: d

    def _fn(self, op, node, path):
        name = node["fn"]
        if name not in FUNCTIONS:
            raise RuleDataError(f"{path}: 허용 목록에 없는 함수 '{name}' (허용: {sorted(FUNCTIONS)})")
        impl, arity = FUNCTIONS[name]
        args = [self.compile(a, f"{path}.args[{i}]") for i, a in enumerate(node.get("args", []))]
        if len(args) != arity:
            raise RuleDataError(f"{path}: 함수 '{name}'은 인자 {arity}개가 필요합니다")
        return lambda env: impl(env, *[a(env) for a in args])

    def _lookup(self, op, node, path):
        ref_id, size_node, ratio_node = node["lookup"]
        ref = load_reference(ref_id)
        size, ratio = self.compile(size_node, path + ".size"), self.compile(ratio_node, path + ".ratio")
        def f(env):
            vals, review = _operands([size(env), ratio(env)])
            if vals is None:
                return review if review is not None else None
            return ref.lookup(vals[0], vals[1])
        return f

    def _term(self, op, node, path):
        name = node["term"]
        if self.table_outputs is None or name not in self.table_outputs:
            raise RuleDataError(f"{path}: term '{name}'은 조건이 쓰는 결정표의 출력이 아닙니다")
        def f(env):
            if env.terms is None or isinstance(env.terms, _NoRow):
                return env.terms
            return env.terms[name]
        return f

    # --- 비교/결합 ---
    def _cmp(self, op, node, path):
        fn = {"eq": operator.eq, "ne": operator.ne, "lte": operator.le, "gte": operator.ge}[op]
        a_node, b_node = node[op]
        a, b = self.compile(a_node, path + ".0"), self.compile(b_node, path + ".1")
        def f(env):
            vals, review = _operands([a(env), b(env)])
            return review if vals is None and review is not None else (
                None if vals is None else fn(vals[0], vals[1]))
        return f

    def _in(self, op, node, path):
        a_node, options = node["in"]
        a = self.compile(a_node, path + ".0")
        def f(env):
            vals, review = _operands([a(env)])
            return review if vals is None and review is not None else (
                None if vals is None else vals[0] in options)
        return f

    def _between(self, op, node, path):
        a_node, lo, hi = node["between"]
        a = self.compile(a_node, path + ".0")
        def f(env):
            vals, review = _operands([a(env)])
            return review if vals is None and review is not None else (
                None if vals is None else lo <= vals[0] <= hi)
        return f

    def _logic(self, op, node, path):
        children = [self.compile(c, f"{path}.{op}[{i}]") for i, c in enumerate(node[op])]
        combine = _combine_all if op == "all" else _combine_any
        return lambda env: combine([_to_review(c(env)) for c in children])


# ---------------------------------------------------------------------------
# 공고 파일 로드
# ---------------------------------------------------------------------------
def _source_ref(source: Dict[str, Any]) -> str:
    ref = f"공고문 p.{source['page']}"
    return f"{ref} {source['clause']}" if source.get("clause") else ref


def _build_condition(doc: Dict[str, Any], tables: Dict[str, DecisionTable], ann: date,
                     where: str) -> RuleCondition:
    cid = doc.get("id")
    for key in ("id", "field", "required", "source", "note", "check"):
        if key not in doc:
            raise RuleDataError(f"{where}: 조건에 '{key}'가 없습니다 (id={cid})")
    if not isinstance(doc["required"], bool):
        raise RuleDataError(f"{where}/{cid}: required는 true/false여야 합니다")
    if "page" not in doc["source"]:
        raise RuleDataError(f"{where}/{cid}: source.page가 없습니다")

    table: Optional[DecisionTable] = None
    if "table" in doc:
        if doc["table"] not in tables:
            raise RuleDataError(f"{where}/{cid}: 정의되지 않은 결정표 '{doc['table']}'")
        table = tables[doc["table"]]
    check_fn = _Compiler(table.outputs if table else None).compile(doc["check"], f"{where}/{cid}.check")
    ctx = {"announcement_date": ann}
    detail = doc.get("reading_detail", f"{cid} 해석 불일치")

    def check(profile):
        if table is None:
            value = check_fn(_Env(profile, ctx))
        else:
            results = {}
            for reading in table.readings:
                env = _Env(profile, ctx)
                env.terms = table.select(env, reading)
                results[reading] = check_fn(env)
            value = _resolve_readings(results, detail)
        value = _to_review(value)
        if not (value is None or isinstance(value, (bool, ReviewNeeded))):
            raise RuleDataError(f"{where}/{cid}: 조건식 결과가 참/거짓이 아닙니다: {value!r}")
        return value

    return RuleCondition(cid, doc["field"], doc["required"], _source_ref(doc["source"]),
                         check, note=doc["note"])


def build_notice(doc: Dict[str, Any]) -> NoticeRuleSet:
    for key in ("notice_id", "title", "announcement_date", "review", "layers"):
        if key not in doc:
            raise RuleDataError(f"공고 파일에 '{key}'가 없습니다")
    status = doc["review"].get("status")
    if status not in REVIEW_STATUSES:
        raise RuleDataError(f"review.status는 {REVIEW_STATUSES} 중 하나여야 합니다: {status!r}")
    ann = date.fromisoformat(doc["announcement_date"])

    tables: Dict[str, DecisionTable] = {}
    for name, tdoc in doc.get("tables", {}).items():
        base = _Compiler()
        tables[name] = DecisionTable(name, tdoc, lambda n, p, c=base: c.compile(n, p))

    layers: Dict[str, LayerRuleSet] = {}
    seen_ids = set()
    for layer, ldoc in doc["layers"].items():
        if layer not in LAYERS:
            raise RuleDataError(f"알 수 없는 계층 '{layer}' (허용: {LAYERS})")
        conditions = []
        for cdoc in ldoc["conditions"]:
            cond = _build_condition(cdoc, tables, ann, f"{doc['notice_id']}/{layer}")
            if cond.rule_id in seen_ids:
                raise RuleDataError(f"조건 ID 중복: {cond.rule_id}")
            seen_ids.add(cond.rule_id)
            conditions.append(cond)
        layers[layer] = LayerRuleSet(layer, conditions)

    meta = {k: doc[k] for k in ("version", "valid_from", "supersedes", "source", "review") if k in doc}
    return NoticeRuleSet(notice_id=doc["notice_id"], title=doc["title"], announcement_date=ann,
                         layers=layers, meta=meta)


@lru_cache(maxsize=None)
def load_notice(notice_id: str) -> NoticeRuleSet:
    path = RULES_DIR / "notices" / f"{notice_id}.json"
    if not path.exists():
        raise RuleDataError(f"공고 규칙 파일이 없습니다: {path}")
    return build_notice(json.loads(path.read_text(encoding="utf-8")))
