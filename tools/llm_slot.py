# -*- coding: utf-8 -*-
"""LLM 슬롯(P1 T3.3, docs/09 §6) — 결정론 추출기가 못 채운 빈칸만 LLM에게 '원문에서 찾아 그대로 복사'하게 한다.

- 슬롯은 판정하지 않는다. 돌려받은 문장은 tools/sheet_extract.py의 검증(원문에 실제로 있는지·형제 문장과 같은 주제인지)을
  통과해야만 쓰인다 — 통과 못 하면 보류.
- 구현: NullSlot(LLM 없음), OllamaSlot(로컬 Ollama, 표준 라이브러리 HTTP만 — 새 패키지 없음). 나중에 Claude API 슬롯도 같은 모양으로.
- 같은 질문의 답은 .cache/llm/에 저장해 다시 쓴다(느린 로컬 모델 재실행 비용을 줄이고, 평가를 재현 가능하게).
"""
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "llm"

SYSTEM = ("너는 한국 공공임대주택 입주자모집공고문에서 문장을 찾아 **원문 그대로 복사**하는 도구다. "
          "요약·의역·판단을 하지 말고, 공고문에 적힌 글자를 그대로 옮긴다. 찾지 못하면 빈 문자열을 쓴다. "
          "쪽 번호는 [p.N] 표시를 보고 적는다.")


def raw_pages(pdf) -> List[str]:
    """LLM에게 보여 줄 쪽 텍스트(띄어쓰기 유지 — 대조용 정규화 텍스트는 띄어쓰기가 없어 읽기 어렵다)."""
    import logging
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    out = []
    for page in PdfReader(str(pdf)).pages:
        try:
            t = page.extract_text() or ""
        except Exception:   # noqa: BLE001 — 쪽 단위 추출 실패는 빈 쪽
            t = ""
        out.append("".join(ch for ch in t if ch >= " " or ch in "\n\t"))
    return out


def page_block(raw: List[str], page_nos: List[int], limit: int = 6000, focus: str = "") -> str:
    """LLM에게 보여 줄 쪽 텍스트. focus(예시 문장)가 있으면 쪽마다 그 문장과 가장 비슷한 부분 주변 limit자만 —
    모델 문맥(8K 토큰)을 넘겨 앞부분이 잘리지 않게, 그리고 빠르게."""
    parts = []
    for p in page_nos:
        if 1 <= p <= len(raw):
            parts.append(f"[p.{p}]\n{window(raw[p - 1], focus, limit) if focus else raw[p - 1][:limit]}")
    return "\n\n".join(parts)


def _grams(x: str) -> set:
    x = re.sub(r"[\s\W\d_]", "", x)
    return {x[i:i + 2] for i in range(len(x) - 1)}


def window(text: str, focus: str, size: int = 2500, step: int = 250) -> str:
    """text에서 focus와 글자 2-gram이 가장 많이 겹치는 size자 구간."""
    if len(text) <= size:
        return text
    want = _grams(focus)
    best, at = -1, 0
    for i in range(0, max(1, len(text) - size + step), step):
        score = len(want & _grams(text[i:i + size]))
        if score > best:
            best, at = score, i
    return text[at:at + size]


class NullSlot:
    name = "none"

    def find_sentence(self, *a, **kw) -> Optional[Tuple[str, int]]:
        return None

    def ask(self, *a, **kw) -> Optional[dict]:
        return None


class OllamaSlot:
    def __init__(self, model: str = "qwen3.5:4b", host: str = "http://127.0.0.1:11434", num_ctx: int = 8192,
                 timeout: int = 900):
        self.model, self.host, self.num_ctx, self.timeout = model, host, num_ctx, timeout
        self.name = f"ollama:{model}"
        self.calls = self.cached = 0
        self.seconds = 0.0

    def ask(self, prompt: str, schema: dict) -> Optional[dict]:
        body = {"model": self.model, "stream": False, "think": False, "format": schema,
                "options": {"temperature": 0, "num_ctx": self.num_ctx},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
        key = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:32]
        cache = CACHE / self.model.replace(":", "_") / f"{key}.json"
        if cache.exists():
            self.cached += 1
            return json.loads(cache.read_text(encoding="utf-8"))
        req = urllib.request.Request(f"{self.host}/api/chat", json.dumps(body).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        t = time.time()
        try:
            resp = json.load(urllib.request.urlopen(req, timeout=self.timeout))
            out = json.loads(resp["message"]["content"])
        except (OSError, ValueError, KeyError):
            return None
        self.calls += 1
        self.seconds += time.time() - t
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out

    def find_sentence(self, raw: List[str], page_nos: List[int], what: str, example: str) -> Optional[Tuple[str, int]]:
        """example(같은 사업 다른 공고의 문장)과 같은 뜻의 문장을 이 공고에서 찾아 (원문 문장, 쪽)."""
        prompt = (f"찾을 것: {what}\n같은 사업의 다른 공고에서는 이렇게 적혀 있었다(표현·날짜·숫자는 다를 수 있음):\n"
                  f"\"{example}\"\n\n아래 공고문 발췌에서 같은 뜻의 문장을 찾아 **발췌에 적힌 글자 그대로** 복사하라. "
                  "예시 문장은 이 공고에 없을 수 있으니 예시를 베끼지 말 것. 앞뒤 문장을 붙이지 말고 그 문장만, "
                  f"예시와 비슷한 길이로. 없으면 빈 문자열.\n\n{page_block(raw, page_nos[:2], 2500, example)}")
        schema = {"type": "object", "properties": {"quote": {"type": "string"}, "page": {"type": "integer"}},
                  "required": ["quote", "page"]}
        out = self.ask(prompt, schema)
        if not out or not str(out.get("quote", "")).strip():
            return None
        return str(out["quote"]).strip(), int(out.get("page") or 0)


def bigram_similarity(a: str, b: str) -> float:
    """두 문장의 글자 2-gram 겹침(Jaccard, 띄어쓰기·기호 무시) — LLM이 고른 문장이 예시와 같은 주제인지 거르는 데 쓴다."""
    def grams(s):
        s = re.sub(r"[\s\W\d_]", "", s)
        return {s[i:i + 2] for i in range(len(s) - 1)}
    ga, gb = grams(a), grams(b)
    return len(ga & gb) / len(ga | gb) if ga and gb else 0.0


def pages_like(pages: List[str], sentence: str, top: int = 2) -> List[int]:
    """예시 문장의 글자 2-gram이 많이 들어 있는 쪽(LLM에게 보여 줄 쪽 고르기)."""
    def grams(x):
        x = re.sub(r"[\s\W\d_]", "", x)
        return {x[i:i + 2] for i in range(len(x) - 1)}
    want = grams(sentence)
    if not want:
        return []
    scores = [(len(want & grams(t)) / len(want) if t else 0.0, i + 1) for i, t in enumerate(pages)]
    return [p for _, p in sorted(scores, reverse=True)[:top]]
