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
UPLOAD_NAME = "upload.pdf"
NOTE = "검증 전 초안 — 자동으로 읽은 공고입니다. 신청 전 원문을 확인하세요."


def passing_programs() -> List[str]:
    """자동 판정하는 사업(PASSING 템플릿)의 화면 이름 — 판정할 수 없는 공고를 올린 사용자에게 무엇을 지원하는지 알린다."""
    out = []
    for t in PASSING:
        d = T.TEMPLATES[t]
        out.append(d["program"] if d["program"].startswith(d["issuer"]) else f"{d['issuer']} {d['program']}")
    return out


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
    unclassified: List[tuple] = field(default_factory=list)  # 조항 장부의 미분류 문장 (쪽, 문장) — 규칙이 모르는 조건일 수 있음(v3 ②)


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


def _siblings_except(exclude: str = ""):
    def f(template):
        return [T.gold_sheet(n) for n in T.sheet_ids() if n != exclude and T.gold_sheet(n)["template"] == template]
    return f


_siblings = _siblings_except()


def make_draft(data: bytes, only=PASSING, pages: Optional[List[str]] = None, exclude: str = "", slot=None) -> Draft:
    """only: 초안을 만들 템플릿(None = 전부 — 등록 도구용). pages: 이미 읽은 쪽 텍스트(없으면 data에서 읽는다).
    exclude: 형제에서 뺄 등록 공고(평가 — 등록 공고를 '처음 보는 공고'처럼 만들 때. 실제 사용에서는 비움).
    slot: LLM 슬롯(tools/llm_slot.py) — PC 보강 작업기(tools/worker.py)만 넘긴다. 결정론이 못 채운 빈칸만 묻고, 낸 값은 같은
    검증(원문 대조·주제 일치)을 통과해야 쓴다. 화면·API는 넘기지 않는다(판정 경로에 LLM 없음)."""
    if pages is None:
        try:
            pages = sv.extract_pages_bytes(data, label="<초안>", cache=False)
        except ValueError as e:
            return Draft(UNREADABLE, str(e))
    if not any(p.strip() for p in pages):
        return Draft(UNREADABLE, "글자를 읽을 수 없는 PDF입니다(스캔 이미지일 수 있음).")
    llm = X.LLM(slot, _raw_pages(data)) if slot is not None else None
    ext = X.extract(pages, _siblings_except(exclude), llm)
    ann = ext["announcement_date"].value if ext["announcement_date"].status == X.FILLED else None
    rep = X.field_report(ext)
    base = dict(template=ext["template"], program=ext["program"], announcement_date=ann,
                fields={"announcement_date": rep["announcement_date"], **rep["fields"]})
    if not ext["template"] or (only is not None and ext["template"] not in only):
        why = "공고문에서 사업 유형을 알아보지 못했습니다." if not ext["template"] else \
            f"이 사업({ext['program']})은 아직 자동 판정을 지원하지 않습니다(정확도를 검증하며 차례로 추가합니다)."
        return Draft(UNSUPPORTED, why, **base)
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        g = X.gate(ext, Path(tmp), pages, DRAFT_ID, llm)
        if g["doc"]:
            g["doc"]["source"]["document"] = UPLOAD_NAME   # 임시 파일 이름 대신 — 같은 원문이면 같은 초안(저장·비교)
        unclassified = _unclassified(Path(tmp), g["doc"], ext["template"], exclude) if g["doc"] else []
    finally:
        os.remove(tmp)
    base.update(held_fields=g["held"], missing=g["missing"], stale=g["stale"], restrictions=g["restrictions"],
                sheet=X.to_sheet(ext, DRAFT_ID), doc=g["doc"], unclassified=unclassified)
    if g["blocked"] or g["critical_held"]:
        reason = g["blocked"] or "판정에 꼭 필요한 값을 원문에서 확인하지 못했습니다: " + ", ".join(g["critical_held"])
        return Draft(BLOCKED, reason, **base)
    base["doc"] = dict(g["doc"], title=f"{ext['program']} (검증 전 초안)")
    notice = build_notice(base["doc"])
    ids = set(re.findall(rf"({DRAFT_ID}-[A-Za-z0-9가-힣-]+)", " ".join(g["missing"])))
    held = {layer: X.affected_conditions(ls.conditions, ids) for layer, ls in notice.layers.items()}
    return Draft(OK, "", notice=notice, held_conditions=held, **base)


