# -*- coding: utf-8 -*-
"""미분류 문장 분류(R2) 평가 — docs/09 §23.

    python tools/eval_sentence_check.py [--model gemma4:e2b] [--nid …] [--out …] [--json …]

① 실제 미분류: 등록 공고를 처음 보는 공고처럼 자동 분석한 초안(make_draft exclude=자기)의 미분류 문장을 LLM이 분류 →
   guard 판(a·b·c)마다 '뺄 수 있음' 수, 미분류 때문에 보류였던 계층 중 풀리는 계층 수(보류 조건·새 제한 문구가 없을 때).
   정답 표시: 같은 공고의 등록 장부(ledger_for_registered) 분류 — 등록 규칙이 쓰지 않는 문장이면 '등록 판정과 같음'.
② 끼워 넣기: 규칙이 모르는 새 조건 문장(강한·부드러운 표현, 기준값 있음·없음)을 여러 공고 쪽에 넣어 분류 →
   **놓침(뺄 수 있음으로 판정) 0이어야 채택**. guard 없이 LLM만 보면 몇 개를 놓치는지도 센다.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools"), str(ROOT / "tests")]

import draft  # noqa: E402
import grading  # noqa: E402
import llm_slot  # noqa: E402
import sentence_check as SC  # noqa: E402
import source_verify as sv  # noqa: E402
import templates as T  # noqa: E402

MODES = ("a", "b", "c")
INJECT = [  # test_v3_ledger.NEW_CONDITIONS 4개 + 부드러운 표현·기준값 유무를 섞은 20개
    "• 신청자 본인이 입주자모집공고일 현재 서울특별시에 2년 이상 거주한 자에 한하여 신청 가능",
    "• 주택청약종합저축 가입기간이 6개월 이상인 자",
    "• 만 25세 미만인 자는 신청할 수 없습니다",
    "• 공고일 현재 사업자등록을 한 자는 신청 불가합니다",
    "• 공고일 현재 해당 지역에 주민등록이 되어 있는 분에 한함",
    "• 혼인기간이 5년을 초과한 신혼부부는 제외",
    "• 세대주인 경우에 한하여 신청 가능합니다",
    "• 대학생의 경우 직전 학기 성적이 평균 C 이상인 경우에 한하여 입주할 수 있습니다",
    "- 공고일 현재 근로 중인 경우에 한하여 산업단지근로자로 인정",
    "※ 반려동물을 키우는 세대는 입주 대상에서 제외됩니다",
    "• 본인 명의의 자동차를 보유한 경우 신청 대상에서 제외",
    "• 신청자 및 배우자 모두 무주택이어야 합니다",
    "• 최근 5년 이내 공공임대주택에 입주한 사실이 있는 분은 제외",
    "• 입주자모집공고일 기준 6개월 이상 연속하여 해당 시에 거주하여야 함",
    "• 연령은 만 20세부터 만 35세까지로 한정합니다",
    "• 금융자산 5천만원을 초과하는 경우 입주 대상에서 제외",
    "• 청약통장 납입횟수 12회 이상인 경우에만 해당",
    "• 군복무 중인 자는 신청 자격이 없습니다",
    "• 신혼부부는 자녀가 있는 세대만 해당됩니다",
    "• 장애인 등록증 소지자에 한하여 1층 주택 신청 가능",
    "• 소득이 전혀 없는 세대는 신청 대상이 아닙니다",
    "- 세대주의 직계존속이 주택을 소유한 경우도 무주택으로 보지 않음",
    "• 1인 가구는 전용 40㎡ 이하 주택형만 신청할 수 있음",
    "• 해당 단지 인근 대학에 재학 중인 학생을 우선하며 그 외 대학 재학생은 신청할 수 없음",
]
INJECT_INTO = ["N12", "N24", "N20", "N30", "N49"]


def real_part(slot, nids):
    rows, layers = [], Counter()
    for nid in nids:
        d = draft.make_draft(sv.pdf_path(nid).read_bytes(), only=None, pages=sv.pdf_pages(nid), exclude=nid)
        if d.status != draft.OK or not d.unclassified:
            continue
        import clause_ledger as CL
        reg = {sv.normalize(u): lab for _, u, lab in CL.ledger_for_registered(nid)}
        raw = llm_slot.raw_pages(sv.pdf_path(nid))
        lay = list(d.notice.layers) if d.notice else []
        lab_of = {}
        for page, text in dict.fromkeys(d.unclassified):
            lab = SC.classify(slot, text, SC.context_of(raw, page, text), lay)
            lab_of[(page, text)] = lab
            rows.append({"nid": nid, "template": d.template, "page": page, "text": text, "llm": lab,
                         "reg": reg.get(sv.normalize(text), "?"),
                         **{f"clear_{m}": SC.clears(lab, text, m) for m in MODES}, "llm_only": lab == SC.NOT_CONDITION})
        for layer in lay:
            clauses = grading.layer_clauses(d, layer)
            if not clauses:
                continue
            layers[("held_by_clause",)] += 1
            other = bool(d.held_conditions.get(layer)) or bool(d.restrictions)
            for m in list(MODES) + ["llm_only"]:
                ok = all((SC.clears(lab_of.get((p, t)), t, m) if m != "llm_only" else lab_of.get((p, t)) == SC.NOT_CONDITION)
                         for p, t in clauses)
                if ok:
                    layers[("cleared", m)] += 1
                    if not other:
                        layers[("auto", m)] += 1
        print(f"{nid} 미분류 {len(set(d.unclassified))} {getattr(slot, 'stats', '')}", file=sys.stderr, flush=True)
    return rows, layers


def inject_part(slot, sentences=None, tag="self"):
    rows = []
    for nid in INJECT_INTO:
        raw = llm_slot.raw_pages(sv.pdf_path(nid))
        d_layers = []
        try:
            from rule_data import load_notice
            d_layers = list(load_notice(nid).layers)
        except Exception:  # noqa: BLE001
            pass
        page = max(1, len(raw) // 3)
        for text in (sentences or INJECT):
            ctx = SC.context_of(raw, page, "자격") + "\n" + text            # 끼워 넣은 문장이 주변 원문 안에 있게
            lab = SC.classify(slot, text, ctx, d_layers)
            rows.append({"nid": nid, "tag": tag, "text": text, "llm": lab, **{f"clear_{m}": SC.clears(lab, text, m) for m in MODES},
                         "guard": {m: SC.guard(text, m) for m in MODES}})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemma4:e2b")
    ap.add_argument("--nid", nargs="*")
    ap.add_argument("--out")
    ap.add_argument("--json")
    ap.add_argument("--holdout", help="독립 시험 문장 JSON([[번호, 문장], …] — 패턴을 보지 않은 쪽이 쓴 것)")
    ap.add_argument("--skip-real", action="store_true")
    a = ap.parse_args(argv)
    slot = SC.classifier(a.model)
    inj = inject_part(slot)
    hold = []
    if a.holdout:
        items = json.loads(Path(a.holdout).read_text(encoding="utf-8"))
        num = {t: n for n, t in items}
        hold = inject_part(slot, [t for _, t in items], "holdout")
        for r in hold:
            r["no"] = num[r["text"]]
    real, layers = ([], Counter()) if a.skip_real else real_part(slot, a.nid or T.sheet_ids())
    L = [f"# 미분류 문장 분류(R2) — {slot.name}", "", f"{getattr(slot, 'stats', '')}", "",
         "## 끼워 넣은 새 조건(놓침 = '뺄 수 있음' — 0이어야 채택)", "",
         f"- 문장 {len(INJECT)}개 × 공고 {len(INJECT_INTO)}건 = {len(inj)}",
         f"- LLM '조건 아님': {sum(r['llm'] == SC.NOT_CONDITION for r in inj)} · 답 없음 {sum(r['llm'] is None for r in inj)}",
         f"- guard 없이 LLM만으로 뺄 때 놓침: **{sum(r['llm'] == SC.NOT_CONDITION for r in inj)}**"]
    for m in MODES:
        L.append(f"- 판 {m}: 놓침 **{sum(r['clear_' + m] for r in inj)}** · guard가 막지 못하는 문장(LLM에만 기대는 것) "
                 f"{sum(not SC.guard(t, m) for t in INJECT)}/{len(INJECT)}")
    if hold:
        L += ["", f"## 독립 시험 문장(피드백 검토 세션이 패턴을 보지 않고 씀) {len(hold) // len(INJECT_INTO)}개 × 공고 {len(INJECT_INTO)}건", "",
              f"- LLM만으로 뺄 때 놓침: **{sum(r['llm'] == SC.NOT_CONDITION for r in hold)}** "
              f"(문장 {sorted({r['no'] for r in hold if r['llm'] == SC.NOT_CONDITION})})"]
        for m in MODES:
            missed = sorted({r["no"] for r in hold if r["clear_" + m]})
            L.append(f"- 판 {m}: 놓침 **{sum(r['clear_' + m] for r in hold)}** (문장 {missed})")
    L += ["", "## 실제 미분류 문장(자기 제외 초안)", "",
          f"- 문장 {len(real)}개(공고 {len({r['nid'] for r in real})}건) · LLM '조건 아님' {sum(r['llm_only'] for r in real)} · 답 없음 "
          f"{sum(r['llm'] is None for r in real)}",
          "- 등록 장부 분류: " + ", ".join(f"{k} {v}" for k, v in Counter(r['reg'].split(':')[0] for r in real).most_common())]
    for m in MODES:
        L.append(f"- 판 {m}: 뺄 수 있음 {sum(r['clear_' + m] for r in real)}/{len(real)}")
    n = layers[("held_by_clause",)]
    L += ["", f"## 미분류 때문에 보류였던 계층 {n}개 중 풀리는 계층", "",
          "| 판 | 미분류가 모두 빠짐 | 그중 자동 확정(보류 조건·제한 문구 없음) |", "|---|---|---|"]
    for m in list(MODES) + ["llm_only"]:
        L.append(f"| {m} | {layers[('cleared', m)]} | {layers[('auto', m)]} |")
    L += ["", "## 끼워 넣은 문장 중 LLM이 '조건 아님'으로 본 것", ""]
    L += [f"- {r['nid']} \"{r['text']}\" — 판 a {'놓침' if r['clear_a'] else '막음'} · b {'놓침' if r['clear_b'] else '막음'} · "
          f"c {'놓침' if r['clear_c'] else '막음'}" for r in inj if r["llm"] == SC.NOT_CONDITION]
    L += ["", "## 실제 미분류 중 판 c로 뺄 수 있는 문장(사람 검토용)", ""]
    L += [f"- {r['nid']} p.{r['page']} \"{r['text'][:90]}\"" for r in real if r["clear_c"]]
    text = "\n".join(L)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps({"inject": inj, "holdout": hold, "real": real}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
