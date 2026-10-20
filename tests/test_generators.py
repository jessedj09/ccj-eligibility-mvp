# -*- coding: utf-8 -*-
"""test_generators.py — 공고 생성 스크립트를 다시 돌려도 커밋된 규칙 파일이 바뀌지 않는지(재실행 안전성).

tools/gen_c1_notices.py는 템플릿 계층만 소유한다. 다른 단계(C3 tools/gen_c3_layers.py)가 추가한 계층·결정표·
미지원 항목을 지우면 안 된다 — 실제로 2026-10-20 점검에서 재실행 시 N6의 고령자·산업단지근로자가 사라지는 것을 재현했다.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEN_C1 = _load("gen_c1_notices")


@pytest.mark.parametrize("target", GEN_C1.TARGETS, ids=[t["nid"] for t in GEN_C1.TARGETS])
def test_rerunning_c1_generator_reproduces_committed_file(target):
    path = ROOT / "rules" / "notices" / f"{target['nid']}.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    doc, missing = GEN_C1.build(target)
    assert not missing
    regenerated = GEN_C1.preserve_later_additions(doc, json.loads(path.read_text(encoding="utf-8")))
    assert regenerated == committed, f"{target['nid']}: 재생성 결과가 커밋된 파일과 다름(다른 단계의 작업이 지워졌을 수 있음)"
