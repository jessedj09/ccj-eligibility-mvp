# -*- coding: utf-8 -*-
"""reference_candidates.py — 기준 연도가 바뀐 공고의 소득표에서 '새 기준표 후보'를 만든다(docs/09 §21 T3 A단계).

해마다 소득 기준(도시근로자 월평균소득·기준중위소득)이 바뀌면 새 공고에는 등록 기준표(rules/reference/income_standard*.json)
금액이 없어 기준표 연도 확인(`sheet_extract.reference_guard`)이 그 조건을 보류한다. 운영자가 새 기준표를 손으로 만들 때까지
보류가 이어지므로, 공고의 표를 칸 위치까지 읽어(src/pdf_tables.py) 같은 칸 구성의 후보를 만들어 둔다.

원칙
- **후보일 뿐 등록하지 않는다** — 운영자가 원문과 대조해 승인해야 rules/reference/에 들어간다.
- 금액은 **원문 칸에 있는 값만** 쓴다(기준액 × 비율로 계산해 채우지 않음). 원문에 없는 칸은 `missing`.
- 검증: 두 추출기 교차·격자 일관성·방법 충돌(pdf_tables.merge) + 가구원수별 기준액이 칸마다 같음 + 등록 표 대비 변화 폭
  (±15% 밖이면 문제) + 기준 연도(원문에 적힌 경우만, 등록 표와 같은 연도면 문제 — 정정 공고일 수 있음).
- 등록 기준표로 이미 설명되는 칸(같은 연도)은 후보 재료로 쓰지 않는다.
"""
import copy
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import pdf_tables as P
import source_verify as sv
from notice_candidates import income_pages

MAX_CHANGE = 0.15            # 등록 표 대비 가구원수별 100% 기준액 변화 폭 한도(해마다 몇 % 안팎)
MIN_COVERAGE = 0.5           # 등록 표 칸 중 원문 표에서 찾은 비율이 이보다 낮으면 그 기준표의 표가 아니라고 본다
YEAR = (re.compile(r"(20\d{2})년도?(?:도시근로자|가구원수별|기준중위소득)"),
        re.compile(r"(20\d{2})년기준(?:금액|중위소득)?"),
        re.compile(r"전년도\((20\d{2})년\)"))
ADDER = re.compile(r"1인당([\d,]{6,9})원")


