# -*- coding: utf-8 -*-
"""draft.py — 미등록 공고의 '검증 전 초안' 판정(P2 준비, docs/09 §17). 화면이 부르는 단일 입구.

    d = make_draft(pdf_bytes)              # 업로드한 공고문 → 초안(규칙) 또는 판정할 수 없는 이유
    verdict, notes = judge(d, profile, layer)

- **합격한 사업만**(PASSING — P1 평가에서 안전 0건·자동 채움 ≥90%·결정론만으로 시험용 판정 100% 같음). AI를 쓰지 않는다.
- 추출·검증은 tools/(sheet_extract·templates — 생성 스크립트 재사용)를 그대로 쓴다. 형제 공고 = 같은 템플릿의 등록 공고 전부.
- 보류된 조건(인용문을 원문에서 못 찾음, 기준표 연도 다름)이 판정에 쓰이거나 템플릿에 없는 제한 문구가 있으면 '지원 가능'을
  '수동 확인'으로 낮춘다. 핵심 빈칸이 보류면 판정하지 않는다.
- 업로드 파일은 디스크에 남기지 않는다(규칙 생성에 필요한 임시 파일은 바로 지움).
"""
import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_TOOLS = str(Path(__file__).resolve().parent.parent / "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

import sheet_extract as X  # noqa: E402
import source_verify as sv  # noqa: E402
import templates as T  # noqa: E402
from rule_data import build_notice  # noqa: E402
from rule_engine import evaluate  # noqa: E402

PASSING = ("lh.youth_rental", "lh.newlywed_rental", "lh.deundeun", "sh.jeonse", "sh.jeonse2")
OK, UNSUPPORTED, BLOCKED, UNREADABLE = "ok", "unsupported", "blocked", "unreadable"


@dataclass
class Draft:
    status: str
    reason: str = ""
    template: Optional[str] = None
    program: Optional[str] = None
    announcement_date: Optional[str] = None
    notice: object = None                                  # NoticeRuleSet(초안) — status == ok일 때
    held_conditions: Dict[str, set] = field(default_factory=dict)   # 계층 → 보류 대상 최상위 조건 ID
    stale: List[str] = field(default_factory=list)          # 기준표 연도가 다른 조건
    restrictions: List[tuple] = field(default_factory=list)  # 템플릿에 없는 제한 문구 (쪽, 문구)
    held_fields: List[str] = field(default_factory=list)


def _siblings(template):
    return [T.gold_sheet(n) for n in T.sheet_ids() if T.gold_sheet(n)["template"] == template]


def make_draft(data: bytes) -> Draft:
    try:
        pages = sv.extract_pages_bytes(data, label="<초안>", cache=False)
    except ValueError as e:
        return Draft(UNREADABLE, str(e))
    if not any(p.strip() for p in pages):
        return Draft(UNREADABLE, "글자를 읽을 수 없는 PDF입니다(스캔 이미지일 수 있음).")
    ext = X.extract(pages, _siblings)
    ann = ext["announcement_date"].value if ext["announcement_date"].status == X.FILLED else None
    base = dict(template=ext["template"], program=ext["program"], announcement_date=ann)
    if ext["template"] not in PASSING:
        why = "사업 유형을 알아보지 못했습니다." if not ext["template"] else \
            f"이 사업({ext['program']})은 아직 자동 초안 판정 대상이 아닙니다(정확도 기준 미달 또는 시험 전)."
        return Draft(UNSUPPORTED, why, **base)
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        g = X.gate(ext, Path(tmp), pages, "DRAFT")
    finally:
        os.remove(tmp)
    if g["blocked"] or g["critical_held"]:
        reason = g["blocked"] or "판정에 꼭 필요한 값을 원문에서 확인하지 못했습니다: " + ", ".join(g["critical_held"])
        return Draft(BLOCKED, reason, held_fields=g["held"], **base)
    notice = build_notice(g["doc"])
    import re
    ids = set(re.findall(r"(DRAFT-[A-Za-z0-9가-힣-]+)", " ".join(g["missing"])))
    held = {layer: X.affected_conditions(ls.conditions, ids) for layer, ls in notice.layers.items()}
    return Draft(OK, "", notice=notice, held_conditions=held, stale=g["stale"], restrictions=g["restrictions"],
                 held_fields=g["held"], **base)


def judge(d: Draft, profile, layer: str) -> Tuple[str, List[str]]:
    """초안 규칙으로 판정 → (판정, 안내). 판정은 엔진 그대로, 보류 대상·새 제한 문구가 있으면 '지원 가능'을 낮춘다."""
    if d.status != OK:
        raise ValueError("판정할 수 있는 초안이 아닙니다")
    r = evaluate(profile, d.notice, layer)
    affected = d.held_conditions.get(layer, set())
    v = X.adjust_verdict(r, affected, bool(d.restrictions))
    notes = ["검증 전 초안 — 자동으로 읽은 공고입니다. 신청 전 원문을 확인하세요."]
    if v != r.verdict:
        if affected:
            notes.append("원문에서 확인하지 못한 조건이 판정에 쓰여 '수동 확인'으로 표시했습니다.")
        if d.restrictions:
            notes.append("규칙에 없는 지역·모집 제한 문구가 있습니다: " + d.restrictions[0][1][:40])
    return v, notes
