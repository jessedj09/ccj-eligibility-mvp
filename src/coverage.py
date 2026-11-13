# -*- coding: utf-8 -*-
"""coverage.py — 확정 판정 범위 관리(흥신소 주 흐름, docs/12 묶음 A, 2026-11-13).

- pending(rows, analyzed): 분석 대기 공고 — 판정 틀은 있는데 공고문 분석 전(예비 판정으로만 보이는) 마감 안 된 공고.
  접수 시작이 가까운 순 → 분석 요청이 많은 순. 운영자가 공고문을 내려받아 재판소에 올리면 모두에게 확정 판정으로 바뀐다.
- coverage(rows, analyzed): 확정 판정 범위 = (등록 + 분석된) / (등록 + 판정 틀 있음) — 접수 시작일 기준 80%가 목표(PRD 11절).
- check_preview(row, d): 공고문이 분석된 수집 공고에서, 대표 공고 기준 예비 판정과 그 공고문 확정 판정을 같은 골든 입력으로 비교 —
  놓침(예비 '어려움' → 확정 '지원 가능')이 1건이라도 있으면 그 판정 틀의 '어려움'을 멈춘다(store.preview_stopped, 다시 켜는 것은 운영자).
- summary_markdown(...): 수집 예약 작업의 GitHub 작업 요약.

판정 로직은 없다(live_judge·grading·find를 부른다). 개인정보 없음.
"""
from collections import Counter
from datetime import date
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import live_judge as J
import live_notices as LN

CHECK_LIMIT = 120          # 계층마다 골든 입력 수(수집 작업 안에서 — 공고 하나 수 초)


def _analyzed_sha(row: Dict, analyzed: List[Dict], peers: Optional[List[Dict]] = None) -> Optional[str]:
    import find
    return find.match_analyzed(row, analyzed, peers) if row.get("template") else None


def pending(rows: Iterable[Dict], analyzed: List[Dict]) -> List[Dict]:
    """같은 공고를 묶은 마감 안 된 행 → 분석 대기 공고(판정 틀 있음 · 등록 아님 · 분석된 업로드와 이어지지 않음)."""
    rows = list(rows)
    out = [r for r in rows if r.get("route") == LN.TEMPLATE and not r.get("registered_id") and not _analyzed_sha(r, analyzed, rows)]
    return sorted(out, key=lambda r: (str(r.get("window_start") or "9999"), -(r.get("request_count") or 0), r["title"]))


def coverage(rows: Iterable[Dict], analyzed: List[Dict]) -> Dict[str, int]:
    c = Counter()
    rows = list(rows)
    for r in rows:
        if r.get("route") == LN.REGISTERED or r.get("registered_id"):
            c["registered"] += 1
        elif r.get("route") == LN.TEMPLATE:
            c["analyzed" if _analyzed_sha(r, analyzed, rows) else "pending"] += 1
        else:
            c["unsupported"] += 1
    target = c["registered"] + c["analyzed"] + c["pending"]
    return {**c, "target": target, "confirmed": c["registered"] + c["analyzed"],
            "pct": round(100 * (c["registered"] + c["analyzed"]) / target) if target else 0}


