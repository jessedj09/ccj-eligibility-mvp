# -*- coding: utf-8 -*-
"""B2 — 등록 전에 얼려 둔 초안 판정과 정식 등록 후 판정을 같은 골든 입력으로 비교한다(docs/08 2-2절).

    python tools/notice_intake.py <새 공고.pdf> --save-draft       # ① 등록 전: docs/draft-checks/<분석 키>.draft.json
    (docs/08 절차대로 등록 — 골든 입력 DATES·GROUPS까지)
    python tools/draft_compare.py docs/draft-checks/<분석 키>.draft.json [--out docs/draft-checks/<분석 키>.md]   # ②

등록 공고는 스냅샷의 원문 지문(sha256)으로 찾는다(--nid로 지정 가능). 그 공고의 골든 계층마다 같은 가상 신청자를
초안(운영자 미리보기와 같은 판정 — 보류 조건·새 제한 문구로 낮춤)과 등록 규칙으로 판정해, 화면 표시(지원 가능·보류·
지원 불가·해당 없음) 기준으로 나눈다.
- 같음
- 초안이 더 조심 — 초안 '보류', 등록은 확정. 안전하지만 사람이 확인해야 하는 몫(비율만 기록)
- **위험** — 초안이 확정(지원 가능·지원 불가·해당 없음)인데 등록과 다름. 특히 '틀린 지원 가능'. 0건이어야 공개(C1) 근거가 된다.
- 초안 판정 없음 — 초안이 판정할 수 없는 상태(사업 미지원·핵심 빈칸 보류 등). 화면은 판정하지 않는다.
위험이 1건이라도 있으면 종료코드 1.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import draft  # noqa: E402
import golden_cases as gc  # noqa: E402
from display_status import HOLD_GROUP, display  # noqa: E402
from notice_candidates import registered_as  # noqa: E402
from rule_data import load_notice  # noqa: E402
from rule_engine import evaluate  # noqa: E402

SAME, CAUTIOUS, WRONG_ELIGIBLE, WRONG_OTHER, NOT_JUDGED = "same", "cautious", "wrong_eligible", "wrong_other", "not_judged"
DANGER = (WRONG_ELIGIBLE, WRONG_OTHER)
LABEL = {SAME: "같음", CAUTIOUS: "초안이 더 조심", WRONG_ELIGIBLE: "⚠️ 틀린 지원 가능", WRONG_OTHER: "⚠️ 다른 확정 판정",
         NOT_JUDGED: "초안 판정 없음"}
EXAMPLES = 5


def classify(draft_verdict: Optional[str], reg_verdict: str) -> str:
    if draft_verdict is None:
        return NOT_JUDGED
    dg, rg = display(draft_verdict).group, display(reg_verdict).group
    if dg == rg:
        return SAME
    if dg == HOLD_GROUP:
        return CAUTIOUS
    return WRONG_ELIGIBLE if draft_verdict == "ELIGIBLE" else WRONG_OTHER


def _ids(xs: List[str]) -> List[str]:
    """조건 ID에서 공고 접두어를 뗀다(초안 DRAFT-…, 등록 N27-… — 같은 조건끼리 맞대기 위해)."""
    return sorted(x.split("-", 1)[1] if "-" in x else x for x in xs)


def compare(snapshot: Dict, nid: Optional[str] = None, limit: Optional[int] = None) -> Dict:
    d = draft.from_snapshot(snapshot)
    nid = nid or registered_as(snapshot["sha256"])
    if not nid:
        raise SystemExit("스냅샷의 원문이 아직 등록되지 않았습니다 — 등록을 마친 뒤 실행하세요(또는 --nid).")
    layers = [layer for n, layer in gc.GROUPS if n == nid]
    if not layers:
        raise SystemExit(f"{nid}의 골든 입력(tests/golden_cases.py GROUPS)이 없습니다 — 등록 절차를 마친 뒤 실행하세요.")
    reg = load_notice(nid)
    counts: Dict[str, Counter] = {}
    examples: Dict[str, List[Dict]] = {}
    for layer in layers:
        c = counts[layer] = Counter()
        for i, (_, _, p) in enumerate(gc.cases(only=[(nid, layer)])):
            if limit is not None and i >= limit:
                break
            r = evaluate(p, reg, layer)
            dr = draft.evaluate_draft(d, p, layer)[0] if d.status == draft.OK else None
            kind = classify(dr.verdict if dr else None, r.verdict)
            c[kind] += 1
            c["exact"] += bool(dr and dr.verdict == r.verdict)
            if kind in DANGER and len(examples.setdefault(layer, [])) < EXAMPLES:
                examples[layer].append(dict(profile=p.profile_id, draft=dr.verdict, registered=r.verdict,
                                            draft_failed=_ids(dr.failed), registered_failed=_ids(r.failed),
                                            draft_unknown=_ids(dr.unknown), registered_unknown=_ids(r.unknown)))
    return dict(nid=nid, title=reg.title, draft=d, snapshot=snapshot, counts=counts, examples=examples)


def danger_count(res: Dict) -> int:
    return sum(c[k] for c in res["counts"].values() for k in DANGER)


def to_markdown(res: Dict) -> str:
    d, s = res["draft"], res["snapshot"]
    total = Counter()
    for c in res["counts"].values():
        total.update(c)
    n = sum(total[k] for k in LABEL)
    danger = danger_count(res)
    out = [f"# 초안 판정 비교(B2) — {res['nid']} {res['title']}", "",
           f"- 초안 스냅샷: `{s.get('file') or '?'}` (만든 날 {s.get('created') or '?'}, 원문 sha256 `{s['sha256'][:12]}…`)",
           f"- 초안 상태: **{d.status}**" + (f" — {d.reason}" if d.reason else "")
           + f" · 사업 `{d.template}` · 공고일 {d.announcement_date}",
           f"- 초안의 보류 빈칸 {len(d.held_fields)}개 · 찾지 못한 인용문 {len(d.missing)}개 · 기준표 연도 다름 {len(d.stale)}개 · "
           f"새 제한 문구 {len(d.restrictions)}개", "",
           f"## 결과: {'✅ 위험 0건' if not danger else f'❌ 위험 {danger}건'} (가상 신청자 {n:,}명)", "",
           "| 계층 | 신청자 | 같음 | 초안이 더 조심 | ⚠️ 틀린 지원 가능 | ⚠️ 다른 확정 판정 | 초안 판정 없음 | 5상태까지 같음 |",
           "|---|---|---|---|---|---|---|---|"]
    for layer, c in list(res["counts"].items()) + [("**합계**", total)]:
        m = sum(c[k] for k in LABEL)
        pct = lambda k: f"{c[k]:,} ({c[k] / m:.1%})" if m else "0"   # noqa: E731
        out.append(f"| {layer} | {m:,} | {pct(SAME)} | {pct(CAUTIOUS)} | {pct(WRONG_ELIGIBLE)} | {pct(WRONG_OTHER)} | "
                   f"{pct(NOT_JUDGED)} | {pct('exact')} |")
    out += ["", "- **같음**: 화면 표시(지원 가능·보류·지원 불가·해당 없음)가 같음. **초안이 더 조심**: 초안은 '보류', 등록은 확정 —"
            " 안전하지만 사람이 확인해야 하는 몫. **위험**: 초안이 확정인데 등록과 다름 — 0건이어야 한다.", ""]
    held = {layer: ids for layer, ids in s["held_conditions"].items() if ids}
    if held or d.restrictions:
        out.append("## 초안이 판정을 낮춘 원인")
        for layer, ids in held.items():
            out.append(f"- {layer}: 보류 조건 {', '.join(_ids(ids))}")
        for page, text in d.restrictions:
            out.append(f"- 새 제한 문구 p.{page}: {text[:80]}")
        out.append("")
    if res["examples"]:
        out.append("## 위험 사례(계층마다 앞 5건) — 초안 추출·템플릿에 없는 조건을 찾는 출발점")
        for layer, rows in res["examples"].items():
            out.append(f"### {layer}")
            for e in rows:
                out.append(f"- `{e['profile']}` 초안 **{e['draft']}** / 등록 **{e['registered']}** — 불충족 조건: 초안 "
                           f"{e['draft_failed'] or '없음'} · 등록 {e['registered_failed'] or '없음'}"
                           + (f" · 모름: 초안 {e['draft_unknown']} · 등록 {e['registered_unknown']}"
                              if e["draft_unknown"] != e["registered_unknown"] else ""))
        out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("snapshot", help="notice_intake.py --save-draft로 저장한 초안 스냅샷(.draft.json)")
    ap.add_argument("--nid", help="비교할 등록 공고 ID(없으면 원문 지문으로 찾는다)")
    ap.add_argument("--limit", type=int, help="계층마다 골든 입력 앞 N건만(빠른 확인용)")
    ap.add_argument("--out", help="결과를 저장할 .md 경로(없으면 화면에 출력)")
    a = ap.parse_args(argv)
    res = compare(json.loads(Path(a.snapshot).read_text(encoding="utf-8")), a.nid, a.limit)
    md = to_markdown(res)
    if a.out:
        Path(a.out).write_text(md + "\n", encoding="utf-8")
        print("비교 결과:", a.out)
    else:
        print(md)
    return 1 if danger_count(res) else 0


if __name__ == "__main__":
    sys.exit(main())
