# -*- coding: utf-8 -*-
"""조항 장부(자동 판정 v3 ②, docs/10 §2-4) — 공고문의 '조건처럼 보이는 문장'을 하나도 빠짐없이 분류해, 규칙이 모르는 새 조건을 찾는다.

    python tools/clause_ledger.py N12                     # 등록 공고 1건(형제 = 같은 사업의 다른 등록 공고)
    python tools/clause_ledger.py --all                   # 등록 공고 전부 요약
    python tools/clause_ledger.py --all --out docs/clause-ledger-review.md   # 미분류 문장 검토 목록

분류(위에서부터 먼저 맞는 것):
  근거            규칙 조건의 인용문이거나 조건 식의 값(유형 이름 등)을 담은 문장
  근거(하위 항목)  근거 문장 바로 아래의 목록 항목(①·1)·가.·- …)
  형제 공고에도   같은 사업의 다른 등록 공고에도 있는 문장 — 그 공고를 등록한 사람이 조건이 아니라고 본 것
  무관:<범주>     공통 제한(외국인·중복 신청 등, 판정 범위 밖 — 안내)·정의·서류·절차·계약·임대·선정·순위·안내
  **미분류**      위 어디에도 없음 → 규칙이 모르는 새 조건일 수 있다
'신청할 수 없'·'~에 한하여 신청'·'거주자만'·'이상인 자' 같은 강한 제한 표현이 있으면 서류·절차 등 무관 범주로 넘기지 않는다
(공통 제한·근거·형제 공고 확인은 그대로).
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

import llm_slot as L  # noqa: E402
import source_verify as sv  # noqa: E402

CACHE = ROOT / ".cache" / "ledger_units"

MARK = re.compile(r"^\s*([•■①-⑳*※○□▶◆◇·ㆍ\-–]|\d+[.)]|[가-하][.)]|\(\d+\)|\d+순위)")
CONDLIKE = re.compile(r"(인자|한자|된자|는자|인사람|한사람|는사람|일것|이어야|여야|신청불가|신청할수없|신청이불가|신청제한|제외|"
                      r"에한하여|에한함|만신청|만해당|거주하는자|거주자에|소유하지않|무주택세대구성원|무주택자)")
STRONG = re.compile(r"(만신청|에한하여신청|신청할수없|신청불가|신청이불가|신청제한|거주하는자|거주자만|이상거주|이내인자|이하인자|"
                    r"이상인자|미만인자|소유하지않은자|해당하지않는자)")
COMMON = re.compile(r"(외국인|재외국민|중복신청|중복당첨|중복으로|말소|거주불명|행방불명|가출|무효처리|부정당첨|불법전대|"
                    r"1세대1주택|1주택만|1주택형만|1주택단지만)")
DEFINITION = re.compile(r"(이란|란,|말함|말한다|의미|산정|산출|가액은|공시지가|평가하|기준으로하며|기준으로합니다|포함됩니다|포함한다|포함함)")
ENUM = re.compile(r"^([①-⑳]|\d+\)|\d(?=[「가-힣])|[가-하][.)]|\(\d+\)|-)")
UNRELATED = {
    "서류": r"(서류|제출|발급|증명서|등본|초본|확인서|사본|증빙|동의서|원본)",
    "절차": r"(인터넷|방문접수|신청서|접수|청약센터|로그인|공동인증|홈페이지|모바일|앱|신청방법|신청기간|삭제)",
    "계약·임대": r"(계약|입주지정|임대기간|재계약|임대료|보증금|월임대|전환|관리비|퇴거|명도|갱신)",
    "선정·순위": r"(감점|가점|배점|순번|추첨|선정방법|동점|예비입주자|예비자|당첨|순위별|배정|선정순서)",
    "안내": r"(주택관리번호|www|문의|콜센터|유의|참조|참고|바랍니다|안내|열람|게시|점심시간|공개시간|사전공개|시설물|승강기|"
            r"사다리차|일조권|조망권|철거|하자)",
}
UNRELATED = {k: re.compile(v) for k, v in UNRELATED.items()}
UNCLASSIFIED = "미분류"


def _units_from_raw(raw: Sequence[str]) -> List[Tuple[int, str]]:
    """쪽 텍스트(띄어쓰기·줄바꿈 유지) → 문장 단위(목록 기호로 시작하는 줄에서 새 단위, 나머지 줄은 이어 붙임) → (쪽, 정규화 문장)."""
    out = []
    for page, text in enumerate(raw, 1):
        cur = None
        for line in text.splitlines():
            if not line.strip():
                continue
            if cur is None or MARK.match(line):
                if cur:
                    out.append(cur)
                cur = [page, line]
            else:
                cur[1] += " " + line
        if cur:
            out.append(cur)
    return [(p, sv.normalize(x)) for p, x in out if len(sv.normalize(x)) >= 10]


def units_of_pdf(pdf: Path) -> List[Tuple[int, str]]:
    """원문 PDF의 문장 단위(원문 지문으로 캐시 — 형제 공고는 여러 번 쓰인다)."""
    pdf = Path(pdf)
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    cache = CACHE / f"{sha}.json"
    if cache.exists():
        return [tuple(u) for u in json.loads(cache.read_text(encoding="utf-8"))]
    units = _units_from_raw(L.raw_pages(pdf))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
    return units


@lru_cache(maxsize=None)
def registered_units(nid: str) -> Tuple[Tuple[int, str], ...]:
    return tuple(units_of_pdf(sv.pdf_path(nid)))


def evidence_of(doc: Dict) -> Tuple[List[str], List[str]]:
    """규칙 문서 → (인용문들, 조건 식의 문자열 값들) — 정규화. 값에서 지명은 뺀다 — '서울특별시 거주'(규칙에 있음)와
    '서울특별시에 2년 이상 거주'(새 조건)를 지명만으로 같은 근거로 보지 않게."""
    from rule_data import region_names
    regions = {sv.normalize(r) for r in region_names()}
    quotes, values = set(), set()

    def take(q):
        t = sv.normalize(q["text"] if isinstance(q, dict) else q)
        if len(t) >= 6:
            quotes.add(t)

    def strings(x):
        if isinstance(x, dict):
            for v in x.values():
                strings(v)
        elif isinstance(x, list):
            for v in x:
                strings(v)
        elif isinstance(x, str):
            t = sv.normalize(x)
            if len(t) >= 3 and not t.isdigit() and t not in regions and not re.match(r"^(N\d+|DRAFT|NEW)-", t):
                values.add(t)

    def walk(conds):
        for c in conds:
            for t in c.get("tracks", []):
                walk(t["conditions"])
            for q in c.get("source", {}).get("quote", []):
                take(q)
            strings(c.get("check"))
    for ld in doc["layers"].values():
        walk(ld["conditions"])
    for td in doc.get("tables", {}).values():
        for q in td.get("source", {}).get("quote", []):
            take(q)
    return sorted(quotes), sorted(values)


def _mask(s: str) -> str:
    return re.sub(r"\d", "#", s)


class Known:
    """형제 공고들의 문장(숫자를 가린 것 그대로 + 비슷한 문장 85% 이상)."""

    def __init__(self, sibling_units: Sequence[Tuple[int, str]]):
        self.masked = {_mask(u) for _, u in sibling_units}
        self.texts = [u for _, u in sibling_units]

    def has(self, u: str) -> bool:
        if _mask(u) in self.masked:
            return True
        for s in self.texts:
            if abs(len(s) - len(u)) >= len(u) * 0.3:
                continue
            m = SequenceMatcher(None, u, s, autojunk=False)
            if m.quick_ratio() >= 0.85 and m.ratio() >= 0.85:
                return True
        return False


def classify(units: Sequence[Tuple[int, str]], doc: Dict, known: Known) -> List[Tuple[int, str, str]]:
    """→ [(쪽, 문장, 분류)] — 조건처럼 보이지 않는 문장은 뺀다."""
    quotes, values = evidence_of(doc)
    out, parent = [], None
    for page, u in units:
        is_evidence = any(q in u or u in q for q in quotes) or any(v in u for v in values)
        if is_evidence:
            parent = page
        elif not ENUM.match(u):
            parent = None
        if not CONDLIKE.search(u):
            continue
        if is_evidence:
            label = "근거"
        elif parent == page and ENUM.match(u):
            label = "근거(하위 항목)"
        elif known.has(u):
            label = "형제 공고에도"
        elif COMMON.search(u):
            label = "무관:공통 제한"
        elif DEFINITION.search(u) and not STRONG.search(u):
            label = "무관:정의"
        else:
            cat = None if STRONG.search(u) else next((k for k, rx in UNRELATED.items() if rx.search(u)), None)
            label = f"무관:{cat}" if cat else UNCLASSIFIED
        out.append((page, u, label))
    return out


def siblings_of(nid: str) -> List[str]:
    """등록 공고의 형제 = 같은 템플릿(행복주택은 템플릿 공고 N1~N3 포함)의 다른 등록 공고."""
    import templates as T
    from rule_data import notice_ids
    tpl = {n: T.gold_sheet(n)["template"] for n in T.sheet_ids()}
    tpl.update({n: "lh.happy_housing" for n in ("N1", "N2", "N3")})
    return [n for n in notice_ids() if n != nid and tpl.get(n) == tpl.get(nid)]


def ledger_for_registered(nid: str) -> List[Tuple[int, str, str]]:
    known = Known([u for s in siblings_of(nid) for u in registered_units(s)])
    return classify(registered_units(nid), sv.notice_doc(nid), known)


def ledger_for_draft(pdf: Path, doc: Dict, sibling_nids: Sequence[str]) -> List[Tuple[int, str, str]]:
    """새 공고(초안 규칙 doc) — 형제는 그 템플릿의 등록 공고."""
    known = Known([u for s in sibling_nids for u in registered_units(s)])
    return classify(units_of_pdf(pdf), doc, known)


def summary(rows) -> Counter:
    return Counter(label for _, _, label in rows)


def main(argv=None):
    from rule_data import notice_ids
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("nid", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", help="미분류 문장 검토 목록(.md)")
    a = ap.parse_args(argv)
    nids = notice_ids() if a.all else [a.nid]
    total, lines = Counter(), ["# 조항 장부 — 미분류 문장 검토 목록", "",
                               "등록 공고마다 '조건처럼 보이지만 규칙 근거·형제 공고·무관 범주 어디에도 없는 문장'(`tools/clause_ledger.py`).",
                               "각 문장을 원문과 대조해 ① 규칙에 빠진 조건이면 규칙을 고치고 ② 조건이 아니면 범주를 보강한다.", ""]
    for nid in nids:
        rows = ledger_for_registered(nid)
        c = summary(rows)
        total += c
        print(f"{nid}: 조건형 문장 {sum(c.values())} — 근거 {c['근거'] + c['근거(하위 항목)']} · 형제 공고에도 {c['형제 공고에도']} · "
              f"무관 {sum(v for k, v in c.items() if k.startswith('무관'))} · 미분류 {c[UNCLASSIFIED]}")
        if c[UNCLASSIFIED]:
            lines += [f"## {nid} ({c[UNCLASSIFIED]})", ""] + [f"- p.{p} {u[:160]}" for p, u, lab in rows
                                                              if lab == UNCLASSIFIED] + [""]
    print("합계:", dict(total))
    if a.out:
        Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("검토 목록:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
