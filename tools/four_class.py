# -*- coding: utf-8 -*-
"""오류 4분류 집계(2026-11-09 피드백 1순위) — 시스템 판정을 기준 판정과 맞대어 화면 표시 기준으로 나눈다.

    ① 틀린 지원 가능      시스템 '지원 가능'인데 기준은 '지원 불가'·'해당 없음'        (헛걸음·부적격)
    ② 틀린 지원 불가      시스템 '지원 불가'·'해당 없음'인데 기준은 '지원 가능'        (신청 기회를 놓침)
    ③ 보류할 것을 확정    기준은 '보류'(정보 부족·해석이 갈림)인데 시스템이 확정
    ④ 불필요한 보류       기준은 확정인데 시스템이 '보류'                              (안전하지만 사람 몫)
    + 같음 · 판정 없음(시스템이 판정하지 않음) · 그 밖의 확정 불일치('지원 불가' ↔ '해당 없음')

세 가지 기준(docs/13-beta-readiness.md 1-1절):

    python tools/four_class.py auto [--limit 200] [--nid N12 …] [--out 보고서.md]
        자동 분석(등록 공고를 형제·조항 장부에서 자기 제외해 처음 보는 공고처럼) ↔ 등록 규칙, 골든 입력.
        '자동 = 사람 등록'을 잰다 — 추출 규칙이 이 공고들을 보며 다듬어졌으므로 낙관적이고, 둘이 같이 틀리면 못 잡는다.
    python tools/four_class.py unseen [--limit N] [--out …]
        등록 전에 얼린 초안(docs/draft-checks/*.draft.json — 개발에 쓰지 않은 공고) ↔ 등록 규칙. 초안이 판정하지 않은
        (차단·미지원) 스냅샷은 '판정 없음'으로만 세고 '검증 근거 공고 수'에 넣지 않는다.
    python tools/four_class.py worksheet [--show-cases]
        엔진(등록 규칙)·자동 분석 ↔ 사람(원문만 보고 채운 독립 검증 사례 docs/independent-validation-cases.json,
        답은 docs/independent-validation-answers.json). 채운 사례만 대조한다. '확인필요'는 보류로 본다. --show-cases는 다 채운 뒤에만(먼저 보면 독립 검증이 아니다).

①②③이 하나라도 있으면 종료코드 1.
"""
import argparse
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools"), str(ROOT / "tests")]

C1, C2, C3, C4 = "c1_wrong_eligible", "c2_wrong_ineligible", "c3_confirmed_should_hold", "c4_needless_hold"
SAME, NOT_JUDGED, OTHER = "same", "not_judged", "other_confirmed"
ORDER = (SAME, C1, C2, C3, C4, OTHER, NOT_JUDGED)
LABEL = {SAME: "같음", C1: "① 틀린 지원 가능", C2: "② 틀린 지원 불가", C3: "③ 보류할 것을 확정", C4: "④ 불필요한 보류",
         OTHER: "그 밖의 확정 불일치", NOT_JUDGED: "판정 없음"}
ERRORS = (C1, C2, C3)

GROUP = {"ELIGIBLE": "가능", "INELIGIBLE": "불가", "NOT_OFFERED": "해당 없음",
         "NEEDS_INFO": "보류", "MANUAL_REVIEW": "보류", "확인필요": "보류"}


def group(verdict: Optional[str]) -> Optional[str]:
    """엔진 5상태(또는 워크시트 답 '확인필요') → 화면 표시 갈래. None = 판정하지 않음."""
    if verdict is None:
        return None
    if verdict not in GROUP:
        raise ValueError(f"알 수 없는 판정: {verdict!r}")
    return GROUP[verdict]


def classify(system: Optional[str], reference: str) -> str:
    """system: 시스템 판정(None = 판정하지 않음), reference: 기준 판정. → 4분류 키."""
    s, r = group(system), group(reference)
    if s is None:
        return NOT_JUDGED
    if s == r:
        return SAME
    if s == "보류":
        return C4
    if r == "보류":
        return C3
    if s == "가능":
        return C1
    if r == "가능":
        return C2
    return OTHER


