# -*- coding: utf-8 -*-
"""sentence_check.py — 조항 장부 미분류 문장 분류(R2, docs/13 2-1·2-4 R-③, docs/09 §23).

조항 장부(tools/clause_ledger.py)가 근거·형제 공고·무관 범주 어디에도 넣지 못한 '조건처럼 보이는 문장'(미분류)을 LLM이
'조건 아님 / 새 조건'으로 나눈다. 미분류 문장이 하나라도 걸린 계층은 '지원 가능'이 전부 보류가 되므로(grading), 진짜 조건이 아닌
문장을 확인할 곳에서 빼면 불필요한 보류(④)가 준다. 반대로 진짜 새 조건을 빼면 틀린 지원 가능(①)이 생긴다 — 그래서
**문장을 빼는 것은 LLM이 '조건 아님'이고, 결정론 표지(guard)도 없을 때만**이다.

- guard 판: a = 강한 제한 표현(clause_ledger.STRONG)만 · b = a + 기준값(금액·비율·기간·나이·날짜) ·
  c = b + 부드러운 제한 표현('에 한함'·'제외'·'충족하여야'·'인 경우에 한하여' …)
- 문장 id(R-① 질문형 확인·R-③ 공고 단위 해소 공용, ProjectCCJ_work와 합의): sentence_id(sha256, 쪽, 문장)
- LLM은 공고문(공개 문서)만 읽는다. 판정 요청의 개인정보는 보내지 않는다. 판정은 결정론 그대로.
"""
import hashlib
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

import source_verify as sv  # noqa: E402

NOT_CONDITION, NEW_CONDITION = "조건 아님", "새 조건"

VALUE = re.compile(r"\d[\d,.]*(?:억|천만|백만|만|천)?(?:원|%|퍼센트|년|개월|일|세|㎡|m2|회|명|인)|\d{2,4}\.\d{1,2}\.\d{1,2}|만\d{1,3}세")
SOFT = re.compile(r"(에한함|에한하며|에한하여|에한한|인경우에한|만해당|만가능|제외|충족하여야|충족해야|이어야|여야하|여야함|하여야|해야|"
                  r"대상이아니|대상이아닙|아닙니다|아님|대상에서|자격이없|자격없|보지않|보지아니|인정하지|아니한자|않은자|않는자|불가|없습니다|할수없|한정)")


def sentence_id(sha256: str, page: int, text: str) -> str:
    """미분류 문장 id — 원문 sha256 앞 16자 : 쪽 : 정규화 문장 sha1 앞 12자. sv.normalize를 바꾸면 id가 바뀐다(해소 기록 재계산)."""
    return f"{sha256[:16]}:{page}:{hashlib.sha1(sv.normalize(text).encode('utf-8')).hexdigest()[:12]}"


def guard(text: str, mode: str = "c") -> bool:
    """결정론 표지가 있으면 True(문장을 빼지 않음)."""
    import clause_ledger as CL
    t = sv.normalize(text)
    if CL.STRONG.search(t):
        return True
    if mode in ("b", "c") and VALUE.search(t):
        return True
    if mode == "c" and SOFT.search(t):
        return True
    return False


SYSTEM = ("너는 한국 공공주택 입주자모집공고문의 문장을 분류하는 도구다. 판단이 애매하면 반드시 '새 조건'으로 답한다. "
          "판정·계산을 하지 말고 문장의 성격만 본다.")
SCHEMA = {"type": "object", "properties": {"label": {"type": "string", "enum": [NOT_CONDITION, NEW_CONDITION]},
                                           "reason": {"type": "string"}}, "required": ["label", "reason"]}


def prompt_for(text: str, context: str, layers: List[str]) -> str:
    return ("아래 '문장'이 신청 자격을 새로 정하거나 제한하는 **조건**인지 분류하라.\n"
            "- 새 조건: 누가 신청할 수 있는지/없는지를 정하거나 좁히는 문장(거주·나이·소득·자산·혼인·자녀·주택 소유·청약통장·직업·"
            "이전 당첨 이력 등의 요건, '~에 한함'·'~는 제외'·'~이어야 함'·'신청할 수 없음').\n"
            "- 조건 아님: 서류 제출·절차·일정·계약·임대 조건 안내, 용어 정의·산정 방법, 당첨자 선정·순위·배정 물량, 이미 정한 자격을 "
            "다시 설명하는 제목·소제목, 문의처.\n"
            f"공급 계층: {', '.join(layers) or '모름'}\n\n문장: \"{text}\"\n\n문장 주변 원문(참고):\n{context}\n\n"
            "애매하면 '새 조건'. label과 짧은 reason을 적어라.")


def context_of(raw_pages: List[str], page: int, text: str, size: int = 1200) -> str:
    from llm_slot import window
    if not 1 <= page <= len(raw_pages):
        return ""
    return window(raw_pages[page - 1], text, size)


