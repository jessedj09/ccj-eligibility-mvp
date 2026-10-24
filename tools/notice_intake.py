# -*- coding: utf-8 -*-
"""새 공고 등록용 내부 도구(E1). 판정은 하지 않는다 — 규칙 데이터를 만들 사람(또는 Claude)이 원문에서 찾을 것을 모아 준다.

    python tools/notice_intake.py <공고문.pdf> [--out 보고서.md]   # 후보 추출 보고서
    python tools/notice_intake.py --audit                          # 등록된 공고 전부의 등록 누락 점검(누락 있으면 종료코드 1)

보고서(후보 추출)에 담는 것 — 모두 '후보'이고, 쪽 번호와 원문 그대로의 인용문을 함께 준다:
  1) 이미 등록된 공고인지(sha256), 발행 기관·사업 유형 추정과 같은 사업의 등록 공고·생성 스크립트
  2) 공고일 후보, 3) 청약 접수기간 후보(rules/schedules.json에 바로 넣을 수 있는 형태, 원문 대조 규칙으로 자체 확인)
  4) 소득 기준표 쪽 후보(등록된 기준표 rules/reference/income_standard*.json과 같은 숫자가 몇 개 있는지)
  5) 기준일 리터럴 후보("…이후 출생", "…이전 출생" 등 — SH는 공고일−N년의 다음 날이므로 원문 날짜를 그대로 쓴다)
  6) 공급 계층·주택형 키워드가 나오는 쪽, 7) 등록 체크리스트
점검(--audit)은 공고마다 원문 PDF·공고 분석·접수기간·골든 입력(DATES·GROUPS)·입력 범위 규칙·소득표 대조가 다 있는지 본다.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import source_verify as sv  # noqa: E402
from rule_data import LAYERS, load_notice, notice_ids  # noqa: E402

# 사업 유형 추정 — 위에서부터 먼저 맞는 것(구체적인 것이 위). 값은 등록 공고 meta.program의 앞부분과 맞춘다.
PROGRAMS = [
    ("장기전세주택2", ("SH", "SH 장기전세주택2")), ("장기전세", ("SH", "SH 장기전세주택")),
    ("장기미임대", ("SH", "SH 장기미임대")), ("일반주택형미리내집", ("SH", "SH 일반주택형 미리내집")),
    ("든든전세", ("LH", "든든전세")), ("청년매입임대", ("LH", "청년매입임대")),
    ("신혼·신생아매입임대주택II", (None, "신혼·신생아 매입임대Ⅱ")), ("신혼·신생아매입임대주택Ⅱ", (None, "신혼·신생아 매입임대Ⅱ")),
    ("신혼·신생아매입임대주택I", (None, "신혼·신생아 매입임대Ⅰ")), ("신혼·신생아매입임대주택Ⅰ", (None, "신혼·신생아 매입임대Ⅰ")),
    ("신혼희망타운행복주택", ("LH", "행복주택(신혼희망타운)")), ("행복주택", ("LH", "행복주택")),
]
KEYWORDS = list(LAYERS) + ["예비신혼", "신생아", "주거약자", "우선공급", "1순위", "2순위", "맞벌이", "자동차", "총자산"]
WEEK = "[월화수목금토일]"


def _date(p: str) -> str:
    return rf"(?:'?(?P<{p}y>20\d\d|\d\d)\.)?(?P<{p}m>\d{{1,2}})\.(?P<{p}d>\d{{1,2}})\.?\({WEEK}\)"


RANGE = re.compile(_date("s") + r"(?P<st>\d{1,2}:\d\d)[~∼](?:" + _date("e") + r")?(?P<et>\d{1,2}:\d\d)")
ANN = re.compile(r"(?:입주자모집공고일|모집공고일|공고일)[:：|]?\(?(20\d\d)\.(\d{1,2})\.(\d{1,2})")
ANY_DATE = re.compile(r"(20\d\d)\.(\d{1,2})\.(\d{1,2})\.?(?:\(" + WEEK + r"(?:요일)?\))?")
CUTOFF = re.compile(r"(?:\[|\()?((?:19|20)\d\d|'\d\d)\.(\d{1,2})\.(\d{1,2})\.?(?:\(" + WEEK + r"\))?(이후|이전|~)")
APPLY_WORDS = ("청약", "신청", "접수")
NOT_APPLY = ("서류", "계약", "현장", "방문", "소명", "공개", "발표", "등기")


def _year(y: Optional[str], m: int, d: int, ann: Optional[date]) -> int:
    if y:
        return int(y) if len(y) == 4 else 2000 + int(y)
    base = ann.year if ann else date.today().year
    return base + 1 if ann and date(base, m, d) < ann else base


def announcement_candidates(pages: List[str]) -> List[dict]:
    seen = Counter()
    first = {}
    for i, t in enumerate(pages[:8], 1):
        for m in ANN.finditer(t):
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            seen[d] += 1
            first.setdefault(d, (i, m.group(0)))
    if not seen:   # SH 표지처럼 "공고일" 없이 날짜만 있으면: 앞 두 쪽에서 "모집공고"·"공고일" 가까이 있는 날짜
        for i, t in enumerate(pages[:2], 1):
            for m in ANY_DATE.finditer(t):
                near = t[max(0, m.start() - 40):m.end() + 60]
                if "공고" not in near:
                    continue
                try:
                    d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    continue
                seen[d] += 1
                first.setdefault(d, (i, near))
    return [{"date": d.isoformat(), "count": c, "page": first[d][0], "quote": first[d][1]} for d, c in seen.most_common()]


def window_candidates(pages: List[str], ann: Optional[date]) -> List[dict]:
    """청약 접수기간 후보. 앞 문맥에 청약·신청·접수가 있고 서류·계약·현장 등이 없으면 '접수' 후보로 올린다.
    같은 기간이 여러 쪽에 나오면 한 번만(첫 쪽) 싣고 나온 쪽을 모은다."""
    out: Dict[tuple, dict] = {}
    for i, t in enumerate(pages, 1):
        for m in RANGE.finditer(t):
            g = m.groupdict()
            try:
                sm, sd = int(g["sm"]), int(g["sd"])
                start = datetime(_year(g["sy"], sm, sd, ann), sm, sd, *map(int, g["st"].split(":")))
                em, ed = (int(g["em"]), int(g["ed"])) if g["em"] else (sm, sd)
                end = datetime(_year(g["ey"] or (g["sy"] if g["em"] is None else None), em, ed, ann), em, ed,
                               *map(int, g["et"].split(":")))
            except ValueError:
                continue
            if end <= start or (ann and start.date() <= ann):
                continue
            before = t[max(0, m.start() - 30):m.start()]
            applyish = any(w in before for w in APPLY_WORDS) and not any(w in before[-12:] for w in NOT_APPLY)
            key = (start, end)
            quote = m.group(0)
            ok = sv._date_in_quote(start.isoformat(timespec="minutes"), quote) and \
                sv._date_in_quote(end.isoformat(timespec="minutes"), quote)
            if key not in out:
                out[key] = {"start": start.isoformat(timespec="minutes"), "end": end.isoformat(timespec="minutes"),
                            "page": i, "quote": quote, "context": before[-20:], "apply": applyish,
                            "quote_check": ok, "pages": [i]}
            else:
                out[key]["pages"].append(i)
                out[key]["apply"] |= applyish
    return sorted(out.values(), key=lambda w: (not w["apply"], w["start"]))


def income_pages(pages: List[str]) -> List[dict]:
    """등록된 소득 기준표의 숫자가 많이 나오는 쪽. 같은 기준표(같은 연도)면 기존 표를 cited_pages에 추가하면 된다."""
    out = []
    for path in sorted((ROOT / "rules" / "reference").glob("income_standard*.json")):
        ref = json.loads(path.read_text(encoding="utf-8"))
        values = {f"{v:,}" for row in ref["table"].values() for v in row.values()}
        for i, t in enumerate(pages, 1):
            hits = sum(1 for v in values if v in t)
            if hits >= 3:
                out.append({"table": path.stem, "label": ref.get("label", ""), "page": i, "hits": hits,
                            "of": len(values)})
    wage = [i for i, t in enumerate(pages, 1) if "월평균소득" in t and re.search(r"\d{1,2},\d{3},\d{3}", t)]
    return sorted(out, key=lambda x: -x["hits"]) + [{"table": None, "page": i} for i in wage
                                                     if i not in {x["page"] for x in out}]


def _full_year(y: str) -> int:
    """'24 → 2024, '61 → 1961(내년 뒤의 두 자리 연도는 1900년대 — 고령자 출생일 등)."""
    if not y.startswith("'"):
        return int(y)
    yy = int(y[1:])
    return 2000 + yy if yy <= date.today().year % 100 + 1 else 1900 + yy


def cutoff_candidates(pages: List[str]) -> List[dict]:
    out = {}
    for i, t in enumerate(pages, 1):
        for m in CUTOFF.finditer(t):
            # 출생·혼인 기준일만 — 그 말이 날짜 바로 뒤(…이후 출생)나 앞(혼인신고를 한 날로부터 7년 이내(…이후))에 있어야 한다
            around = t[max(0, m.start() - 30):m.start()] + t[m.end():m.end() + 10]
            if not re.search(r"출생|혼인|태어", around):
                continue
            key = (m.group(1), m.group(2), m.group(3), m.group(4))
            out.setdefault(key, {"date": f"{_full_year(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}",
                                 "direction": m.group(4), "page": i,
                                 "quote": t[max(0, m.start() - 15):m.end() + 10]})
    return list(out.values())


def keyword_pages(pages: List[str]) -> Dict[str, List[int]]:
    return {k: [i for i, t in enumerate(pages, 1) if k in t] for k in KEYWORDS
            if any(k in t for t in pages)}


def classify(pages: List[str]):
    head = "".join(pages[:3])
    issuer = "SH" if "i-sh.co.kr" in "".join(pages) else "LH" if "apply.lh.or.kr" in "".join(pages) else None
    # 제목이 맨 앞에 오므로 가장 먼저 나오는 사업 이름을 쓴다(본문은 다른 사업을 함께 언급한다 — 예: 미리내집 공고의
    # "아파트형 미리내집(장기전세주택Ⅱ)"). 같은 위치면 더 긴 이름(구체적인 것).
    for text in (pages[0] if pages else "", head):
        found = [(text.find(key), -len(key), iss, program) for key, (iss, program) in PROGRAMS if key in text]
        if found:
            _, _, iss, program = min(found)
            return iss or issuer, program
    return issuer, None


def similar_notices(issuer: Optional[str], program: Optional[str]) -> List[str]:
    if not program:
        return []
    base = program.replace("SH ", "")
    out = []
    for nid in notice_ids():
        meta = load_notice(nid).meta
        if (issuer is None or meta.get("issuer") == issuer) and base in meta.get("program", ""):
            out.append(nid)
    return out


def generators_for(nids: List[str]) -> List[str]:
    out = []
    for g in sorted((ROOT / "tools").glob("gen_*.py")):
        text = g.read_text(encoding="utf-8")
        if any(f'"{n}"' in text for n in nids):
            out.append(g.name)
    return out


def registered_as(sha: str) -> Optional[str]:
    for nid in notice_ids():
        if sv.notice_doc(nid)["source"]["sha256"] == sha:
            return nid
    return None


def next_notice_id() -> str:
    return f"N{max(int(n[1:]) for n in notice_ids()) + 1}"


def report(path: Path, pages: Optional[List[str]] = None) -> dict:
    path = Path(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    pages = pages if pages is not None else sv.extract_pages(path)
    anns = announcement_candidates(pages)
    ann = date.fromisoformat(anns[0]["date"]) if anns else None
    issuer, program = classify(pages)
    similar = similar_notices(issuer, program)
    return {"file": str(path), "sha256": sha, "pages": len(pages),
            "extraction_failures": sv.EXTRACTION_FAILURES.get(str(path), []),
            "registered_as": registered_as(sha), "next_id": next_notice_id(),
            "issuer": issuer, "program": program, "similar": similar, "generators": generators_for(similar),
            "announcement": anns, "windows": window_candidates(pages, ann), "income": income_pages(pages),
            "cutoffs": cutoff_candidates(pages), "keywords": keyword_pages(pages)}


def to_markdown(r: dict) -> str:
    L = [f"# 공고 등록 후보 보고서 — {Path(r['file']).name}", "",
         "> 자동 추출한 **후보**다. 판정에 쓰기 전에 반드시 원문 쪽을 열어 확인하고, 규칙 데이터의 인용문은 원문 그대로 쓴다.", "",
         "## 1. 기본", f"- 쪽 수 {r['pages']}, sha256 `{r['sha256'][:16]}…`"
         + (f", **추출 실패 쪽 {r['extraction_failures']}**" if r["extraction_failures"] else "")]
    L.append(f"- **이미 등록된 공고: {r['registered_as']}**" if r["registered_as"] else f"- 신규 공고 — 다음 ID 후보 `{r['next_id']}`")
    L.append(f"- 발행 기관 추정 {r['issuer'] or '알 수 없음'}, 사업 유형 추정 **{r['program'] or '알 수 없음(새 사업 유형일 수 있음)'}**")
    if r["similar"]:
        L.append(f"- 같은 사업의 등록 공고: {', '.join(r['similar'])} — 생성 스크립트: {', '.join(r['generators']) or '없음'}")
    L += ["", "## 2. 공고일 후보"]
    L += [f"- **{a['date']}** ({a['count']}회, 첫 쪽 p.{a['page']}: `{a['quote']}`)" for a in r["announcement"]] or ["- 못 찾음"]
    L += ["", "## 3. 청약 접수기간 후보", "앞 문맥에 청약·신청·접수가 있는 것(✅)을 먼저 보인다. 순위별 접수일이 따로 있으면 각각 별도 기간이다.", ""]
    for w in r["windows"]:
        mark = "✅" if w["apply"] else "·"
        chk = "" if w["quote_check"] else " ⚠️인용문-날짜 불일치"
        L.append(f"- {mark} {w['start']} ~ {w['end']} — p.{w['page']} (나온 쪽 {sorted(set(w['pages']))}) "
                 f"문맥 `…{w['context']}` 인용 `{w['quote']}`{chk}")
    apply = [w for w in r["windows"] if w["apply"]]
    if apply:
        snippet = {"windows": [{"label": "인터넷 청약", "start": w["start"], "end": w["end"],
                                "source": {"page": w["page"], "quote": [w["quote"]]}} for w in apply[:3]]}
        L += ["", "schedules.json 초안(라벨·기간 수는 원문을 보고 고칠 것):", "```json",
              json.dumps({r["registered_as"] or r["next_id"]: snippet}, ensure_ascii=False, indent=2), "```"]
    L += ["", "## 4. 소득 기준표 쪽 후보"]
    for x in r["income"]:
        if x["table"]:
            L.append(f"- p.{x['page']}: 등록 기준표 `{x['table']}`({x['label']}) 숫자 {x['hits']}/{x['of']}개 일치")
        else:
            L.append(f"- p.{x['page']}: 월평균소득 금액표(등록 기준표와 일치하는 숫자 적음 — 다른 연도·사업 기준표일 수 있음)")
    if not r["income"]:
        L.append("- 못 찾음(소득 요건이 없는 사업이거나 표가 그림일 수 있음)")
    L += ["", "## 5. 기준일 리터럴 후보 (출생·혼인 기준일)"]
    L += [f"- {c['date']} {c['direction']} — p.{c['page']} `{c['quote']}`" for c in r["cutoffs"]] or ["- 못 찾음"]
    L += ["", "## 6. 계층·주택형 키워드가 나오는 쪽"]
    L += [f"- {k}: {v[:12]}{' …' if len(v) > 12 else ''}" for k, v in r["keywords"].items()]
    nid = r["registered_as"] or r["next_id"]
    L += ["", "## 7. 등록 체크리스트", "",
          f"1. 공고 분석 `docs/notice-analysis/` + `index.json`(sha256) — 계층·소득·자산·기준일·순위 구조를 원문 쪽과 함께 정리",
          f"2. 규칙 데이터 `rules/notices/{nid}.json` — 같은 사업이면 위 생성 스크립트에 공고를 추가해 만든다(재실행 안전 유지)",
          "3. 소득 기준표 — 같은 기준표면 `rules/reference/income_standard*.json`의 `cited_pages`에 쪽 추가, 다르면 결정표에 직접",
          f"4. 접수기간 `rules/schedules.json`에 `{nid}` (위 3번 초안)",
          f"5. 골든 `tests/golden_cases.py` — `DATES`(손계산 기준일), `GROUPS`(맨 뒤에 추가 — 기존 그룹 불변), 필요하면 `PROGRAM_OF`·지역",
          "6. 새 사업 유형이면 `rules/reference/input_scope.json`(본인/세대 범위)과 화면 질문",
          "7. 확인: `python tools/verify_sources.py` → `python tools/regen_golden.py`(기존 그룹 불변 확인) → "
          "`python -m pytest -q` → `python tools/ui_smoke.py` → `python tools/notice_intake.py --audit`",
          "8. 문서: `docs/07-notice-generalization.md` 결과 절, CLAUDE.md·README 공고 수"]
    return "\n".join(L) + "\n"


def audit() -> List[str]:
    """등록된 공고마다 등록 산출물이 다 있는지. 문제 목록(없으면 빈 목록)."""
    import golden_cases as gc
    from matcher import scope_for
    problems = []
    index = json.loads((ROOT / "docs" / "notice-analysis" / "index.json").read_text(encoding="utf-8"))
    analysed = {x["sha256"] for x in index}
    schedules = json.loads((ROOT / "rules" / "schedules.json").read_text(encoding="utf-8"))["notices"]
    groups = set(gc.GROUPS)
    refs = {p.stem: json.loads(p.read_text(encoding="utf-8"))
            for p in (ROOT / "rules" / "reference").glob("income_standard*.json")}
    for nid in notice_ids():
        doc = sv.notice_doc(nid)
        notice = load_notice(nid)
        try:
            sv.pdf_path(nid)
        except FileNotFoundError as e:
            problems.append(str(e))
        if doc["source"]["sha256"] not in analysed:
            problems.append(f"{nid}: 공고 분석(docs/notice-analysis/index.json)에 이 PDF(sha256)가 없음")
        if nid not in schedules:
            problems.append(f"{nid}: 접수기간(rules/schedules.json) 없음")
        if nid not in gc.DATES:
            problems.append(f"{nid}: 골든 기준일(tests/golden_cases.py DATES) 없음")
        for layer in notice.layers:
            if (nid, layer) not in groups:
                problems.append(f"{nid}: 골든 그룹(GROUPS)에 '{layer}' 없음")
            try:
                scope_for(notice, layer)
            except ValueError as e:
                problems.append(f"{nid}: {e}")
        text = json.dumps(doc, ensure_ascii=False)
        for ref_id, ref in refs.items():
            if f'"{ref_id}"' in text and nid not in ref["cited_pages"]:
                problems.append(f"{nid}: 소득 기준표 {ref_id}를 쓰지만 cited_pages에 없음")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf", nargs="?", help="새 공고문 PDF")
    ap.add_argument("--out", help="보고서를 저장할 .md 경로(없으면 화면에 출력)")
    ap.add_argument("--audit", action="store_true", help="등록된 공고 전부의 등록 누락 점검")
    a = ap.parse_args(argv)
    if a.audit:
        problems = audit()
        print(f"등록 공고 {len(notice_ids())}건 점검 — 누락 {len(problems)}건")
        for p in problems:
            print("  -", p)
        return 1 if problems else 0
    if not a.pdf:
        ap.error("PDF 경로 또는 --audit가 필요합니다")
    md = to_markdown(report(Path(a.pdf)))
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        print("보고서:", a.out)
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