def summary_line(c: Counter, notices: int, dev_unused: int, what: str) -> str:
    """10-31 피드백 10항의 보고 형식 — 분모와 평가 조건을 붙인다."""
    n = sum(c.values())
    return (f"평가 공고 {notices}건, {what} {n:,}건에서 ① 틀린 지원 가능 {c[C1]:,} · ② 틀린 지원 불가 {c[C2]:,} · "
            f"③ 보류할 것을 확정 {c[C3]:,} · ④ 불필요한 보류 {c[C4]:,} · 같음 {c[SAME]:,} · 판정 없음 {c[NOT_JUDGED]:,} · "
            f"그 밖 {c[OTHER]:,}. 개발에 사용하지 않은 공고 {dev_unused}건.")


def table(rows: Dict[str, Counter]) -> list:
    out = ["| 구분 | 건수 | " + " | ".join(LABEL[k] for k in ORDER) + " |", "|---|---|" + "---|" * len(ORDER)]
    for name, c in rows.items():
        n = sum(c.values()) or 1
        out.append(f"| {name} | {sum(c.values()):,} | " + " | ".join(
            f"{c[k]:,} ({c[k] / n:.1%})" if c[k] else "0" for k in ORDER) + " |")
    return out


# ------------------------------------------------------------------ auto: 자기 제외 자동 분석 ↔ 등록 규칙
def auto(nids: Iterable[str], limit: int):
    import draft
    import golden_cases as gc
    import grading
    import source_verify as sv
    import templates as T
    from rule_data import load_notice
    from rule_engine import evaluate

    per: Dict[str, Counter] = defaultdict(Counter)
    notices = 0
    for nid in nids:
        t = T.gold_sheet(nid)["template"]
        d = draft.make_draft(sv.pdf_path(nid).read_bytes(), only=None, pages=sv.pdf_pages(nid), exclude=nid)
        reg = load_notice(nid)
        notices += 1
        for _, layer in [g for g in gc.GROUPS if g[0] == nid]:
            for i, (_, _, p) in enumerate(gc.cases(only=[(nid, layer)])):
                if i >= limit:
                    break
                ref = evaluate(p, reg, layer).verdict
                if d.status != draft.OK or grading.offered(d, layer) is None:
                    mine = None
                elif not grading.offered(d, layer):
                    mine = "NOT_OFFERED"
                else:
                    mine = grading.judge(d, p, layer)[0].verdict
                per[t][classify(mine, ref)] += 1
        print(nid, t, dict(per[t]), file=sys.stderr, flush=True)
    return per, notices


# ------------------------------------------------------------------ unseen: 등록 전에 얼린 초안 ↔ 등록 규칙
def registered_on(nid: str) -> Optional[str]:
    """그 공고 규칙 파일이 저장소에 처음 들어온 날(YYYY-MM-DD, git). 알 수 없으면 None."""
    import subprocess
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%aI", "--", f"rules/notices/{nid}.json"],
                             cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return out[-1][:10] if out else None


def frozen_after_registration(snap: Dict, nid: str) -> bool:
    """초안을 등록한 날보다 뒤에 얼렸으면 처음 보는 공고가 아니다(예: 이미 등록된 공고 파일로 다시 얼린 스냅샷).
    같은 날은 순서를 알 수 없어 처음 보는 공고로 둔다."""
    reg = registered_on(nid)
    created = (snap.get("created") or "")[:10]
    return bool(reg and created and created > reg)


