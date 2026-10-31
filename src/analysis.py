# -*- coding: utf-8 -*-
"""analysis.py — 업로드한 미등록 공고의 자동 분석 + 공유 저장소(v3 ④). 화면·API가 부르는 입구.

    d = analyze(pdf_bytes, ident)     # 같은 원문·같은 엔진으로 분석한 결과가 저장소에 있으면 그것, 없으면 분석해 저장

- 저장소가 없거나 멈춰도 결과는 같다(그때마다 분석할 뿐) — 판정 경로가 DB에 기대지 않는다.
- 엔진 판(analysis_version): 분석에 쓰는 코드 파일과 형제 공고(정답 시트)의 해시. 코드나 등록 공고가 바뀌면 판이 바뀌어
  예전 분석을 쓰지 않는다(손으로 올리는 버전 번호 없음).
- 후속 작업: 결정론이 못 채운 값이 있으면 enhance(PC 작업기가 로컬 LLM으로 보강), 규칙이 모르는 문장·대상 아닌 LH·SH 사업이면
  review(운영자). 작업을 넣을 때만 PDF를 잠시 둔다 — **LH·SH 공고로 식별된 것만**(개인 문서 보관 방지).
"""
import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

import draft
import grading
from store import get_store

ROOT = Path(__file__).resolve().parent.parent
CODE = ("src/draft.py", "src/grading.py", "src/rule_data.py", "tools/sheet_extract.py", "tools/templates.py",
        "tools/clause_ledger.py")
KEEP_PDF = ("LH", "SH")


@lru_cache(maxsize=1)
def analysis_version() -> str:
    import templates as T
    h = hashlib.sha256()
    for f in CODE:
        h.update((ROOT / f).read_bytes().replace(b"\r\n", b"\n"))
    h.update(json.dumps([T.gold_sheet(n) for n in sorted(T.sheet_ids())], ensure_ascii=False, sort_keys=True,
                        default=str).encode("utf-8"))
    return "v3-" + h.hexdigest()[:12]


def overall_grade(d: draft.Draft) -> Optional[str]:
    """공고 전체 등급 — 모든 계층이 자동 확정이면 auto, 하나라도 일부 확인이면 partial. 판정할 수 없는 초안이면 None."""
    if d.status != draft.OK:
        return None
    gs = grading.grades(d)
    return grading.AUTO if gs and all(g.grade == grading.AUTO for g in gs.values()) else grading.PARTIAL


def follow_up(d: draft.Draft, issuer: Optional[str]) -> Optional[Tuple[str, int]]:
    """(작업 종류, 우선순위) 또는 None. 우선순위가 클수록 먼저."""
    if issuer not in KEEP_PDF:
        return None
    if d.status == draft.BLOCKED or (d.status == draft.OK and (d.missing or d.held_fields)):
        return "enhance", 10 if d.status == draft.BLOCKED else 5
    if d.status == draft.OK and overall_grade(d) == grading.PARTIAL:
        return "review", 3                 # 미분류 문장·새 제한 문구 — LLM으로 풀 수 없고 운영자가 분류
    if d.status == draft.UNSUPPORTED and d.program:
        return "review", 1                 # 아직 대상이 아닌 사업의 공고 — 사업 확장 후보
    return None


def analyze(data: bytes, ident=None, store=None) -> draft.Draft:
    store = store or get_store()
    sha = hashlib.sha256(data).hexdigest()
    version = analysis_version()
    snap = store.latest_analysis(sha, version)
    if snap is not None:
        try:
            return draft.from_snapshot(snap)
        except (KeyError, ValueError, TypeError):
            pass                            # 형식이 맞지 않는 저장본은 무시하고 다시 분석
    d = draft.make_draft(data)
    issuer = getattr(ident, "issuer", None)
    store.save_notice(sha, issuer=issuer, program=d.program or getattr(ident, "program", None),
                      announcement_date=d.announcement_date or getattr(ident, "announcement", None))
    store.save_analysis(sha, version, draft.to_snapshot(d, sha, created=datetime.now(timezone.utc).isoformat()),
                        overall_grade(d))
    job = follow_up(d, issuer)
    if job and store.put_pdf(sha, data):
        store.enqueue(sha, *job)
    return d