def _raw_pages(data: bytes) -> List[str]:
    """LLM에게 보여 줄 쪽 텍스트(띄어쓰기 유지)."""
    import llm_slot as L
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return L.raw_pages(tmp)
    finally:
        os.remove(tmp)


def _unclassified(pdf: Path, doc: Dict, template: Optional[str], exclude: str = "") -> List[tuple]:
    """조항 장부(v3 ②): 규칙 근거·형제 공고·무관 범주 어디에도 없는 조건형 문장 (쪽, 문장)."""
    import clause_ledger as CL
    rows = CL.ledger_for_draft(pdf, doc, CL.template_siblings(template, exclude))
    return [(p, u) for p, u, label in rows if label == CL.UNCLASSIFIED]


def evaluate_draft(d: Draft, profile, layer: str):
    """초안 규칙으로 판정 → (엔진 결과, 안내). 판정은 엔진 그대로, 그 사용자의 결론이 확실하지 않은 값·문장에 따라 갈리면
    '수동 확인'으로 낮춘 결과(verdict만 바꾼 복사본)와 원문에서 확인할 곳(grading.judge)."""
    import grading
    r, checks = grading.judge(d, profile, layer)
    return r, [NOTE] + [c.text for c in checks]


def judge(d: Draft, profile, layer: str) -> Tuple[str, List[str]]:
    """초안 규칙으로 판정 → (판정, 안내)."""
    r, notes = evaluate_draft(d, profile, layer)
    return r.verdict, notes


# ------------------------------------------------------------------ 초안 스냅샷(B2 — 등록 전에 얼려 두고 등록 후 판정과 비교)
SNAPSHOT_FORMAT = "draft-snapshot/1"


def to_snapshot(d: Draft, sha256: str, source: str = "", created: str = "") -> Dict:
    """초안을 파일로 얼린다 — 규칙 문서와 함께 판정을 낮추는 데 쓰는 보류 조건·제한 문구까지(evaluate_draft를 그대로 재현).
    판정할 수 없는 초안도 이유와 함께 남긴다(그 공고는 '초안 판정 없음'으로 비교된다)."""
    return {"format": SNAPSHOT_FORMAT, "sha256": sha256, "file": source, "created": created,
            "status": d.status, "reason": d.reason, "template": d.template, "program": d.program,
            "announcement_date": d.announcement_date, "held_fields": d.held_fields,
            "held_conditions": {layer: sorted(ids) for layer, ids in d.held_conditions.items()},
            "restrictions": [list(r) for r in d.restrictions], "stale": d.stale, "missing": d.missing, "doc": d.doc,
            "unclassified": [list(u) for u in d.unclassified]}


def from_snapshot(s: Dict) -> Draft:
    if s.get("format") != SNAPSHOT_FORMAT:
        raise ValueError(f"초안 스냅샷 형식이 아닙니다(format={s.get('format')!r})")
    return Draft(s["status"], s["reason"], template=s["template"], program=s["program"],
                 announcement_date=s["announcement_date"],
                 notice=build_notice(s["doc"]) if s["status"] == OK else None,
                 held_conditions={layer: set(ids) for layer, ids in s["held_conditions"].items()},
                 stale=s["stale"], restrictions=[tuple(r) for r in s["restrictions"]], held_fields=s["held_fields"],
                 missing=s["missing"], doc=s["doc"], unclassified=[tuple(u) for u in s.get("unclassified", [])])
