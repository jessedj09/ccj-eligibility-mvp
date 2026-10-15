# -*- coding: utf-8 -*-
"""test_c1_notices.py — C1에서 추가한 LH 행복주택 공고(N4~N8) 검증.

1) 템플릿과의 동등성: N4·N5·N6은 N3, N7·N8은 N1과 자격 규칙이 같다(공고별 분석 docs/notice-analysis/GROUP_1~3).
   공고일에 맞춰 날짜를 옮긴 같은 체계적 입력(골든 S·T 구간)에 대해 판정 기록이 같아야 한다.
2) 기준일: 원문이 날짜를 적어 둔 곳은 그 리터럴을 쓰고, 그 날짜는 LH 관행 공식과 일치한다(공식의 교차 검증).
3) 공고 메타: 기관·사업유형·미지원 계층·유의사항.
"""

import json
import re
from datetime import date

import golden_cases
import golden_lib
import pytest
from rule_data import RULES_DIR, load_notice
from rule_engine import marriage_cutoff, young_child_cutoff

TEMPLATE = {"N4": "N3", "N5": "N3", "N6": "N3", "N7": "N1", "N8": "N1"}
GOLDEN = golden_lib.load_outcomes()["groups"]


def _neutral(record):
    return re.sub(r"N\d+-", "X-", json.dumps(record, ensure_ascii=False))


@pytest.mark.parametrize("nid,layer", [g for g in golden_cases.GROUPS if g[0] in TEMPLATE])
def test_same_verdicts_as_template_for_date_shifted_inputs(nid, layer):
    group, template = GOLDEN[f"{nid}/{layer}"], GOLDEN[f"{TEMPLATE[nid]}/{layer}"]
    n = group["n"] - golden_cases.RANDOM_PER_GROUP       # 무작위 구간은 시드가 달라 비교 대상이 아니다
    mine = [_neutral(r) for r in group["records"][:n]]
    theirs = [_neutral(r) for r in template["records"][:n]]
    diff = [i for i, (a, b) in enumerate(zip(mine, theirs)) if a != b]
    assert not diff, f"{nid}/{layer}: 템플릿과 다른 판정 {len(diff)}건(첫 위치 {diff[:5]})"


def _dates_in(nid, cid_suffix):
    doc = json.loads((RULES_DIR / "notices" / f"{nid}.json").read_text(encoding="utf-8"))
    for layer in doc["layers"].values():
        for c in layer["conditions"]:
            if c["id"].endswith(cid_suffix):
                return re.findall(r'"date": "(\d{4}-\d{2}-\d{2})"', json.dumps(c["check"]))
    return []


# 원문 리터럴(손으로 옮김) — 공고일 기준 LH 공식과 같아야 한다
LITERALS = [
    ("N4", "-M-duration", None, date(2019, 10, 2)),       # p.1 "만6세 이하(2019.10.02. 이후 출생)"
    ("N6", "-M-duration", None, date(2019, 5, 16)),       # p.2 "(2019.05.16.이후 출생)"
    ("N7", "-M-duration", date(2019, 6, 29), date(2019, 6, 30)),   # p.1·p.5
]


@pytest.mark.parametrize("nid,suffix,marriage,child", LITERALS)
def test_literal_cutoffs_are_used_and_match_lh_formula(nid, suffix, marriage, child):
    found = {date.fromisoformat(d) for d in _dates_in(nid, suffix)}
    ann = load_notice(nid).announcement_date
    if marriage:
        assert marriage in found and marriage == marriage_cutoff(ann)
    assert child in found and child == young_child_cutoff(ann)


def test_n8_has_no_literal_and_uses_the_formula_with_derivation():
    doc = json.loads((RULES_DIR / "notices" / "N8.json").read_text(encoding="utf-8"))
    dur = next(c for c in doc["layers"]["신혼부부"]["conditions"] if c["id"] == "N8-M-duration")
    assert "marriage_cutoff" in json.dumps(dur["check"]) and "derivation" in dur["source"]


@pytest.mark.parametrize("nid", list(TEMPLATE))
def test_meta_issuer_program_unsupported_layers_and_notes(nid):
    meta = load_notice(nid).meta
    assert meta["issuer"] == "LH" and meta["program"].startswith("행복주택")
    assert meta["unsupported_layers"] and all(u["note"] for u in meta["unsupported_layers"])
    assert meta["notes"]
    assert not set(u["name"] for u in meta["unsupported_layers"]) & set(load_notice(nid).layers)