def unseen(limit: Optional[int]):
    import draft
    import golden_cases as gc
    import templates as T
    from notice_candidates import registered_as
    from rule_data import load_notice
    from rule_engine import evaluate

    per: Dict[str, Counter] = defaultdict(Counter)
    judged, blocked, late = defaultdict(set), defaultdict(set), defaultdict(set)
    sheet = set(T.sheet_ids())
    # 같은 공고를 여러 번 얼린 경우(판정 틀이 생기기 전·후)가 있다 — 공고마다 하나만 쓴다: 판정한 스냅샷 중 가장 먼저 만든 것,
    # 판정한 것이 없으면 가장 먼저 만든 것('판정 없음'으로 한 번만 센다).
    by_nid: Dict[str, list] = defaultdict(list)
    for f in sorted(glob.glob(str(ROOT / "docs" / "draft-checks" / "*.draft.json"))):
        snap = json.loads(Path(f).read_text(encoding="utf-8"))
        nid = registered_as(snap.get("sha256", "")) if snap.get("sha256") else None
        if nid:                                        # 아직 등록 안 된 공고는 비교할 기준이 없다
            by_nid[nid].append(snap)
    for nid, snaps in sorted(by_nid.items()):
        ok = [s for s in snaps if not frozen_after_registration(s, nid)]
        if not ok:                                     # 등록 뒤에 얼린 것뿐 — 처음 보는 공고 검증이 아니다(세지 않음)
            t = T.gold_sheet(nid)["template"] if nid in sheet else (snaps[0].get("template") or "?")
            late[t].add(nid)
            continue
        snaps = ok
        snaps.sort(key=lambda s: (s.get("status") != draft.OK, s.get("created") or ""))
        snap = snaps[0]
        layers = [layer for n, layer in gc.GROUPS if n == nid]
        if not layers:
            continue
        d = draft.from_snapshot(snap)
        reg = load_notice(nid)
        t = T.gold_sheet(nid)["template"] if nid in sheet else (snap.get("template") or "?")
        (judged if d.status == draft.OK else blocked)[t].add(nid)
        for layer in layers:
            for i, (_, _, p) in enumerate(gc.cases(only=[(nid, layer)])):
                if limit is not None and i >= limit:
                    break
                ref = evaluate(p, reg, layer).verdict
                mine = (draft.evaluate_draft(d, p, layer)[0].verdict
                        if d.status == draft.OK and layer in d.notice.layers else None)
                per[t][classify(mine, ref)] += 1
    return per, judged, blocked, late


# ------------------------------------------------------------------ worksheet: 엔진·자동 분석 ↔ 사람
CASES = ROOT / "docs" / "independent-validation-cases.json"
# 사람 답은 사례 파일(입력만 — test_b5)과 따로 둔다: {"answers": {"<id>": {"verdict": "...", "page": "...", "note": "..."}}}
ANSWERS = ROOT / "docs" / "independent-validation-answers.json"


def with_answers(cases, answers_path: Path = ANSWERS):
    """사례 목록에 답 파일의 답을 합친 복사본(답 파일이 없으면 그대로). 사례 파일 안의 답이 있으면 그것이 먼저다."""
    if not Path(answers_path).exists():
        return cases
    ans = json.loads(Path(answers_path).read_text(encoding="utf-8")).get("answers", {})
    out = []
    for c in cases:
        a = ans.get(str(c["id"]))
        if a and not (c.get("user_verdict") or "").strip():
            c = dict(c, user_verdict=a.get("verdict", ""), user_page=a.get("page", ""), user_note=a.get("note", ""))
        out.append(c)
    return out


def engine_verdict(case: Dict) -> str:
    from profile_io import household_from_dict
    from rule_data import load_notice
    from rule_engine import evaluate
    p = household_from_dict(dict(case["profile"], profile_id=f"W{case['id']}"))
    return evaluate(p, load_notice(case["notice"]), case["layer"]).verdict


def auto_verdict(case: Dict, _cache={}) -> Optional[str]:
    """그 공고를 처음 보는 공고처럼(자기 제외) 자동 분석했을 때의 화면 판정. 템플릿이 없는 공고는 None."""
    import draft
    import grading
    import source_verify as sv
    import templates as T
    from profile_io import household_from_dict
    nid = case["notice"]
    if nid not in T.sheet_ids():
        return None
    if nid not in _cache:
        _cache[nid] = draft.make_draft(sv.pdf_path(nid).read_bytes(), only=None, pages=sv.pdf_pages(nid), exclude=nid)
    d = _cache[nid]
    if d.status != draft.OK or grading.offered(d, case["layer"]) is None:
        return None
    if not grading.offered(d, case["layer"]):
        return "NOT_OFFERED"
    p = household_from_dict(dict(case["profile"], profile_id=f"W{case['id']}"))
    return grading.judge(d, p, case["layer"])[0].verdict


