# -*- coding: utf-8 -*-
"""draft.py — 미등록 공고의 '검증 전 초안' 판정(P2 준비, docs/09 §17). 화면이 부르는 단일 입구.

    d = make_draft(pdf_bytes)              # 업로드한 공고문 → 초안(규칙) 또는 판정할 수 없는 이유
    verdict, notes = judge(d, profile, layer)
    result, notes = evaluate_draft(d, profile, layer)   # 화면용 — 낮춘 판정을 담은 엔진 결과(근거 표시에 그대로 쓴다)

- **합격한 사업만**(PASSING — P1 평가에서 안전 0건·자동 채움 ≥90%·결정론만으로 시험용 판정 100% 같음). AI를 쓰지 않는다.
- 추출·검증은 tools/(sheet_extract·templates — 생성 스크립트 재사용)를 그대로 쓴다. 형제 공고 = 같은 템플릿의 등록 공고 전부.
- 보류된 조건(인용문을 원문에서 못 찾음, 기준표 연도 다름)이 판정에 쓰이거나 템플릿에 없는 제한 문구가 있으면 '지원 가능'을
  '수동 확인'으로 낮춘다. 핵심 빈칸이 보류면 판정하지 않는다.
- 업로드 파일은 디스크에 남기지 않는다(규칙 생성에 필요한 임시 파일은 바로 지움).
- 등록 도구(tools/notice_intake.py --draft)는 `only=None`으로 모든 사업의 초안을 만든다 — 추출 내역(fields)·시트(sheet)·
  찾지 못한 인용문(missing)을 등록 작업의 출발점으로 쓴다(판정에는 쓰지 않음).
"""
import dataclasses
import os
import re
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
DRAFT_ID = "DRAFT"
NOTE = "검증 전 초안 — 자동으로 읽은 공고입니다. 신청 전 원문을 확인하세요."


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
    fields: Dict = field(default_factory=dict)              # 추출 내역(공고일 + 빈칸별 status·value·page·quote·how)
    sheet: Optional[Dict] = None                            # 파라미터 시트 초안(보류 빈칸은 자리표시 값)
    missing: List[str] = field(default_factory=list)        # 원문에서 찾지 못한 인용문(기준표 연도 포함) — 그 조건은 보류
    doc: Optional[Dict] = None                              # 초안 규칙 문서(JSON) — 만들 수 있었을 때


FIELD_KEYS = {"status", "value", "page", "quote", "how"}


def field_rows(fields: Dict, prefix: str = "") -> List[Tuple[str, Dict]]:
    """추출 내역(중첩 dict)을 (빈칸 경로, 내역) 목록으로 편다 — 예: ("dates.marriage", {status, value, page, …})."""
    out = []
    for k, v in fields.items():
        if isinstance(v, dict) and set(v) == FIELD_KEYS:
            out.append((prefix + k, v))
        elif isinstance(v, dict):
            out += field_rows(v, prefix + k + ".")
    return out


def _siblings(template):
    return [T.gold_sheet(n) for n in T.sheet_ids() if T.gold_sheet(n)["template"] == template]


def make_draft(data: bytes, only=PASSING, pages: Optional[List[str]] = None) -> Draft:
    """only: 초안을 만들 템플릿(None = 전부 — 등록 도구용). pages: 이미 읽은 쪽 텍스트(없으면 data에서 읽는다)."""
    if pages is None:
        try:
            pages = sv.extract_pages_bytes(data, label="<초안>", cache=False)
        except ValueError as e:
            return Draft(UNREADABLE, str(e))
    if not any(p.strip() for p in pages):
        return Draft(UNREADABLE, "글자를 읽을 수 없는 PDF입니다(스캔 이미지일 수 있음).")
    ext = X.extract(pages, _siblings)
    ann = ext["announcement_date"].value if ext["announcement_date"].status == X.FILLED else None
    rep = X.field_report(ext)
    base = dict(template=ext["template"], program=ext["program"], announcement_date=ann,
                fields={"announcement_date": rep["announcement_date"], **rep["fields"]})
    if not ext["template"] or (only is not None and ext["template"] not in only):
        why = "사업 유형을 알아보지 못했습니다." if not ext["template"] else \
            f"이 사업({ext['program']})은 아직 자동 초안 판정 대상이 아닙니다(정확도 기준 미달 또는 시험 전)."
        return Draft(UNSUPPORTED, why, **base)
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        g = X.gate(ext, Path(tmp), pages, DRAFT_ID)
    finally:
        os.remove(tmp)
    base.update(held_fields=g["held"], missing=g["missing"], stale=g["stale"], restrictions=g["restrictions"],
                sheet=X.to_sheet(ext, DRAFT_ID), doc=g["doc"])
    if g["blocked"] or g["critical_held"]:
        reason = g["blocked"] or "판정에 꼭 필요한 값을 원문에서 확인하지 못했습니다: " + ", ".join(g["critical_held"])
        return Draft(BLOCKED, reason, **base)
    base["doc"] = dict(g["doc"], title=f"{ext['program']} (검증 전 초안)")
    notice = build_notice(base["doc"])
    ids = set(re.findall(rf"({DRAFT_ID}-[A-Za-z0-9가-힣-]+)", " ".join(g["missing"])))
    held = {layer: X.affected_conditions(ls.conditions, ids) for layer, ls in notice.layers.items()}
    return Draft(OK, "", notice=notice, held_conditions=held, **base)


def evaluate_draft(d: Draft, profile, layer: str):
    """초안 규칙으로 판정 → (엔진 결과, 안내). 판정은 엔진 그대로, 보류 대상·새 제한 문구가 있으면 '지원 가능'을 낮춘
    결과(verdict만 바꾼 복사본)를 돌려준다 — 화면은 이 결과로 근거를 그대로 그린다."""
    if d.status != OK:
        raise ValueError("판정할 수 있는 초안이 아닙니다")
    r = evaluate(profile, d.notice, layer)
    affected = d.held_conditions.get(layer, set())
    v = X.adjust_verdict(r, affected, bool(d.restrictions))
    notes = [NOTE]
    if v != r.verdict:
        if affected:
            notes.append("원문에서 확인하지 못한 조건이 판정에 쓰여 '수동 확인'으로 표시했습니다.")
        if d.restrictions:
            notes.append("규칙에 없는 지역·모집 제한 문구가 있습니다: " + d.restrictions[0][1][:40])
    return dataclasses.replace(r, verdict=v), notes


def judge(d: Draft, profile, layer: str) -> Tuple[str, List[str]]:
    """초안 규칙으로 판정 → (판정, 안내)."""
    r, notes = evaluate_draft(d, profile, layer)
    return r.verdict, notes