def check_preview(row: Dict, d, limit: int = CHECK_LIMIT) -> Optional[Tuple[str, Counter]]:
    """분석된 수집 공고 하나 — (대표 공고의 판정 틀, Counter(compared·missed·likely_ok·likely_wrong)). 대표 공고가 없으면 None.
    입력은 대표 공고 계층의 골든 입력(tests/golden_cases.py — 경계값·조합 위주)."""
    import sys
    from pathlib import Path
    tests = str(Path(__file__).resolve().parent.parent / "tests")
    if tests not in sys.path:
        sys.path.insert(0, tests)
    import golden_cases as gc
    import grading
    from find import registered
    from notices_data import ALL_NOTICES
    regs, index = registered()
    announced = date.fromisoformat(str(row["announced"])[:10]) if row.get("announced") else None
    rep = J.pick_representative(row["template"], row.get("issuer"), row.get("program"), announced, regs)
    if rep is None or d is None or d.notice is None:
        return None
    rep_notice = ALL_NOTICES[rep.notice_id]
    c = Counter()
    for nid, layer in [g for g in gc.GROUPS if g[0] == rep.notice_id]:
        target_layer = J.match_layer(layer, d.notice)
        if target_layer is None:
            continue
        for i, (_n, _l, p) in enumerate(gc.cases(only=[(nid, layer)])):
            if i >= limit:
                break
            truth = grading.judge(d, p, target_layer)[0].verdict
            if truth == "NOT_OFFERED":
                continue
            pv = J.preview_layer(p, layer, rep_notice, rep.template, index, announced).outcome
            c["compared"] += 1
            if pv == J.UNLIKELY and truth == "ELIGIBLE":
                c["missed"] += 1
            elif pv == J.LIKELY:
                c["likely_ok" if truth == "ELIGIBLE" else "likely_wrong"] += 1
    return rep.template, c


def summary_markdown(cov: Dict[str, int], waiting: List[Dict], checks: List[Tuple[str, str, Counter]],
                     stopped: Iterable[str], today: date, autos=()) -> str:
    """수집 예약 작업 요약(GitHub 작업 요약 — $GITHUB_STEP_SUMMARY)."""
    lines = [f"## 공고 수집 {today.isoformat()}", "",
             f"**확정 판정 범위 {cov['pct']}%** — 등록 {cov.get('registered', 0)} + 분석 {cov.get('analyzed', 0)} / "
             f"판정 대상 {cov['target']}(분석 대기 {cov.get('pending', 0)}, 판정 안 하는 사업 {cov.get('unsupported', 0)})", ""]
    if autos:
        lines += ["### LH 공고문 자동 분석(이번 수집)", "", "| 공고 | 결과 | 등급 | 크기 | 걸린 시간 |", "|---|---|---|---|---|"]
        for r, rec in autos:
            lines.append(f"| {LN.clean_title(r['title'])[:50]} | {rec.get('result')} | {rec.get('grade') or ''} | "
                         f"{rec.get('kb', '?')}KB | {rec.get('seconds')}초 |")
        lines.append("")
    if waiting:
        lines += ["### 분석 대기 공고 — LH는 수집 작업이 자동 분석(한 번에 8건), 그 밖은 공고문을 재판소에 올리면 모두에게 확정 판정", "",
                  "| 접수 | 기관 | 사업 | 공고 | 분석 요청 | 공식 공고 | 공고문 |", "|---|---|---|---|---|---|---|"]
        for r in waiting:
            when = f"{r.get('window_start') or '?'}~{r.get('window_end') or '?'}"
            dk = r.get("detail_key") or {}
            auto = (dk.get("auto") or {}).get("result")
            pdf = f"[PDF]({dk['pdf']})" + (f" ({auto})" if auto else "") if dk.get("pdf") else ""
            lines.append(f"| {when} | {r.get('issuer') or ''} | {r.get('program') or ''} | {LN.clean_title(r['title'])[:60]} | "
                         f"{r.get('request_count') or 0} | {('[링크](' + r['url'] + ')') if r.get('url') else ''} | {pdf} |")
        lines.append("")
    if checks:
        lines += ["### 예비 판정 감시(새로 분석된 공고)", "", "| 공고 | 판정 틀 | 비교 | 놓침 | 가능성 있음 맞음/헛걸음 |",
                  "|---|---|---|---|---|"]
        for title, tname, c in checks:
            lines.append(f"| {LN.clean_title(title)[:50]} | {tname} | {c['compared']} | {c['missed']} | {c['likely_ok']}/{c['likely_wrong']} |")
        lines.append("")
    stopped = sorted(stopped)
    if stopped:
        lines += [f"**예비 '어려움'을 멈춘 판정 틀**: {', '.join(stopped)} — 원인 확인 뒤 `python tools/preview_health.py --resume <틀>`", ""]
    return "\n".join(lines)
