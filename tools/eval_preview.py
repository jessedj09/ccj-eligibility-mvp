# -*- coding: utf-8 -*-
"""예비 판정 되짚어 보기(흥신소 주 흐름 ②-1, docs/12 '2단계 재설계').

등록 공고를 판정 틀별 공고일 순으로 놓고, 공고마다 **같은 틀의 앞선 등록 공고를 대표 공고로 삼아** 그 공고의 골든 입력을
예비 판정(src/live_judge.py)한 뒤, 그 공고 자신의 등록 규칙 판정(확정)과 비교한다.

    python tools/eval_preview.py [--limit 400] [--template lh.happy_housing …] [--out docs/eval-preview.md]

- **놓침**: 예비 '어려움'인데 확정 '지원 가능' — 0이어야 한다(있으면 종료코드 1, 틀·조건을 보고).
- 함께 보는 값: 가능성 있음 중 확정 지원 가능 비율(맞음)·확정 지원 불가 비율(헛걸음), 확인 필요 비율, 판정 안 함(대표 공고에 계층 없음).
- 앞선 등록 공고가 없는 공고(틀의 첫 공고·같은 날 공고뿐)는 빼고 건수를 보고한다.
"""
import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools"), str(ROOT / "tests")]

import golden_cases as gc  # noqa: E402
import live_judge as J  # noqa: E402
import templates as T  # noqa: E402
from rule_data import load_notice, notice_ids  # noqa: E402
from rule_engine import evaluate  # noqa: E402

BASE_TEMPLATE = {"N1": "lh.happy_housing", "N2": "lh.happy_housing", "N3": "lh.happy_housing"}
MISS, SOFT_MISS, LIKELY_OK, LIKELY_WRONG, LIKELY_SOFT = "놓침", "어려움→확정 보류", "가능성 있음·맞음", "가능성 있음·헛걸음", "가능성 있음·확정 보류"


def registered():
    out = []
    for nid in notice_ids():
        n = load_notice(nid)
        tname = BASE_TEMPLATE.get(nid) or T.gold_sheet(nid)["template"]
        out.append(J.Registered(nid, tname, n.meta.get("issuer"), n.meta.get("program"), n.announcement_date))
    return out


def classify(preview: str, truth: str) -> str:
    if preview == J.UNLIKELY:
        return MISS if truth == "ELIGIBLE" else (SOFT_MISS if truth in ("NEEDS_INFO", "MANUAL_REVIEW") else "어려움·맞음")
    if preview == J.LIKELY:
        return LIKELY_OK if truth == "ELIGIBLE" else (LIKELY_WRONG if truth == "INELIGIBLE" else LIKELY_SOFT)
    return {J.CHECK: "확인 필요", J.NONE: "판정 안 함"}[preview]


def evaluate_pair(target: J.Registered, rep: J.Registered, limit: int, regs):
    tn, rn = load_notice(target.notice_id), load_notice(rep.notice_id)
    index = J.CommonIndex([r for r in regs if r.notice_id != target.notice_id])    # 처음 보는 공고처럼 — 자기 공고는 뺀다
    c, misses = Counter(), Counter()
    for nid, layer in [g for g in gc.GROUPS if g[0] == target.notice_id]:
        for i, (_, _, p) in enumerate(gc.cases(only=[(nid, layer)])):
            if i >= limit:
                break
            truth = evaluate(p, tn, layer).verdict
            if truth == "NOT_OFFERED":
                continue
            pv = J.preview_layer(p, layer, rn, rep.template, index, tn.announcement_date)
            k = classify(pv.outcome, truth)
            c[k] += 1
            if k == MISS:
                misses[(layer, tuple(sorted(set(pv.fields))))] += 1
    return c, misses


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=400, help="계층마다 골든 입력 수")
    ap.add_argument("--template", nargs="*", help="이 판정 틀만")
    ap.add_argument("--out", help="보고표를 이 파일(마크다운)에")
    a = ap.parse_args(argv)
    regs = registered()
    by_t = defaultdict(list)
    for r in regs:
        by_t[r.template].append(r)
    lines = ["| 판정 틀 | 공고 ← 대표 공고 | 비교 | 놓침 | 어려움→확정 보류 | 가능성 있음(맞음/헛걸음/확정 보류) | 확인 필요 | 판정 안 함 |",
             "|---|---|---|---|---|---|---|---|"]
    total, skipped, all_miss = Counter(), [], []
    for tname in sorted(by_t):
        if a.template and tname not in a.template:
            continue
        for t in sorted(by_t[tname], key=lambda x: (x.announcement_date, x.notice_id)):
            earlier = [r for r in by_t[tname] if r.announcement_date < t.announcement_date]
            rep = J.pick_representative(tname, t.issuer, t.program, t.announcement_date, earlier)
            if rep is None:
                skipped.append(t.notice_id)
                continue
            c, misses = evaluate_pair(t, rep, a.limit, regs)
            total.update(c)
            n = sum(c.values())
            lines.append(f"| {tname} | {t.notice_id} ← {rep.notice_id} | {n} | {c[MISS]} | {c[SOFT_MISS]} | "
                         f"{c[LIKELY_OK]}/{c[LIKELY_WRONG]}/{c[LIKELY_SOFT]} | {c['확인 필요']} | {c['판정 안 함']} |")
            for (layer, fields), k in misses.items():
                all_miss.append(f"{tname} {t.notice_id}←{rep.notice_id} {layer} {list(fields)} ×{k}")
    n = sum(total.values())
    likely = total[LIKELY_OK] + total[LIKELY_WRONG] + total[LIKELY_SOFT]
    pct = lambda x, d: f"{100 * x / d:.1f}%" if d else "-"  # noqa: E731
    report = "\n".join(lines) + "\n\n" + "\n".join([
        f"- 비교 {n:,}건(앞선 등록 공고 없는 공고 {len(skipped)}건 제외: {', '.join(skipped)})",
        f"- **놓침 {total[MISS]}** · 어려움인데 확정 보류 {total[SOFT_MISS]}",
        f"- 가능성 있음 {likely:,}건({pct(likely, n)}) — 확정 지원 가능 {pct(total[LIKELY_OK], likely)} · 헛걸음(확정 지원 불가) "
        f"{pct(total[LIKELY_WRONG], likely)} · 확정 보류 {pct(total[LIKELY_SOFT], likely)}",
        f"- 어려움 {total[MISS] + total[SOFT_MISS] + total['어려움·맞음']:,}건 · 확인 필요 {total['확인 필요']:,}건({pct(total['확인 필요'], n)})"
        f" · 판정 안 함 {total['판정 안 함']:,}건",
    ] + ([f"- 놓침 상세: {m}" for m in all_miss]))
    print(report)
    if a.out:
        Path(a.out).write_text(report + "\n", encoding="utf-8")
    return 1 if total[MISS] else 0


if __name__ == "__main__":
    sys.exit(main())
