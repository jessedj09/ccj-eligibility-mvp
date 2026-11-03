# -*- coding: utf-8 -*-
"""LLM 슬롯 '문장 찾기' 시험(docs/09 §20) — 로컬 모델 후보를 같은 문항으로 비교한다.

    python tools/eval_llm_slot.py --count                              # 문항 수만
    python tools/eval_llm_slot.py gemma4:e2b [다른 모델 …] [--out 결과폴더]

추출 평가(eval_extraction)는 결정론이 빈칸 대부분을 채워 LLM에게 묻는 문항이 몇 개뿐이라 모델 차이가 드러나지 않는다. 그래서 LLM 슬롯의
실제 일(`sheet_extract.llm_sentence` — 같은 사업 다른 공고의 문장을 예시로 이 공고의 같은 역할 조건 문장 찾기, 원문 잘라 오기·주제 겹침
검증 포함)을 등록 공고 정답으로 출제한다.
- 문항: SH 신혼 시트 문장 + 등록 규칙의 조건별 인용문(조건 ID가 같은 형제 공고 문장을 예시로). 숫자·날짜만 다른 문항(결정론이 푸는 것)은 뺀다.
- 판정: 맞음(정답 문장과 같은 쪽·같은 문장) / 겹침(같은 문장의 앞뒤만 다름) / **다른 문장**(검증을 통과한 오답) / 못 찾음.
- 답은 llm_slot의 캐시(.cache/llm/)를 쓴다 — 같은 모델·같은 문항은 다시 묻지 않는다.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

import llm_slot as L  # noqa: E402
import sheet_extract as X  # noqa: E402
import source_verify as sv  # noqa: E402
import templates as T  # noqa: E402

LABEL = {"right": "맞음", "overlap": "겹침", "different": "다른 문장", "none": "못 찾음"}


def _sheet_quotes(params):
    def walk(d, p):
        for k, v in d.items():
            if isinstance(v, str) and len(sv.normalize(v)) >= 10:
                yield p + k, v
            elif isinstance(v, dict):
                yield from walk(v, p + k + ".")
    yield from walk(params.get("quotes", {}), "")


def _condition_quotes(nid):
    """등록 규칙의 조건별 첫 인용문 — 키는 '계층/조건 ID에서 공고 번호를 뗀 이름'(예: 청년/T3-income)."""
    out = {}
    for layer, ls in sv.notice_doc(nid)["layers"].items():
        for c in sv.all_conditions(ls["conditions"]):
            q = c.get("source", {}).get("quote")
            q = q[0] if isinstance(q, list) and q else q
            q = q.get("text") if isinstance(q, dict) else q
            if isinstance(q, str) and len(sv.normalize(q)) >= 10:
                out.setdefault(layer + "/" + re.sub(r"^N\d+-", "", c["id"]), q)
    return out


def _digits_masked(s):
    return re.sub(r"[\d’‘'.~\-]", "", sv.normalize(s))


def items():
    """문항 목록: {nid, key, template, target(정규화 정답 문장), page, example(형제 문장), sibling}."""
    templates = {n: T.gold_sheet(n)["template"] for n in T.sheet_ids()}
    sources = [({n: dict(_sheet_quotes(T.gold_sheet(n)["params"])) for n in templates}),
               ({n: _condition_quotes(n) for n in templates})]
    out, seen = [], set()
    for quotes in sources:
        for nid, tpl in templates.items():
            pages = sv.pdf_pages(nid)
            for key, target in quotes[nid].items():
                tn = sv.normalize(target)
                page = X.on_page(pages, tn)
                if not page or (nid, tn) in seen:
                    continue
                for sid, stpl in templates.items():
                    ex = quotes[sid].get(key) if sid != nid and stpl == tpl else None
                    if ex and _digits_masked(ex) != _digits_masked(target):       # 표현이 실제로 다른 문항만
                        seen.add((nid, tn))
                        out.append(dict(nid=nid, key=key, template=tpl, target=tn, page=page, example=ex, sibling=sid))
                        break
    return out


def judge(got, item) -> str:
    if not got:
        return "none"
    page, quote = got
    target = item["target"]
    if page == item["page"] and (target in quote or quote in target or L.bigram_similarity(quote, target) >= 0.8):
        return "right"
    m = SequenceMatcher(None, target, quote, autojunk=False).find_longest_match(0, len(target), 0, len(quote))
    return "overlap" if page == item["page"] and m.size >= 0.6 * min(len(target), len(quote)) else "different"


class Slot(L.OllamaSlot):
    """시험용 — /api/chat이 500(일부 GGUF의 대화 양식 + 형식 강제 오류, 예: Kanana)이면 같은 내용을 /api/generate로 한 번 더."""
    fallback = 0

    def _post(self, body):
        try:
            return super()._post(body)
        except urllib.error.HTTPError as e:
            if e.code != 500:
                raise
            self.fallback += 1
            msgs = body["messages"]
            b = {"model": body["model"], "stream": False, "format": body["format"], "options": body["options"],
                 "system": msgs[0]["content"], "prompt": msgs[1]["content"]}
            req = urllib.request.Request(f"{self.host}/api/generate", json.dumps(b).encode("utf-8"),
                                         {"Content-Type": "application/json"})
            return {"message": {"content": json.load(urllib.request.urlopen(req, timeout=self.timeout))["response"]}}


def run(slot, its):
    raws, out = {}, []
    for it in its:
        raw = raws.setdefault(it["nid"], L.raw_pages(sv.pdf_path(it["nid"])))
        got = X.llm_sentence(sv.pdf_pages(it["nid"]), X.LLM(slot, raw), it["example"])
        out.append(dict(it, verdict=judge(got, it), got=got))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*", help="Ollama 모델 이름(기본: llm_slot.DEFAULT_MODEL)")
    ap.add_argument("--count", action="store_true", help="문항 수만 보고")
    ap.add_argument("--out", help="모델별 결과 JSON을 저장할 폴더")
    a = ap.parse_args(argv)
    its = items()
    print(f"문항 {len(its)}개 — " + ", ".join(f"{t} {n}" for t, n in Counter(i["template"] for i in its).most_common()))
    if a.count:
        return 0
    print("| 모델 | " + " | ".join(LABEL.values()) + " | 질문당 |\n|---|---|---|---|---|---|")
    for model in a.models or [L.DEFAULT_MODEL]:
        slot = Slot(model)
        res = run(slot, its)
        c = Counter(r["verdict"] for r in res)
        per = f"{slot.seconds / slot.calls:.1f}초" if slot.calls else "캐시"
        note = (f" (실패 {slot.failed})" if slot.failed else "") + (f" (generate 우회 {slot.fallback})" if slot.fallback else "")
        print(f"| {model}{note} | " + " | ".join(str(c[k]) for k in LABEL) + f" | {per} |")
        if a.out:
            Path(a.out).mkdir(parents=True, exist_ok=True)
            name = re.sub(r"[^\w.-]+", "_", model)
            (Path(a.out) / f"{name}.json").write_text(json.dumps(
                dict(model=model, calls=slot.calls, cached=slot.cached, failed=slot.failed, seconds=slot.seconds, results=res),
                ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
