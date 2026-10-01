# -*- coding: utf-8 -*-
"""golden_lib.py — 골든 스냅샷 생성·비교 공용 코드 (tests/test_rules_golden.py, tools/regen_golden.py)."""

import gzip
import json
from pathlib import Path
from typing import Any, Dict, List

import golden_cases
from rule_engine import evaluate

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
OUTCOMES = GOLDEN_DIR / "outcomes.json.gz"
CONDITIONS = GOLDEN_DIR / "conditions.json"


def record(result) -> List[Any]:
    return [result.verdict, result.score, list(result.matched), list(result.failed),
            list(result.unknown), list(result.review), list(result.notes),
            {k: [v.code, v.detail] for k, v in result.review_reasons.items()}]


def build_outcomes(notices: Dict[str, Any]) -> Dict[str, Any]:
    groups: Dict[str, Dict[str, Any]] = {}
    for nid, layer, profile in golden_cases.cases():
        g = groups.setdefault(f"{nid}/{layer}", {"records": []})
        g["records"].append(record(evaluate(profile, notices[nid], layer)))
    for g in groups.values():
        g["n"] = len(g["records"])
    return {"version": 1, "groups": groups}


def build_conditions(notices: Dict[str, Any]) -> Dict[str, Any]:
    return {f"{nid}/{layer}": [
        {"id": c.rule_id, "field": c.field, "required": c.required, "source_ref": c.source_ref,
         "note": c.note, "timing": c.timing} for c in notices[nid].layers[layer].conditions]
        for nid, layer in golden_cases.GROUPS}


def write(outcomes: Dict[str, Any], conditions: Dict[str, Any]) -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    with gzip.open(OUTCOMES, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(outcomes, f, ensure_ascii=False, separators=(",", ":"))
    CONDITIONS.write_text(json.dumps(conditions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def load_outcomes() -> Dict[str, Any]:
    with gzip.open(OUTCOMES, "rt", encoding="utf-8") as f:
        return json.load(f)
