# -*- coding: utf-8 -*-
"""사업(판정 틀)별 검증 상태 — R-⑤(2026-11-14 사용자 결정, 점검 세션 docs/13 2-4).

공개 원칙은 'A안 + 규칙 기반 파이프라인 + 검증 상태 표시': 판정 틀이 있으면 판정하고, 그 판정 방식이 얼마나 검증됐는지를
결과의 '이 판정이 확인한 것' 칸과 이용 안내에 **표시만** 한다(판정은 막지 않는다 — 멈춤은 이미 있는 program_health 장치).

- 독립 검증 완료(verified): 그 사업의 워크시트 사례(`docs/independent-validation-cases.json` — 입력만)에 사람이 원문만 보고 낸 답
  (`docs/independent-validation-answers.json` — {"answers": {"<id>": {"verdict", "page", "note"}}}, 점검 세션 tools/four_class.py와 같은
  형식)이 모두 있고 엔진과 불일치 0이며, 대조를 마쳤다고 `docs/independent-validation-status.json`에 기록한 사업. 기록 뒤에 규칙이 바뀌어
  불일치가 생기면 CI 시험(tests/test_verification.py)이 깨진다 — 기록이 저절로 유지되지 않게.
  답은 사례 파일이 아니라 답 파일에만 둔다(사례 파일의 user_verdict는 비워 두는 것이 워크시트 시험의 전제).
- 정확도 점검 중(paused): B2 비교 위험 등으로 자동 판정을 멈춘 사업(`store.demoted_programs`).
- 검증 중(in_progress): 그 밖 — 판정 틀이 있어 판정하지만 독립 검증 전.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
STATUS_FILE = ROOT / "docs" / "independent-validation-status.json"
CASES_FILE = ROOT / "docs" / "independent-validation-cases.json"
ANSWERS_FILE = ROOT / "docs" / "independent-validation-answers.json"

VERIFIED, IN_PROGRESS, PAUSED = "verified", "in_progress", "paused"
LABEL = {VERIFIED: "독립 검증 완료", IN_PROGRESS: "검증 중", PAUSED: "정확도 점검 중"}
NOTE = {
    VERIFIED: "이 사업의 판정 방식은 사람이 공고문 원문만 보고 판단한 사례와 대조해 일치를 확인했습니다(독립 검증 완료).",
    IN_PROGRESS: "이 사업의 판정 방식은 사람이 공고문 원문만 보고 판단한 사례와 대조하는 중입니다(독립 검증 전).",
    PAUSED: "이 사업은 정확도 점검 중이라 새 공고 자동 판정을 잠시 멈췄습니다.",
}


@lru_cache(maxsize=None)
def _recorded() -> Dict[str, dict]:
    """대조를 마친 사업 기록 {템플릿: {"verified_at", "cases", "note"}}. 파일이 없으면 빈 기록(모두 검증 중)."""
    if not STATUS_FILE.exists():
        return {}
    return json.loads(STATUS_FILE.read_text(encoding="utf-8")).get("verified", {})


def answers() -> Dict[str, dict]:
    """사람 답 {사례 id(문자열): {"verdict", "page", "note"}} — 파일이 없으면 빈 답."""
    if not ANSWERS_FILE.exists():
        return {}
    return {str(k): v for k, v in json.loads(ANSWERS_FILE.read_text(encoding="utf-8")).get("answers", {}).items()}


def with_answers(cases: List[dict], ans: Optional[Dict[str, dict]] = None) -> List[dict]:
    """사례(입력)에 답 파일의 답을 user_verdict·user_page로 합친 복사본(사례 파일 자체는 바꾸지 않는다)."""
    ans = answers() if ans is None else ans
    out = []
    for c in cases:
        a = ans.get(str(c.get("id"))) or {}
        out.append(dict(c, user_verdict=(a.get("verdict") or "").strip(), user_page=a.get("page") or ""))
    return out


@lru_cache(maxsize=None)
def _json_cases_by_template() -> Dict[str, List[dict]]:
    from find import registered
    tmpl = {r.notice_id: r.template for r in registered()[0]}
    out: Dict[str, List[dict]] = {}
    if CASES_FILE.exists():
        for c in with_answers(json.loads(CASES_FILE.read_text(encoding="utf-8")).get("cases", [])):
            if c.get("notice") in tmpl:
                out.setdefault(tmpl[c["notice"]], []).append(c)
    return out


def status_of(template: Optional[str], demoted: Iterable[str] = ()) -> Optional[str]:
    """템플릿의 검증 상태 코드. 템플릿을 모르면 None(표시하지 않음)."""
    if not template:
        return None
    if template in set(demoted):
        return PAUSED
    rec = _recorded().get(template)
    cases = _json_cases_by_template().get(template, [])
    # 기록이 있어도 그 사업 사례 중 답이 빈 것이 있으면(사례를 더한 경우) 다시 '검증 중'. 엔진 불일치는 CI 시험이 막는다.
    if rec and cases and all(c.get("user_verdict") for c in cases):
        return VERIFIED
    return IN_PROGRESS


def verification_json(template: Optional[str], demoted: Iterable[str] = ()) -> Optional[dict]:
    code = status_of(template, demoted)
    if code is None:
        return None
    return {"template": template, "status": code, "label": LABEL[code], "note": NOTE[code]}


def program_name(template: str) -> str:
    import sys
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import templates as T
    d = T.TEMPLATES[template]
    return d["program"] if d["program"].startswith(d["issuer"]) else f"{d['issuer']} {d['program']}"


def all_programs(demoted: Iterable[str] = ()) -> List[dict]:
    """이용 안내 지원 범위 표 — 새 공고 자동 판정 사업(draft.PASSING)마다 이름·검증 상태."""
    import draft
    demoted = frozenset(demoted)
    return [dict(verification_json(t, demoted), program=program_name(t)) for t in draft.PASSING]
