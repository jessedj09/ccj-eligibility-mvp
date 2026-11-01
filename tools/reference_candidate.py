# -*- coding: utf-8 -*-
"""새 기준표 후보 만들기(운영자 도구, docs/09 §21 T3) — 기준 연도가 바뀐 공고의 소득표를 칸 위치까지 읽어 등록 기준표와 같은
칸 구성의 후보를 만든다. **등록하지 않는다** — 후보 JSON을 원문과 대조한 뒤 rules/reference/에 넣는 것은 운영자 몫(docs/08).

    python tools/reference_candidate.py 새공고.pdf                      # 보고서만
    python tools/reference_candidate.py 공고1.pdf 공고2.pdf --out .cache/reference_candidates   # 여러 공고를 합쳐 후보 JSON 저장
    python tools/reference_candidate.py 새공고.pdf --only income_standard_public
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src")]

import pdf_tables as P  # noqa: E402
import reference_candidates as R  # noqa: E402


def describe(c: R.Candidate) -> str:
    n = sum(len(r) for r in c.table.values())
    change = ", ".join(f"{s}인 {v:+.1%}" for s, v in sorted(c.change.items()))
    lines = [f"[{'후보 완성' if c.ok else '확인 필요'}] {c.ref_id} — 칸 {n}개 찾음 · 없음 {len(c.missing)}개 · 쪽 {c.pages} · "
             f"기준 연도 {c.year or '원문에서 못 찾음'}",
             f"    100% 기준액 변화: {change or '—'}"]
    if c.missing:
        lines.append("    원문에 없는 칸: " + ", ".join(f"{s}인 {r}%" for s, r in c.missing[:12]) + (" …" if len(c.missing) > 12 else ""))
    lines += [f"    문제: {p}" for p in c.problems]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="+")
    ap.add_argument("--only", nargs="*", help="이 등록 기준표만(id)")
    ap.add_argument("--out", help="후보 JSON을 저장할 폴더(기본: 저장 안 함)")
    a = ap.parse_args(argv)
    refs = P.load_references()
    by_ref = {}
    for pdf in a.pdf:
        for c in R.candidates(pdf, refs=refs, only=a.only):
            by_ref.setdefault(c.ref_id, []).append((Path(pdf).name, c))
    if not by_ref:
        print("후보 없음 — 표가 등록 기준표와 같은 연도이거나(설명됨), 등록 기준표 칸 구성과 맞는 표를 찾지 못했습니다.")
        return 0
    for rid, items in by_ref.items():
        cand = items[0][1] if len(items) == 1 else R.combine([c for _, c in items], refs[rid])
        print(describe(cand) + (f"\n    공고 {len(items)}건 합침: {[n for n, _ in items]}" if len(items) > 1 else ""))
        if a.out:
            out = Path(a.out)
            out.mkdir(parents=True, exist_ok=True)
            doc = R.to_reference(cand, refs[rid], " + ".join(n for n, _ in items))
            path = out / f"{doc['id']}.candidate.json"
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            print(f"    저장: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