def worksheet(cases, with_auto: bool = True):
    filled = [c for c in cases if (c.get("user_verdict") or "").strip()]
    rows, eng, aut = [], Counter(), Counter()
    for c in filled:
        user = c["user_verdict"].strip()
        e = engine_verdict(c)
        a = auto_verdict(c) if with_auto else None
        ke, ka = classify(e, user), (classify(a, user) if with_auto else None)
        eng[ke] += 1
        if with_auto:
            aut[ka] += 1
        rows.append(dict(id=c["id"], notice=c["notice"], layer=c["layer"], user=user, user_page=c.get("user_page", ""),
                         engine=e, auto=a, engine_class=ke, auto_class=ka, memo=c.get("memo", "")))
    return dict(total=len(cases), filled=len(filled), engine=eng, auto=aut, rows=rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="mode", required=True)
    pa = sub.add_parser("auto")
    pa.add_argument("--limit", type=int, default=200, help="계층마다 골든 입력 앞 N건")
    pa.add_argument("--nid", nargs="*")
    pa.add_argument("--out")
    pu = sub.add_parser("unseen")
    pu.add_argument("--limit", type=int)
    pu.add_argument("--out")
    pw = sub.add_parser("worksheet")
    pw.add_argument("--show-cases", action="store_true", help="사례별 엔진·자동 분석 판정(작성자가 다 채운 뒤에만)")
    pw.add_argument("--no-auto", action="store_true", help="자동 분석 대조는 빼고 엔진만(빠름)")
    a = ap.parse_args(argv)

    if a.mode == "auto":
        import templates as T
        per, notices = auto(a.nid or T.sheet_ids(), a.limit)
        total = sum(per.values(), Counter())
        lines = ["# 오류 4분류 — 자동 분석(자기 제외) ↔ 등록 규칙", "",
                 "> " + summary_line(total, notices, 0, "가상 신청자(골든 입력)") +
                 " 추출 규칙이 이 공고들을 보며 다듬어졌으므로 낙관적인 값이다.", ""]
        lines += table(dict(sorted(per.items())) | {"**합계**": total})
    elif a.mode == "unseen":
        per, judged, blocked, late = unseen(a.limit)
        total = sum(per.values(), Counter())
        k = sum(len(v) for v in judged.values())
        lines = ["# 오류 4분류 — 등록 전에 얼린 초안(처음 보는 공고) ↔ 등록 규칙", "",
                 "> " + summary_line(total, k + sum(len(v) for v in blocked.values()), k, "가상 신청자(골든 입력)") +
                 " 초안이 판정하지 않은(차단·미지원) 공고는 '판정 없음'으로만 세고 개발에 안 쓴 공고 수에서 뺐다.", ""]
        lines += table(dict(sorted(per.items())) | {"**합계**": total})
        lines += ["", "| 사업 | 초안이 판정한 공고 | 초안이 판정 안 함(검증 근거 아님) | 등록 뒤에 얼림(세지 않음) |", "|---|---|---|---|"]
        for t in sorted(set(judged) | set(blocked) | set(late)):
            lines.append(f"| {t} | {', '.join(sorted(judged[t])) or '-'} | {', '.join(sorted(blocked[t])) or '-'} | "
                         f"{', '.join(sorted(late[t])) or '-'} |")
    else:
        cases = with_answers(json.loads(CASES.read_text(encoding="utf-8"))["cases"])
        res = worksheet(cases, with_auto=not a.no_auto)
        total = res["engine"] + res["auto"]
        lines = [f"# 오류 4분류 — 사람(독립 검증 사례) 기준", "",
                 f"사례 {res['total']}건 중 채운 {res['filled']}건.", ""]
        lines += table({"엔진(등록 규칙)": res["engine"]} | ({} if a.no_auto else {"자동 분석(자기 제외)": res["auto"]}))
        lines += ["", "다른 사례(① 엔진 오류 ② 작성 오독 ③ 원문 해석 갈림 중 하나로 분류해 기록):"]
        for r in res["rows"]:
            if r["engine_class"] != SAME or (r["auto_class"] not in (SAME, None)):
                lines.append(f"- #{r['id']} {r['notice']}/{r['layer']}: 사람 {r['user']}(p.{r['user_page'] or '?'}) · "
                             f"엔진 {r['engine']} [{LABEL[r['engine_class']]}]"
                             + ("" if a.no_auto else f" · 자동 분석 {r['auto']} [{LABEL[r['auto_class']]}]")
                             + f" — {r['memo']}")
        if a.show_cases:
            lines += ["", "사례별:"] + [f"- #{r['id']}: 엔진 {r['engine']} · 자동 분석 {r['auto']}" for r in res["rows"]]
    text = "\n".join(lines) + "\n"
    if getattr(a, "out", None):
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)
    return 1 if any(total[k] for k in ERRORS) else 0


if __name__ == "__main__":
    sys.exit(main())
