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


def test_rerunning_c5_jeonse_generator_reproduces_committed_files(tmp_path, monkeypatch):
    """C5b(SH 장기전세·장기전세2)는 공고 파일 전체를 만든다 — 다시 돌린 결과가 커밋 파일과 같아야 한다."""
    gen = _load("gen_c5_jeonse")
    (tmp_path / "rules" / "notices").mkdir(parents=True)
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    gen.main()
    for plan in gen.PLAN:
        nid = plan["nid"]
        assert json.loads((tmp_path / "rules" / "notices" / f"{nid}.json").read_text(encoding="utf-8")) == \
            json.loads((ROOT / "rules" / "notices" / f"{nid}.json").read_text(encoding="utf-8")), nid


def test_rerunning_c5_generator_keeps_committed_files(tmp_path, monkeypatch):
    """C5(주거약자용 변형 계층)는 기존 파일을 읽어 변형 계층만 다시 만든다 — 결과가 커밋 파일과 같아야 한다."""
    import shutil
    gen = _load("gen_c5_housing_weak")
    src = ROOT / "rules" / "notices"
    work = tmp_path / "rules" / "notices"
    work.mkdir(parents=True)
    for nid in gen.PLAN:
        shutil.copy(src / f"{nid}.json", work / f"{nid}.json")
    monkeypatch.setattr(gen, "ROOT", tmp_path)
    gen.main()
    for nid in gen.PLAN:
        assert json.loads((work / f"{nid}.json").read_text(encoding="utf-8")) == \
            json.loads((src / f"{nid}.json").read_text(encoding="utf-8")), nid


@pytest.mark.parametrize("target", GEN_C1.TARGETS, ids=[t["nid"] for t in GEN_C1.TARGETS])
def test_rerunning_c1_generator_reproduces_committed_file(target):
    path = ROOT / "rules" / "notices" / f"{target['nid']}.json"
    committed = json.loads(path.read_text(encoding="utf-8"))
    doc, missing = GEN_C1.build(target)
    assert not missing
    regenerated = GEN_C1.preserve_later_additions(doc, json.loads(path.read_text(encoding="utf-8")))
    assert regenerated == committed, f"{target['nid']}: 재생성 결과가 커밋된 파일과 다름(다른 단계의 작업이 지워졌을 수 있음)"
