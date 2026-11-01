# -*- coding: utf-8 -*-
"""표 추출 평가(docs/09 §19 T5) — src/pdf_tables.py가 공고문 표를 칸 위치까지 맞게 읽는지 등록 공고와 새 공고로 잰다.

    python tools/eval_tables.py                          # 등록 공고(rules/notices) 전부
    python tools/eval_tables.py --extra ../sample_new    # + 등록 안 된 새 공고 폴더(기준표 대조·일관성만)
    python tools/eval_tables.py --report docs/eval-tables.md

지표
- 틀린 칸(최우선, 0이어야 함): 등록 기준표 묶음(기준·연도 — 가구원수별 100% 기준액 × 비율)으로 보면 제 칸과 맞지 않고
  같은 쪽의 다른 (가구원수, 비율) 칸 값과 맞는 칸 = 위치를 잘못 읽은 칸
- 설명 안 됨: 어느 칸으로도 맞지 않는 금액 — 다른 연도·기준의 표면 정상, 같은 연도 쪽이면 따로 센다(살펴볼 대상)
- 교차 실패(0이어야 함): 표에서 읽은 금액이 그 쪽 pypdf 텍스트에 없음
- 방법 충돌: 선(lines)과 글자 좌표(words)가 같은 칸에 다른 금액 — 충돌한 칸은 쓰지 않는다
- 기준표 복원율(등록 공고): 그 공고가 인용하는 기준표(cited_pages)의 칸 중 표 영역에 금액이 보이는 칸을, 표 읽기가
  같은 (가구원수, 비율) 위치로 찾은 비율
- 결정표 금액 수집률(등록 공고): 규칙 결정표의 100만 원 이상 금액 중 원문 쪽에 있는 것을 표 칸에서 찾은 비율(위치는 보지 않음)
- 일관성: 같은 가구원수 칸들이 한 기준액 × 비율로 설명되는 격자 / 안 되는 격자(버림) / 확인 불가
"""
import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src")]

import pdf_tables as P  # noqa: E402
import source_verify as sv  # noqa: E402
from notice_candidates import income_pages  # noqa: E402
from rule_data import notice_ids  # noqa: E402


def _amounts(obj):
    if isinstance(obj, bool):
        return
    if isinstance(obj, int) and obj >= 1_000_000:
        yield obj
    elif isinstance(obj, (list, tuple)):
        for x in obj:
            yield from _amounts(x)


def registered_truth(refs):
    """nid → {'pages': 후보 쪽, 'ref_pages': {기준표: [쪽]}, 'decision': {쪽: {금액}}}."""
    out = {}
    for nid in notice_ids():
        doc = sv.notice_doc(nid)
        blob = json.dumps(doc, ensure_ascii=False)
        ref_pages = {rid: ref["cited_pages"][nid] for rid, ref in refs.items()
                     if nid in ref.get("cited_pages", {}) and f'"{rid}"' in blob}
        decision = {}
        for t in doc.get("tables", {}).values():
            page = t.get("source", {}).get("page")
            if page:
                decision.setdefault(page, set()).update(a for row in t.get("rows", []) for a in _amounts(row.get("out")))
        out[nid] = {"ref_pages": ref_pages, "decision": decision}
    return out