class OllamaClassifier:
    """분류 슬롯(모델 바꿔 끼우기) — llm_slot.OllamaSlot의 캐시·전송, 시스템 지시만 분류용."""

    def __init__(self, model: Optional[str] = None, **kw):
        from llm_slot import DEFAULT_MODEL, OllamaSlot
        self._s = OllamaSlot(model or DEFAULT_MODEL, **kw)
        self.name = self._s.name

    def ask(self, prompt: str, schema: dict) -> Optional[dict]:
        import llm_slot
        old, llm_slot.SYSTEM = llm_slot.SYSTEM, SYSTEM
        try:
            return self._s.ask(prompt, schema)
        finally:
            llm_slot.SYSTEM = old

    @property
    def stats(self):
        return {"calls": self._s.calls, "cached": self._s.cached, "failed": self._s.failed, "seconds": round(self._s.seconds, 1)}


def classifier(name: str):
    if name.startswith("claude"):
        raise NotImplementedError("Claude API 분류는 사용자 승인 뒤 연결합니다")
    return OllamaClassifier(name.split("ollama:", 1)[-1] if name else None)


def classify(slot, text: str, context: str, layers: List[str]) -> Optional[str]:
    """LLM 분류 — '조건 아님' / '새 조건' / None(답 없음 = 새 조건과 같게 다룬다: 빼지 않음)."""
    out = slot.ask(prompt_for(text, context, layers), SCHEMA)
    lab = (out or {}).get("label") if isinstance(out, dict) else None
    return lab if lab in (NOT_CONDITION, NEW_CONDITION) else None


def clears(label: Optional[str], text: str, mode: str = "c") -> bool:
    """확인할 곳에서 뺄 수 있는가 — LLM '조건 아님' AND 결정론 표지 없음."""
    return label == NOT_CONDITION and not guard(text, mode)


def decide(slot, d, raw_pages: List[str], mode: str = "c") -> List[Tuple[int, str, Optional[str], bool]]:
    """초안의 미분류 문장마다 (쪽, 문장, LLM 분류, 뺄 수 있음). 대기열 정렬 신호로만 쓴다(채택 전)."""
    layers = list(d.notice.layers) if getattr(d, "notice", None) else []
    out = []
    for page, text in d.unclassified:
        lab = classify(slot, text, context_of(raw_pages, page, text), layers)
        out.append((page, text, lab, clears(lab, text, mode)))
    return out


# ------------------------------------------------------------------ R-③ 공고 단위 해소에 넘길 후보(2026-11-15 사용자 승인 — 3단계 해결안)
REQUIRED, REFERENCE = "required", "reference"


def tier_of(d, page: int, text: str) -> str:
    """필수/참고 — 필수 = 자격 영역(계층마다 조건 근거 쪽 범위, grading.layer_pages) 안에 있거나 결정론 표지(guard 'c': 강한·부드러운
    제한 표현·기준값)가 있음. ProjectCCJ_work clause_resolution과 같은 정의(guard·sentence_id 이름 유지). 질문·해소 순서에만 쓴다."""
    import grading
    inside = any(a <= page <= b for a, b in grading.layer_pages(d.doc).values()) if d.doc else False
    return REQUIRED if inside or guard(text, "c") else REFERENCE


def candidates(d, raw_pages: List[str], sha256: str, slot=None) -> List[dict]:
    """초안의 미분류 문장 → R-③ 저장소(clause_resolutions)에 'proposed'로 넣을 행. ProjectCCJ_work tools/resolve_clauses.py import와
    맞춘 모양: {sha256, sentence_id, page, sentence, context, tier(required/reference), draft_verdict('조건 아님'/'새 조건'/None), reason,
    template}. slot(LLM)이 없으면 draft_verdict는 None(판정 초안 없음).
    판정에는 쓰지 않는다 — 판정자(운영자·Claude 세션)가 확정해야 반영된다(R-③ 안전 조건)."""
    rows = []
    layers = list(d.notice.layers) if getattr(d, "notice", None) else []
    for page, text in dict.fromkeys(d.unclassified):
        context = context_of(raw_pages, page, text)
        verdict, reason = None, ""
        if slot is not None:
            out = slot.ask(prompt_for(text, context, layers), SCHEMA)
            lab = (out or {}).get("label") if isinstance(out, dict) else None
            verdict = lab if lab in (NOT_CONDITION, NEW_CONDITION) else None
            reason = str((out or {}).get("reason", ""))[:200] if verdict else ""
        rows.append({"sha256": sha256, "sentence_id": sentence_id(sha256, page, text), "page": page, "sentence": text,
                     "context": context, "tier": tier_of(d, page, text), "draft_verdict": verdict, "reason": reason,
                     "template": getattr(d, "template", None)})
    rows.sort(key=lambda r: (r["tier"] != REQUIRED, r["page"]))
    return rows
