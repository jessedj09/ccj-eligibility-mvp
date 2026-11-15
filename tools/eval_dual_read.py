# -*- coding: utf-8 -*-
"""이중 읽기(R1) 평가 — docs/09 §22.

    python tools/eval_dual_read.py --stage 0 [--nid N30 …] [--out docs/eval-dual-read.md]

1단계(--stage 1 [--model gemma4:e2b]): 같은 초안에 대해 LLM이 원문만 보고 계층·항목마다 값을 읽고(dual_read.llm_read), 조건마다
신호(일치/부분/불일치/답 없음)를 낸다. 지표 — 헛경보(초안이 맞는데 불일치), 일부러 넣은 오류(초안 값 하나를 다른 공고 값·한 해 밀린 날짜 등으로
바꿈 — LLM 답은 그대로, 다시 묻지 않음)를 불일치로 잡은 비율과 **잘못된 일치**(바꾼 값을 일치로 넘김 — 0이어야), 답 없음 비율(사업별).

0단계(LLM 없음): 등록 공고를 '처음 보는 공고'처럼 자동 분석한 초안(make_draft exclude=자기)의 핵심 값(tools/dual_read.facts)을
등록 규칙의 핵심 값과 조건마다 대조한다 — 결정론 추출이 실제로 틀리는 빈도(기준선). 이중 읽기가 잡아야 할 '실제 결정론 오류'의 목록이다.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools"), str(ROOT / "tests")]

import draft  # noqa: E402
import dual_read as D  # noqa: E402
import source_verify as sv  # noqa: E402
import templates as T  # noqa: E402
from rule_data import notice_ids  # noqa: E402


def registered_doc(nid):
    return sv.notice_doc(nid)


def stage0(nid):
    d = draft.make_draft(sv.pdf_path(nid).read_bytes(), only=None, pages=sv.pdf_pages(nid), exclude=nid)
    truth = D.facts(registered_doc(nid))
    row = {"nid": nid, "status": d.status, "template": d.template, "truth": len(truth)}
    if d.status != draft.OK or not d.doc:
        row["reason"] = d.reason
        return row, truth, {}
    got = D.facts(d.doc)
    cmp = D.compare(got, truth)
    row.update({k: len(v) for k, v in cmp.items()})
    row["layers_same"] = D.layers(d.doc) == D.layers(registered_doc(nid))
    row["detail"] = cmp
    return row, truth, got


def _pool(nids):
    """일부러 넣을 오류 후보 값 — 항목별로 다른 공고들이 쓰는 값."""
    pool = {}
    for nid in nids:
        for f in D.facts(sv.notice_doc(nid)).values():
            pool.setdefault(f["kind"], set()).update(f["values"])
    return pool


def mutate(kind, v, text, pool, salt, S=()):
    """바꿔 넣을 틀린 값 w — 그 조건에 이미 있는 값은 고르지 않는다(이미 있는 값으로 바꾸면 '바꿔치기'가 아니라 '지우기'가 됨).
    원문 다른 자리에 있는 값(표의 옆 칸 비율 등)도 고를 수 있다 — 칸을 잘못 읽은 오류가 가장 그럴듯한 오류다."""
    import hashlib
    S = set(S)
    if kind == "date":
        y, m, d = v.split("-")
        w = f"{int(y) - 1}-{m}-{d}"
        return w if w not in S else None
    if kind == "age":
        return next((w for w in (v + 1, v - 1, v + 2) if w not in S), None)
    if kind == "income" and v[0] == "%":
        return next((("%", v[1] + d) for d in (10, -10, 20, -20, 30) if ("%", v[1] + d) not in S and 30 <= v[1] + d <= 300), None)
    cands = sorted((w for w in pool.get(kind, ()) if w != v and w not in S and type(w) is type(v) and not D.in_text(kind, w, text)
                    and (kind != "income" or w[0] == v[0])), key=str)
    if not cands:
        return None
    h = int(hashlib.sha256(f"{salt}".encode()).hexdigest(), 16)
    return cands[h % len(cands)]


def stage1(nid, slot, pool):
    import llm_slot
    d = draft.make_draft(sv.pdf_path(nid).read_bytes(), only=None, pages=sv.pdf_pages(nid), exclude=nid)
    if d.status != draft.OK or not d.doc:
        return None
    got = D.facts(d.doc)
    norm = sv.pdf_pages(nid)
    text = "".join(norm)
    raw = llm_slot.raw_pages(sv.pdf_path(nid))
    by_lk = {}
    for (layer, key), f in got.items():
        by_lk.setdefault((layer, f["kind"]), []).append(key)
    reads = {lk: [v for v, _, _ in D.llm_read(slot, raw, norm, *lk)] for lk in by_lk}
    rows = []
    for (layer, kind), keys in by_lk.items():
        V = reads[(layer, kind)]
        U = set().union(*(got[(layer, k)]["values"] for k in keys))
        for k in keys:
            S = got[(layer, k)]["values"]
            real = D.signal(V, S, U, kind, text)
            muts, dels = [], []
            for i, v in enumerate(sorted(S, key=str)):
                if kind in ("income", "age") and not D.in_text(kind, v, text):
                    continue                       # 계산된 값은 원문 읽기로 확인할 수 없음 — 바꿔 넣는 시험에서 뺌
                w = mutate(kind, v, text, pool, f"{nid}|{layer}|{k}|{i}", S)
                if w is not None:
                    S2 = (set(S) - {v}) | {w}
                    U2 = (U - {v}) | {w}
                    muts.append(D.signal(V, S2, U2, kind, text))
                if len(S) >= 2:                    # 지우기(값 하나가 빠짐) — 이중 읽기의 한계를 따로 센다
                    dels.append(D.signal(V, set(S) - {v}, U - {v} if not any(v in got[(layer, k2)]["values"] for k2 in keys if k2 != k) else U,
                                         kind, text))
            rows.append({"nid": nid, "template": d.template, "layer": layer, "key": k, "kind": kind,
                         "real": real, "muts": muts, "dels": dels, "V": sorted(map(str, V)), "S": sorted(map(str, S))})
    return rows


def main_stage1(a):
    slot = D.reader(a.model)
    nids = a.nid or T.sheet_ids()
    pool = _pool(T.sheet_ids())
    allrows = []
    for nid in nids:
        try:
            rows = stage1(nid, slot, pool)
        except Exception as e:  # noqa: BLE001
            print(f"{nid} 오류 {type(e).__name__}: {e}", file=sys.stderr)
            continue
        allrows += rows or []
        print(f"{nid} {len(rows or [])}조건 {getattr(slot, 'stats', '')}", file=sys.stderr, flush=True)
    by_t = {}
    for r in allrows:
        c = by_t.setdefault(r["template"], Counter())
        c["cond"] += 1
        c["real:" + r["real"]] += 1
        for m in r["muts"]:
            c["mut"] += 1
            c["mut:" + m] += 1
        for m in r["dels"]:
            c["del"] += 1
            c["del:" + m] += 1
    tot = sum(by_t.values(), Counter())

    def pct(a, b):
        return f"{100 * a / b:.1f}%" if b else "—"
    head = ["| 사업 | 조건 | 일치 | 부분 | **불일치(헛경보)** | 답 없음 | 바꿔 넣은 오류 | 잡음(불일치) | **잘못된 일치** | 중립 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    def line(name, c):
        return (f"| {name} | {c['cond']} | {c['real:일치']} | {c['real:부분']} | {c['real:불일치']} ({pct(c['real:불일치'], c['cond'])}) | "
                f"{c['real:답 없음']} ({pct(c['real:답 없음'], c['cond'])}) | {c['mut']} | {c['mut:불일치']} ({pct(c['mut:불일치'], c['mut'])}) | "
                f"{c['mut:일치']} | {c['mut:부분'] + c['mut:답 없음']} |")
    lines = [f"# 이중 읽기 1단계 — {slot.name}", "", f"공고 {len({r['nid'] for r in allrows})}건 · {getattr(slot, 'stats', '')}", ""] + head
    lines += [line(t, c) for t, c in sorted(by_t.items())] + [line("**합계**", tot)]
    kinds = {}
    for r in allrows:
        c = kinds.setdefault(r["kind"], Counter())
        c["cond"] += 1
        c["real:" + r["real"]] += 1
        for m in r["muts"]:
            c["mut"] += 1
            c["mut:" + m] += 1
    lines += ["", "## 항목별", ""] + head + [line(k, c) for k, c in sorted(kinds.items())]
    lines += ["", "## 지우기(값 하나가 빠진 초안) — 이중 읽기의 한계", "",
              f"- 지운 경우 {tot['del']} · 불일치로 잡음 {tot['del:불일치']} · **일치로 넘김 {tot['del:일치']}** · 중립 {tot['del:부분'] + tot['del:답 없음']}",
              "- '일치'는 '초안 값이 모두 원문에서 확인됨'이지 '빠진 값이 없음'이 아니다 — LLM이 읽지 못한 칸이 빠지면 알 수 없다."]
    lines += ["", "## 헛경보(초안이 맞는데 불일치)", ""]
    lines += [f"- {r['nid']} {r['layer']} {r['key']}({r['kind']}): LLM {r['V']} / 초안 {r['S']}" for r in allrows if r["real"] == D.DISAGREE]
    lines += ["", "## 잘못된 일치(바꾼 값을 일치로 넘김)", ""]
    lines += [f"- {r['nid']} {r['layer']} {r['key']}({r['kind']})" for r in allrows if D.AGREE in r["muts"]]
    text = "\n".join(lines)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    if a.json:
        import json
        Path(a.json).write_text(json.dumps(allrows, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, default=0)
    ap.add_argument("--nid", nargs="*")
    ap.add_argument("--out")
    ap.add_argument("--model", default="gemma4:e2b", help="읽기 모델(ollama 이름 또는 claude:… — Claude는 사용자 승인 뒤)")
    ap.add_argument("--json", help="조건별 결과 JSON")
    a = ap.parse_args(argv)
    if a.stage == 1:
        return main_stage1(a)
    nids = a.nid or T.sheet_ids()
    lines = ["# 이중 읽기 0단계 — 결정론 초안 vs 등록 규칙 핵심 값(조건 단위)", "",
             "| 공고 | 사업 | 초안 | 등록 조건 | 같음 | **다름** | 초안에만 | 등록에만 | 계층 구성 같음 |", "|---|---|---|---|---|---|---|---|---|"]
    tot = Counter()
    by_kind = Counter()
    diffs = []
    for nid in nids:
        try:
            row, truth, got = stage0(nid)
        except Exception as e:  # noqa: BLE001
            lines.append(f"| {nid} | — | 오류 {type(e).__name__}: {e} | | | | | | |")
            continue
        if row["status"] != draft.OK:
            tot["not_ok"] += 1
            lines.append(f"| {nid} | {row['template']} | {row['status']} | {row['truth']} | | | | | |")
            continue
        for k in ("same", "differ", "draft_only", "truth_only"):
            tot[k] += row[k]
            for key in row["detail"][k]:
                by_kind[(k, (truth.get(key) or got.get(key))["kind"])] += 1
        for key in row["detail"]["differ"]:
            diffs.append((nid, key, sorted(got[key]["values"], key=str), sorted(truth[key]["values"], key=str)))
        tot["notices"] += 1
        lines.append(f"| {nid} | {row['template']} | ok | {row['truth']} | {row['same']} | {row['differ']} | {row['draft_only']} | "
                     f"{row['truth_only']} | {'예' if row['layers_same'] else '**아니오**'} |")
    lines += ["", f"- 초안 ok {tot['notices']}건 · 판정 불가 {tot['not_ok']}건",
              f"- 조건: 같음 {tot['same']} · **다름 {tot['differ']}** · 초안에만 {tot['draft_only']} · 등록에만 {tot['truth_only']}",
              "- 항목별: " + ", ".join(f"{k}/{kind} {n}" for (k, kind), n in sorted(by_kind.items())), "", "## 다른 값", ""]
    lines += [f"- {nid} {key}: 초안 {g} / 등록 {t}" for nid, key, g, t in diffs]
    text = "\n".join(lines)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