def evaluate_pdf(path, truth=None, refs=None, fams=None):
    pages = sv.extract_pages(path)
    cand = {x["page"] for x in income_pages(pages)}
    if truth:
        cand |= {p for ps in truth["ref_pages"].values() for p in ps} | set(truth["decision"])
    t0 = time.time()
    tables = P.read_tables(path, cand)
    secs = time.time() - t0
    r = Counter(pages=len(cand), tables=sum(1 for t in tables if t.method == "lines"))
    grids = [P.income_cells(t) for t in tables]
    for g in grids:
        r["dropped"] += g.dropped
        if g.cells:
            state = P.consistent(g)
            r["grid_ok" if state else "grid_bad" if state is False else "grid_unchecked"] += 1
    cells, conflicts = P.merge(grids)
    r["cells"], r["conflicts"] = len(cells), conflicts
    r["cross_fail"] = sum(len(P.cross_check(P.Grid(c.page, c.method, [c]), pages[c.page - 1])) for c in cells)
    wrong = []
    by_page = {}
    for c in cells:
        by_page.setdefault(c.page, []).append(c)
    for cs in by_page.values():
        cmp = P.compare_reference(cs, fams)
        r["ref_same"] += len(cmp["same"])
        r["wrong"] += len(cmp["misplaced"])
        wrong += cmp["misplaced"]
        key = "unexplained" if len(cmp["same"]) >= len(cs) / 2 else "other_year"   # 같은 연도 쪽에서 설명 안 되는 칸은 따로
        r[key] += len(cmp["other"])
    if truth:
        # 기준표 복원율: 표의 금액 줄에 실린 기준표 금액
        money_cells = {}       # 금액 칸이 두 개 이상인 줄의 금액(표 칸 안 문장 속 금액은 표 읽기 대상이 아님 — 청년매입 순위표)
        for t in tables:
            for row in t.rows:
                found = [P.money(c) for c in row if P.money(c)]
                if len(found) >= 2:
                    money_cells.setdefault(t.page, set()).update(found)
        found = {(c.page, c.size, c.ratio, c.amount) for c in cells}
        for rid, cited in truth["ref_pages"].items():
            for size, row in refs[rid]["table"].items():
                for ratio, v in row.items():
                    where = [p for p in cited if v in money_cells.get(p, set())]
                    if not where:
                        continue
                    r["ref_expected"] += 1
                    r["ref_located"] += any((p, int(size), int(ratio), v) in found for p in where)
        any_cell = {}          # 결정표 금액은 한 줄에 하나뿐인 칸(자산 한도 등)도 센다
        for t in tables:
            any_cell.setdefault(t.page, set()).update(P.money(c) for row in t.rows for c in row if P.money(c))
        for pg, amounts in truth["decision"].items():
            for a in amounts:
                if f"{a:,}" in pages[pg - 1]:
                    r["dec_expected"] += 1
                    r["dec_found"] += a in any_cell.get(pg, set())
    return r, secs, wrong


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", action="append", default=[], help="등록 안 된 새 공고 PDF 폴더")
    ap.add_argument("--only", nargs="*", help="이 공고 ID만(등록 공고)")
    ap.add_argument("--report", help="마크다운 보고서 저장 경로")
    a = ap.parse_args()
    refs = P.load_references()
    fams = P.families(refs)
    truth = registered_truth(refs)
    rows, total, secs_all, wrong_all = [], Counter(), 0.0, []
    registered_sha = set()
    for nid in a.only or notice_ids():
        path = sv.pdf_path(nid)
        registered_sha.add(hashlib.sha256(path.read_bytes()).hexdigest())
        r, secs, wrong = evaluate_pdf(path, truth[nid], refs, fams)
        rows.append(("등록", nid, path.name, r, secs))
        total.update(r)
        secs_all += secs
        wrong_all += [(nid, c) for c in wrong]
    for d in a.extra:
        for path in sorted(Path(d).glob("*.pdf")):
            if hashlib.sha256(path.read_bytes()).hexdigest() in registered_sha:
                continue                                   # 등록 공고와 같은 파일
            r, secs, wrong = evaluate_pdf(path, None, refs, fams)
            rows.append(("새 공고", "-", path.name, r, secs))
            total.update(r)
            secs_all += secs
            wrong_all += [(path.name, c) for c in wrong]

    lines = ["| 구분 | 공고 | 쪽 | 칸 | 기준표로 맞음 | 다른 연도·기준 | 같은 연도인데 설명 안 됨 | **틀린 칸** | 교차 실패 | 방법 충돌 | 복원율 | 결정표 금액 | 격자 일관(○/✗/?) | 초 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for kind, nid, name, r, secs in rows:
        label = nid if nid != "-" else name[:28]
        lines.append(f"| {kind} | {label} | {r['pages']} | {r['cells']} | {r['ref_same']} | {r['other_year']} | {r['unexplained']} | "
                     f"{r['wrong']} | {r['cross_fail']} | {r['conflicts']} | {pct(r['ref_located'], r['ref_expected'])} | "
                     f"{pct(r['dec_found'], r['dec_expected'])} | {r['grid_ok']}/{r['grid_bad']}/{r['grid_unchecked']} | {secs:.1f} |")
    summary = [
        f"- 공고 {len(rows)}건(등록 {sum(1 for x in rows if x[0] == '등록')} · 새 공고 {sum(1 for x in rows if x[0] != '등록')}), "
        f"표가 있는 쪽 {total['pages']}쪽, 표 읽기 {secs_all:.1f}초(쪽당 {secs_all / max(total['pages'], 1):.2f}초)",
        f"- 읽은 소득 기준표 칸 {total['cells']} — 등록 기준표(기준·연도 묶음)로 맞음 {total['ref_same']}, 다른 연도·기준의 표 {total['other_year']}, "
        f"같은 연도 쪽인데 설명 안 됨 {total['unexplained']}",
        f"- **틀린 칸 {total['wrong']}**, 교차 실패 {total['cross_fail']}, 방법 충돌 {total['conflicts']}, 가산 폭을 못 풀어 버린 칸 {total['dropped']}",
        f"- 기준표 복원율(등록) {pct(total['ref_located'], total['ref_expected'])} ({total['ref_located']}/{total['ref_expected']}), "
        f"결정표 금액 수집률(등록) {pct(total['dec_found'], total['dec_expected'])} ({total['dec_found']}/{total['dec_expected']})",
        f"- 격자 일관성: 맞음 {total['grid_ok']} / 안 맞음(버림) {total['grid_bad']} / 확인 불가 {total['grid_unchecked']}",
    ]
    out = "\n".join(summary) + "\n\n" + "\n".join(lines)
    if wrong_all:
        out += "\n\n틀린 칸:\n" + "\n".join(f"- {w}: p.{c.page} {c.size}인 {c.ratio}% {c.amount:,} ({c.method})" for w, c in wrong_all)
    print(out)
    if a.report:
        head = ("# 표 칸 위치 읽기 평가(docs/09 §19 T5)\n\n"
                f"`python tools/eval_tables.py{' --extra <새 공고 폴더>' if a.extra else ''}` — 지표 정의는 도구 머리말.\n\n")
        Path(a.report).write_text(head + out + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