@dataclass
class Candidate:
    ref_id: str                                     # 이 후보가 대신할 등록 기준표
    table: Dict[str, Dict[str, int]]                # 등록 표와 같은 칸(가구원수 → 비율 → 금액), 원문 칸 금액만
    missing: List[Tuple[int, int]]                  # 원문 표에서 찾지 못한 등록 표 칸
    pages: List[int]
    cells: List[P.Cell] = field(default_factory=list)
    year: Optional[str] = None                      # 원문 표 쪽에 적힌 기준 연도(없으면 None — 운영자 확인)
    change: Dict[int, float] = field(default_factory=dict)   # 가구원수별 100% 기준액 변화율(새/등록 − 1)
    adder7: Optional[int] = None                    # 7인 이상 1인당 가산(등록 표가 쓰는 경우만 원문에서 찾음)
    problems: List[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        n = sum(len(r) for r in self.table.values())
        return n / (n + len(self.missing)) if n + len(self.missing) else 0.0

    @property
    def ok(self) -> bool:
        return not self.missing and not self.problems


def table_pages(pages: List[str]) -> List[int]:
    """소득표가 있을 만한 쪽 — 등록 기준표 금액이 많은 쪽·'월평균소득' 쪽(income_pages) + '기준중위소득' 쪽."""
    found = {x["page"] for x in income_pages(pages)}
    found |= {i for i, t in enumerate(pages, 1) if "기준중위소득" in t and len(re.findall(r"\d,\d{3},\d{3}", t)) >= 3}
    return sorted(found)


def new_year_cells(pdf, pages: List[str], fams: List[P.Family]) -> List[P.Cell]:
    """검증을 통과한 표 칸 중 등록 기준표 묶음으로 설명되지 않는 칸(다른 연도·다른 기준의 표)."""
    tables = P.read_tables(pdf, table_pages(pages))
    cells, _ = P.merge([P.income_cells(t) for t in tables])
    cells = [c for c in cells if not P.cross_check(P.Grid(c.page, c.method, [c]), pages[c.page - 1])]
    return P.compare_reference(cells, fams)["other"]


def _bases(pairs: List[Tuple[int, int]]) -> Optional[Tuple[float, float]]:
    lo = max(P._interval(a, r)[0] for r, a in pairs)
    hi = min(P._interval(a, r)[1] for r, a in pairs)
    return (lo, hi) if lo <= hi else None


def _year(pages: List[str], at: Iterable[int]) -> Optional[str]:
    found = Counter()
    for p in at:
        for rx in YEAR:
            found.update(rx.findall(pages[p - 1]))
    return found.most_common(1)[0][0] if found else None


def candidate(ref_id: str, ref: dict, cells: List[P.Cell], pages: List[str]) -> Optional[Candidate]:
    keys = {(int(s), int(r)) for s, row in ref["table"].items() for r in row}
    core = {tuple(k) for k in ref.get("required_in_every_notice", [])} or keys   # 모든 공고가 싣는 칸(없으면 전체)
    mine = [c for c in cells if (c.size, c.ratio) in keys]
    if not mine or len({(c.size, c.ratio) for c in mine} & core) / len(core) < MIN_COVERAGE:
        return None
    cand = Candidate(ref_id, {}, [], sorted({c.page for c in mine}), mine)
    by_key: Dict[Tuple[int, int], set] = {}
    for c in mine:
        by_key.setdefault((c.size, c.ratio), set()).add(c.amount)
    for (s, r), amounts in sorted(by_key.items()):
        if len(amounts) > 1:
            cand.problems.append(f"{s}인 {r}% 칸이 쪽마다 다름: {sorted(amounts)}")
            continue
        cand.table.setdefault(str(s), {})[str(r)] = amounts.pop()
    cand.missing = sorted(keys - set(by_key))
    old = P._ref_family(ref_id, ref)
    for s in sorted({c.size for c in mine if c.size <= 6}):
        new = _bases([(c.ratio, c.amount) for c in mine if c.size == s])
        if new is None:
            cand.problems.append(f"{s}인 칸들이 한 기준액으로 설명되지 않음")
            continue
        if s in old.base:
            cand.change[s] = (sum(new) / 2) / (sum(old.base[s]) / 2) - 1
            if abs(cand.change[s]) > MAX_CHANGE:
                cand.problems.append(f"{s}인 기준액 변화 {cand.change[s]:+.1%} — 등록 표와 너무 다름(다른 기준의 표일 수 있음)")
    cand.year = _year(pages, cand.pages)
    if cand.year and cand.year == str(ref.get("year_basis")):
        cand.problems.append(f"원문 기준 연도 {cand.year}가 등록 표와 같은데 금액이 다름 — 정정 공고인지 확인")
    if int(ref.get("per_person_adder_7plus") or 0):
        found = {int(x.replace(",", "")) for p in cand.pages for x in ADDER.findall(pages[p - 1])}
        cand.adder7 = found.pop() if len(found) == 1 else None
        if cand.adder7 is None:
            cand.problems.append("7인 이상 1인당 가산 금액을 원문 표 쪽에서 하나로 찾지 못함")
    return cand


def candidates(pdf, pages: Optional[List[str]] = None, refs: Optional[Dict[str, dict]] = None,
               only: Optional[Iterable[str]] = None) -> List[Candidate]:
    """공고 PDF(경로·바이트) → 새 기준표 후보(등록 표마다 하나, 그 표의 칸이 원문 표에 절반 이상 있을 때만)."""
    if pages is None:
        pages = sv.extract_pages(pdf) if not isinstance(pdf, (bytes, bytearray)) else sv.extract_pages_bytes(pdf, cache=False)
    refs = refs if refs is not None else P.load_references()
    cells = new_year_cells(pdf, pages, P.families(refs))
    out = []
    for rid in (only or refs):
        c = candidate(rid, refs[rid], cells, pages)
        if c:
            out.append(c)
    return out


def agree(cands: List[Candidate]) -> List[str]:
    """같은 기준표의 후보 여러 개(서로 다른 공고)가 겹치는 칸에서 같은 금액인지 — 다른 칸 목록(비어 있어야 함)."""
    seen: Dict[Tuple[str, str, str], set] = {}
    for c in cands:
        for s, row in c.table.items():
            for r, v in row.items():
                seen.setdefault((c.ref_id, s, r), set()).add(v)
    return [f"{rid} {s}인 {r}%: {sorted(v)}" for (rid, s, r), v in sorted(seen.items()) if len(v) > 1]


def combine(cands: List[Candidate], ref: dict) -> Candidate:
    """같은 기준표의 후보 여러 개(서로 다른 공고)를 합친다 — 매입임대처럼 공고마다 다른 비율 열을 싣는 표(Ⅰ형 70·90%, Ⅱ형 130·200%).
    겹치는 칸 금액이 다르거나 기준 연도가 다르면 문제로 적는다."""
    keys = {(int(s), int(r)) for s, row in ref["table"].items() for r in row}
    out = Candidate(cands[0].ref_id, {}, [], sorted({p for c in cands for p in c.pages}),
                    [x for c in cands for x in c.cells])
    out.problems = [f"칸 금액이 공고마다 다름 — {d}" for d in agree(cands)]
    out.problems += sorted({p for c in cands for p in c.problems})
    for c in cands:
        for s, row in c.table.items():
            for r, v in row.items():
                out.table.setdefault(s, {}).setdefault(r, v)
    out.missing = sorted(keys - {(int(s), int(r)) for s, row in out.table.items() for r in row})
    years = {c.year for c in cands if c.year}
    out.year = years.pop() if len(years) == 1 else None
    if len({c.year for c in cands if c.year}) > 1:
        out.problems.append(f"공고마다 기준 연도가 다름: {sorted({c.year for c in cands if c.year})}")
    for s in {s for c in cands for s in c.change}:
        out.change[s] = sum(c.change[s] for c in cands if s in c.change) / sum(1 for c in cands if s in c.change)
    adders = {c.adder7 for c in cands if c.adder7}
    out.adder7 = adders.pop() if len(adders) == 1 else None
    if out.adder7 is not None:
        out.problems = [p for p in out.problems if not p.startswith("7인 이상 1인당 가산")]
    return out


def to_reference(cand: Candidate, ref: dict, source_label: str) -> dict:
    """후보 → 기준표 JSON 초안(status CANDIDATE). 운영자가 원문과 대조·승인한 뒤 rules/reference/에 넣는다."""
    out = copy.deepcopy(ref)
    year = cand.year or "확인필요"
    out.update({
        "id": f"{cand.ref_id}_{year}",
        "status": "CANDIDATE",
        "candidate_of": cand.ref_id,
        "year_basis": cand.year,
        "source": f"자동 후보(표 칸 위치 읽기, src/reference_candidates.py) — {source_label} p.{cand.pages}. 운영자 확인 전",
        "table": cand.table,
        "cited_pages": {},
        "candidate_check": {"missing": [f"{s}인 {r}%" for s, r in cand.missing], "problems": cand.problems,
                            "change": {str(s): round(v, 4) for s, v in cand.change.items()}},
    })
    if int(ref.get("per_person_adder_7plus") or 0):
        out["per_person_adder_7plus"] = cand.adder7
    return out
