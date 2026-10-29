# -*- coding: utf-8 -*-
"""자동 판정 v3 평가 — 등록 공고를 '처음 보는 공고'처럼(형제·조항 장부에서 자기 공고를 빼고) 자동 분석해, 같은 골든 입력으로
등록(검증) 판정과 비교한다(docs/10 §8).

    python tools/eval_v3.py [--limit 400] [--nid N12 …] [--out docs/eval-v3.md]

공고마다: 초안 상태(판정 불가면 이유) · 계층별 등급(자동 확정/일부 확인) · 판정 비교(B2 분류 — 같음 / 초안이 더 조심(=사용자 단위
보류) / 위험 / 판정 없음). **위험(틀린 확정 판정)은 0이어야 한다** — 있으면 종료코드 1.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools"), str(ROOT / "tests")]

import draft  # noqa: E402
import draft_compare as dc  # noqa: E402
import golden_cases as gc  # noqa: E402
import grading  # noqa: E402
import source_verify as sv  # noqa: E402
import templates as T  # noqa: E402
from rule_data import load_notice  # noqa: E402
from rule_engine import evaluate  # noqa: E402


def evaluate_notice(nid: str, limit: int = 400):
    d = draft.make_draft(sv.pdf_path(nid).read_bytes(), only=None, pages=sv.pdf_pages(nid), exclude=nid)
    reg = load_notice(nid)
    c = Counter()
    grades = grading.grades(d) if d.status == draft.OK else {}
    for _, layer in [g for g in gc.GROUPS if g[0] == nid]:
        for i, (_, _, p) in enumerate(gc.cases(only=[(nid, layer)])):
            if i >= limit:
                break
            r = evaluate(p, reg, layer)
            if d.status != draft.OK:
                c[dc.NOT_JUDGED] += 1
                continue
            known = grading.offered(d, layer)
            if known is None:                       # 계층 구성을 읽지 못함 — 판정하지 않는다
                c[dc.NOT_JUDGED] += 1
                continue
            if not known:
                c[dc.classify("NOT_OFFERED", r.verdict)] += 1
                continue
            mine, _checks = grading.judge(d, p, layer)
            c[dc.classify(mine.verdict, r.verdict)] += 1
    return d, grades, c


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=400, help="계층마다 골든 입력 앞 N건")
    ap.add_argument("--nid", nargs="*", help="공고(없으면 템플릿이 있는 등록 공고 전부)")
    ap.add_argument("--out", help="결과 표(.md)")
    a = ap.parse_args(argv)
    nids = a.nid or T.sheet_ids()
    total = Counter()
    lines = ["| 공고 | 사업 | 초안 | 계층 등급 | 같음 | 사용자 단위 보류 | 위험 | 판정 없음 |", "|---|---|---|---|---|---|---|---|"]
    for nid in nids:
        d, grades, c = evaluate_notice(nid, a.limit)
        total += c
        n = sum(c.values()) or 1
        gtxt = ", ".join(f"{grading.GRADE_LABEL[g.grade]} {k}" for k, g in grades.items()) or (d.reason[:40] if d.reason else d.status)
        auto = sum(1 for g in grades.values() if g.grade == grading.AUTO)
        row = (f"| {nid} | {d.template or '-'} | {d.status} | 자동 확정 {auto}/{len(grades)} | {c[dc.SAME] / n:.0%} | "
               f"{c[dc.CAUTIOUS] / n:.0%} | {c[dc.WRONG_ELIGIBLE] + c[dc.WRONG_OTHER]} | {c[dc.NOT_JUDGED] / n:.0%} |")
        lines.append(row)
        print(row, "|", gtxt[:120])
    n = sum(total.values()) or 1
    danger = total[dc.WRONG_ELIGIBLE] + total[dc.WRONG_OTHER]
    summary = (f"합계 {n:,}건: 같음 {total[dc.SAME] / n:.1%} · 사용자 단위 보류 {total[dc.CAUTIOUS] / n:.1%} · "
               f"판정 없음 {total[dc.NOT_JUDGED] / n:.1%} · **위험 {danger}**")
    print(summary)
    if a.out:
        Path(a.out).write_text("# 자동 판정 v3 평가(등록 공고를 처음 보는 공고처럼)\n\n" + "\n".join(lines) + f"\n\n{summary}\n",
                               encoding="utf-8")
    return 1 if danger else 0


if __name__ == "__main__":
    sys.exit(main())
