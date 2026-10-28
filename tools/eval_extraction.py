# -*- coding: utf-8 -*-
"""추출 정확도 평가(P1 T3.2·T3.4) — 등록 공고를 '처음 보는 공고'처럼 넣고 추출한 시트를 정답 시트와 빈칸 단위로 비교한다.

    python tools/eval_extraction.py --set tune     # 다듬기용 공고만(추출 규칙을 다듬는 동안 이것만 본다)
    python tools/eval_extraction.py --set test     # 시험용 공고(다듬기가 끝난 뒤 한 번)

빈칸 결과
- correct: 채운 값이 정답과 같다(문장 빈칸은 원문에서 찾은 근거면 정답 — 인용 위치 역할)
- held: 채우지 못했거나 검증 관문에서 걸려 보류 — 틀린 판정으로 이어지지 않는다
- wrong: 채운 값이 정답과 다르다, 또는 있어야 할 것을 '없다'고 했다(누락) — **틀린 통과**. 0이어야 한다
- ok_absent: 정답도 '없음', 추출도 '없음'
형제(같은 템플릿의 다른 공고) 정답 시트는 다듬기용 공고에서만 가져온다 — 시험용 공고의 정답을 추출에 쓰지 않는다.
"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools"), str(ROOT / "tests")]

import sheet_extract as X  # noqa: E402
import source_verify as sv  # noqa: E402
import templates as T  # noqa: E402

TEST = ["N4", "N8", "N10", "N12", "N14", "N17", "N21", "N24", "N26"]       # 사업별 최신 차수(행복주택은 3건)
TUNE = [n for n in T.sheet_ids() if n not in TEST]                         # 나머지 14건(1건뿐인 사업 포함)
SINGLE = {"N15", "N18", "N19", "N22"}                                       # 같은 템플릿·같은 종류가 하나뿐 — 표시

CORRECT, HELD, WRONG, OK_ABSENT = "correct", "held", "wrong", "ok_absent"
ALT = "alt"      # 근거 문장: 정답 시트와 다른 곳이지만 정답 문장의 값(금액·비율·날짜)을 모두 담은 원문 — 같은 근거의 다른 표현


LOO = False     # --loo: 형제 = 같은 템플릿의 등록 공고 전부(자기 제외) — 실제 새 공고가 들어올 때와 같은 조건


def siblings_for(nid):
    """형제 정답 시트 — 다듬기용 공고 중 같은 템플릿(자기 자신 제외). --loo면 등록 공고 전부 중에서."""
    def f(template):
        pool = T.sheet_ids() if LOO else TUNE
        return [T.gold_sheet(n) for n in pool if n != nid and T.gold_sheet(n)["template"] == template]
    return f


def _dates_in(text):
    out = set()
    for m in X._TOKEN.finditer(str(text)):
        y = int(m.group("y"))
        y = y if y > 999 else 2000 + y if y < 50 else 1900 + y
        try:
            out.add(date(y, int(m.group("m")), int(m.group("d"))))
        except ValueError:
            pass
    return out


def _norm(x):
    return sv.normalize(str(x)) if x is not None else None


def _cmp_text(gold, f):
    if f.status != X.FILLED:
        return HELD
    if _norm(gold) == _norm(f.value) or (_dates_in(gold) and _dates_in(gold) == _dates_in(f.value)):
        return CORRECT
    return WRONG


def _cmp_eq(gold, f):
    if f.status == X.HELD:
        return HELD
    if f.status == X.ABSENT:
        return OK_ABSENT if gold in (None, {}, [], False) else WRONG
    return CORRECT if gold == f.value else WRONG


def same_place(gold: str, got: str) -> bool:
    """근거 문장이 정답 시트의 문장과 같은 곳을 가리키는지 — 한쪽이 다른 쪽을 담거나, 글자의 60% 이상이 겹친다
    (앞뒤로 몇 글자 더/덜 잘린 것은 같은 근거로 본다)."""
    from difflib import SequenceMatcher
    a, b = _norm(gold), _norm(got)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    m = sum(x.size for x in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    return m / min(len(a), len(b)) >= 0.6


def _cmp_quote(gold, f):
    """문장 빈칸: 못 찾으면 보류. 찾은 근거가 정답 시트 문장과 다른 곳이면 틀림(2026-10-28 — 근거 문장을 값·핵심 표현으로
    다시 찾기 시작하며 위치까지 본다)."""
    if f.status != X.FILLED:
        return HELD
    if isinstance(gold, str) and isinstance(f.value, str) and not same_place(gold, f.value):
        gv, fv = _norm(gold), _norm(f.value)
        values = X._values_of(gv) | {str(d) for d in X._dates_of(gv)}
        got = X._values_of(fv) | {str(d) for d in X._dates_of(fv)}
        # 값이 서로 어긋나지 않으면(한쪽이 다른 쪽의 값을 모두 담음 — 예: 정답 '130%·맞벌이 200%', 찾은 곳 '130%') 다른 곳의
        # 같은 근거. 값이 다르면(70% ↔ 130%) 틀림.
        return ALT if values and got and (values <= got or got <= values) else WRONG
    return CORRECT


def compare(gold: dict, ext: dict):
    """→ [(빈칸 이름, 결과, critical)]"""
    rows = [("announcement_date", _cmp_eq(gold["announcement_date"], ext["announcement_date"]), True)]
    if ext["template"] != gold["template"]:
        return rows + [("template", WRONG, True)]
    spec = {p.name: p for p in T.TEMPLATES[gold["template"]]["params"]}
    g, fields = gold["params"], ext["fields"]
    for name, p in spec.items():
        f = fields.get(name)
        gv = g.get(name)
        if p.kind in ("dates",):
            for k in sorted(set(gv or {}) | set(f or {})):
                fk = (f or {}).get(k) or X.Field(X.ABSENT)
                rows.append((f"{name}.{k}", _cmp_eq((gv or {}).get(k), fk), True))
        elif p.kind == "quotes" and name != "overrides":
            for k in sorted(set(gv or {}) | set(f or {})):
                gk, fk = (gv or {}).get(k), (f or {}).get(k) or X.Field(X.HELD)
                if isinstance(gk, dict):        # 우선공급 문장 묶음
                    for kk in sorted(set(gk) | set(fk if isinstance(fk, dict) else {})):
                        sub = fk.get(kk, X.Field(X.HELD)) if isinstance(fk, dict) else X.Field(X.HELD)
                        rows.append((f"{name}.{k}.{kk}", _cmp_quote(gk.get(kk), sub), False))
                elif isinstance(gk, (bool, int)) or k in ("minor_date",):
                    rows.append((f"{name}.{k}", _cmp_eq(gk, fk), True))
                elif k in ("assets", "car"):
                    rows.append((f"{name}.{k}", _cmp_text(gk, fk), True))
                else:
                    rows.append((f"{name}.{k}", _cmp_quote(gk, fk), False))
        elif name == "overrides":
            if f is not None and f.status == X.FILLED:
                rows.append((name, CORRECT, False))       # LLM이 찾은 원문 문장(원문·주제 확인됨)
            else:
                rows.append((name, HELD if gv else OK_ABSENT, False))
        elif name == "region":
            if f is None or f.status == X.ABSENT:
                rows.append((name, WRONG if gv else OK_ABSENT, True))
            elif f.status == X.FILLED:
                want = {k: v["fields"] for k, v in (gv or {}).items()}
                got = {k: v["fields"] for k, v in f.value.items()}
                rows.append((name, CORRECT if gv and want == got else WRONG, True))
            else:
                rows.append((name, HELD, True))
        elif name == "extra_layers":
            want = {k: (v["builder"], v["args"]) for k, v in (gv or {}).items()}
            got = {k: (v["builder"], v["args"]) for k, v in (f.value or {}).items()} if f else {}
            rows.append((name, CORRECT if want == got else WRONG, True))
        elif name == "weak":
            if f is None or f.status == X.ABSENT:
                rows.append((name, WRONG if gv else OK_ABSENT, True))
            elif f.status == X.HELD:
                rows.append((name, HELD, True))
            else:
                same = gv and gv.get("bases") == f.value.get("bases") and gv.get("elderly") == f.value.get("elderly")
                rows.append((name, CORRECT if same else WRONG, True))
        elif name == "layers":
            rows.append((name, (CORRECT if sorted(gv) == sorted(f.value) else WRONG) if f.status == X.FILLED else HELD, True))
        elif name == "weak_quote":
            if f is None or f.status == X.ABSENT:
                rows.append((name, WRONG if gv else OK_ABSENT, True))
            else:
                rows.append((name, _cmp_quote(gv, f) if gv else WRONG, True))
        elif p.kind == "text":
            rows.append((name, _cmp_text(gv, f) if f else HELD, p.critical))
        elif p.kind == "table":
            rows.append((name, HELD if (f is None or f.status != X.FILLED) else (CORRECT if f.value == gv else WRONG), True))
        else:
            rows.append((name, _cmp_eq(gv, f) if f else HELD, p.critical))
    return rows


SAME, J_HELD, J_WRONG = "same", "held", "wrong"


def judgment_agreement(nid, g, limit=None):
    """골든 입력으로 자동 규칙(g = sheet_extract.gate 결과)과 등록 규칙의 판정을 비교 — P2 동작을 흉내 낸다:
    핵심 빈칸 보류·규칙 생성 실패면 그 공고 전부 보류, 인용문을 못 찾은 조건이 판정에 쓰이면 그 판정은 수동 확인.
    → Counter(same / held / wrong[자동 규칙이 '지원 가능·불가'로 확정했는데 등록 규칙과 다름]) + 계층 차이"""
    import golden_cases as gc
    from rule_data import build_notice, load_notice
    from rule_engine import evaluate as judge
    reg = load_notice(nid)
    out, notes = Counter(), []
    groups = [(n, layer) for n, layer in gc.GROUPS if n == nid]
    auto = None
    if g["doc"] is not None and not g["critical_held"]:
        auto = build_notice(g["doc"])
        extra = set(auto.layers) - set(reg.layers)
        if extra:
            notes.append(f"등록에 없는 계층 {sorted(extra)}")
            out[J_WRONG] += len(extra)
    missing_ids = set(re.findall(r"(N\d+-[A-Za-z0-9가-힣-]+)", " ".join(g["missing"])))
    for _, layer in groups:
        cases = [p for _, _, p in gc.cases(only=[(nid, layer)])]
        cases = cases[:limit] if limit else cases
        if auto is None or layer not in auto.layers:
            out[J_HELD] += len(cases)
            if auto is not None:
                notes.append(f"계층 없음 {layer}")
            continue
        aff = X.affected_conditions(auto.layers[layer].conditions, missing_ids)
        restricted = bool(g.get("restrictions"))
        for p in cases:
            r, a = judge(p, reg, layer).verdict, judge(p, auto, layer)
            av = X.adjust_verdict(a, aff, restricted)
            out[SAME if av == r else J_HELD if av in ("MANUAL_REVIEW", "NEEDS_INFO") else J_WRONG] += 1
    return out, notes


def make_llm(model):
    """--llm 모델 이름 → 공고마다 LLM 문맥을 만드는 함수(없으면 None — 결정론만)."""
    if not model:
        return None
    import llm_slot as L
    slot = L.OllamaSlot(model)
    return lambda nid: X.LLM(slot, L.raw_pages(sv.pdf_path(nid)))


def evaluate(nids, verbose=False, llm_for=None):
    per = {}
    for nid in nids:
        gold = T.gold_sheet(nid)
        llm = llm_for(nid) if llm_for else None
        ext = X.extract(sv.pdf_pages(nid), siblings_for(nid), llm)
        rows = compare(gold, ext)
        per[nid] = dict(template=gold["template"], rows=rows, ext=ext, llm=llm)
        if verbose:
            bad = [(n, r) for n, r, c in rows if r in (WRONG, HELD, ALT)]
            print(f"{nid} {gold['template']}: " + ", ".join(f"{n}={r}" for n, r in bad) if bad else f"{nid} 모두 맞음")
    return per


def summarize(per):
    tot, crit = Counter(), Counter()
    by_t = defaultdict(Counter)
    for nid, d in per.items():
        for name, r, c in d["rows"]:
            tot[r] += 1
            by_t[d["template"]][r] += 1
            if c:
                crit[r] += 1
    return tot, crit, by_t


def judge_all(per, limit=None, verbose=False):
    total = Counter()
    for nid, d in per.items():
        g = X.gate(d["ext"], sv.pdf_path(nid), sv.pdf_pages(nid), nid, d.get("llm"))
        c, notes = judgment_agreement(nid, g, limit)
        d["judge"], d["gate"] = c, g
        total += c
        if verbose:
            n = sum(c.values())
            print(f"  {nid}: 같음 {c[SAME]}/{n} · 보류 {c[J_HELD]} · 틀림 {c[J_WRONG]}"
                  + (f" | 핵심 보류 {g['critical_held']}" if g["critical_held"] else "")
                  + (f" | 인용 못 찾음 {len(g['missing'])}" if g["missing"] else "")
                  + (f" | {g['blocked']}" if g["blocked"] else "") + (f" | {notes}" if notes else ""))
    return total


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["tune", "test", "all"], default="tune")
    ap.add_argument("-v", action="store_true")
    ap.add_argument("--judge", action="store_true", help="골든 입력으로 판정 일치율까지(시간이 걸림)")
    ap.add_argument("--limit", type=int, help="계층마다 골든 입력 앞 N건만")
    ap.add_argument("--llm", help="결정론이 못 채운 빈칸을 물어볼 로컬 Ollama 모델(예: ministral-3:3b)")
    ap.add_argument("--loo", action="store_true",
                    help="형제를 등록 공고 전부(자기 제외)에서 — 실제 새 공고 조건(다듬기/시험 구분 없는 하나 빼고 맞혀 보기)")
    a = ap.parse_args(argv)
    global LOO
    LOO = a.loo
    nids = {"tune": TUNE, "test": TEST, "all": TUNE + TEST}[a.set]
    llm_for = make_llm(a.llm)
    per = evaluate(nids, verbose=a.v, llm_for=llm_for)
    tot, crit, by_t = summarize(per)
    n = sum(tot.values())
    filled = tot[CORRECT] + tot[ALT] + tot[WRONG] + tot[OK_ABSENT]
    print(f"[{a.set}] 공고 {len(nids)}건, 빈칸 {n}개 — 맞음 {tot[CORRECT]} · 없음 일치 {tot[OK_ABSENT]} · 보류 {tot[HELD]} · "
          f"틀림 {tot[WRONG]}" + (f" · 다른 곳·같은 값 {tot[ALT]}" if tot[ALT] else "") + f" | 자동 채움 {filled / n:.0%} · 핵심 빈칸 틀림 {crit[WRONG]}")
    for t, c in sorted(by_t.items()):
        m = sum(c.values())
        print(f"  {t}: 맞음 {c[CORRECT] + c[OK_ABSENT]}/{m} · 보류 {c[HELD]} · 틀림 {c[WRONG]}"
              + (f" · 다른 곳·같은 값 {c[ALT]}" if c[ALT] else ""))
    if llm_for:
        slot = next((d["llm"].slot for d in per.values() if d.get("llm")), None)
        if slot:
            print(f"LLM {slot.name}: 새 호출 {slot.calls}회({slot.seconds:.0f}초) · 저장된 답 재사용 {slot.cached}회"
                  + (f" · **실패 {slot.failed}회**" if slot.failed else ""))
            if slot.failed and not slot.calls and not slot.cached:
                print("경고: LLM 호출이 모두 실패했습니다 — 위 결과는 결정론만과 같습니다(모델을 받았는지·Ollama가 켜져 있는지 확인).")
    if a.judge:
        j = judge_all(per, a.limit, verbose=a.v)
        n = sum(j.values())
        print(f"판정 일치(골든 입력 {n}건): 같음 {j[SAME] / n:.1%} · 보류 {j[J_HELD] / n:.1%} · 확정 판정 틀림 {j[J_WRONG]}건")
        return 1 if tot[WRONG] or j[J_WRONG] else 0
    return 1 if tot[WRONG] else 0


if __name__ == "__main__":
    sys.exit(main())
