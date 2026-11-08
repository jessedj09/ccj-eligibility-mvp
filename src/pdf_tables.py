# -*- coding: utf-8 -*-
"""pdf_tables.py — 공고문 PDF의 표를 칸 위치까지 읽는다(pdfplumber). docs/09 §19 T1·T2(평가 단계 — 판정 경로에는 아직 연결하지 않음).

pypdf 텍스트는 표를 한 줄로 풀어 빈 칸(병합 셀)이 사라진다 — "80% 4,693,016원 …"의 첫 값이 몇 인 가구인지 알 수 없다.
여기서는 표를 두 방법으로 읽어 셀 격자를 만든다.
- lines: 표의 선으로 칸을 나눈다(pdfplumber 기본). 선이 다 그어진 표는 정확하다.
- words: 같은 표 영역의 글자 좌표로 줄을 묶고, 금액 글자의 가로 위치로 열을 맞춘다. 세로선이 없는 표(가로선만 있는
  국민임대 기준표 등)에서 lines가 놓치는 맨 앞·맨 뒤 열을 살린다.

소득 기준표 해석 `income_cells`: 머리글의 가구원수(1인…)·비율(70%…)로 칸마다 (가구원수, 비율, 금액)을 만든다.
1·2인 칸은 머리글 비율에 가산(+20%p·+10%p)이 붙은 금액을 싣기도 한다(LH 신혼·신생아 표는 표시도 없다) — 머리글에
'+N%p'가 있으면 그것을, 없으면 같은 가구원수의 두 칸 이상으로 가산 폭을 풀어 정한다(못 풀면 그 칸은 버린다).

검증(T2) — 판정에 쓰려면 모두 통과해야 한다(평가는 tools/eval_tables.py):
- cross_check: 셀 금액이 pypdf 텍스트에도 있다(두 추출기 교차)
- consistent: 같은 가구원수의 칸들이 한 기준액 × 비율(원 단위 반올림·버림)로 설명된다
- agree: 두 방법이 같은 (가구원수, 비율) 칸에서 같은 금액을 낸다
- compare_reference: 등록 기준표(rules/reference/income_standard*.json)와 칸 단위 대조
"""
import io
import json
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

import source_verify as sv

MONEY = re.compile(r"^(\d{1,3}(?:,\d{3}){2,})원?(?:이하|미만)?$")    # 100만 원 이상 금액 하나만 든 칸
SIZE = re.compile(r"^(\d)인(?:가구)?")
RATIO = re.compile(r"(\d{2,3})%(?!p)")
HEAD_RATIO = re.compile(r"[가-힣]*~?(\d{2,3})%(?:이하)?")                 # '70%' · '~30%' · '50%이하' · '월평균소득50%'
PER_SIZE = re.compile(r"(\d{2,3})%\(([^()]*\d인가구\d{2,3}%[^()]*)\)")       # '월평균소득50%(1인가구70%,2인가구60%)'
SIZE_RATIO = re.compile(r"(\d)인가구(\d{2,3})%")
ADDER = re.compile(r"\+(\d{1,2})(?:%p|p%|%포인트)")
COL_GAP = 18.0          # words: 금액 글자 가운데 x가 이만큼 넘게 떨어지면 다른 열(pt)
LINE_GAP = 3.0          # words: 글자 윗변 y가 이만큼 안이면 같은 줄(pt)


@dataclass
class Table:
    page: int                       # 1부터
    bbox: Tuple[float, float, float, float]
    method: str                     # lines | words
    rows: List[List[str]]           # 정규화한 셀 문자열(빈 칸은 "")


@dataclass
class Cell:
    size: int
    ratio: int                      # 가산을 반영한 실제 비율
    amount: int
    page: int
    method: str
    adder: int = 0                  # 머리글 비율에 더한 가산(%p)


@dataclass
class Grid:
    """소득 기준표 하나를 해석한 결과."""
    page: int
    method: str
    cells: List[Cell] = field(default_factory=list)
    dropped: int = 0                # 가산 폭을 정하지 못해 버린 칸


def money(text: str) -> Optional[int]:
    m = MONEY.match(text or "")
    return int(m.group(1).replace(",", "")) if m else None


def _norm(text) -> str:
    return sv.normalize(text or "").replace("퍼센트포인트", "%p").replace("퍼센트", "%")     # SH: '소득의 100퍼센트'


# ------------------------------------------------------------------ T1 표 읽기
def _inside(page, bbox):
    """쪽 밖으로 삐져나온 표 영역(N61 p.5 — 표 선이 쪽 경계를 넘음)은 쪽 안으로 잘라 읽는다. within_bbox는 쪽 밖 영역이면 ValueError."""
    x0, top, x1, bottom = page.bbox
    return page.within_bbox((max(bbox[0], x0), max(bbox[1], top), min(bbox[2], x1), min(bbox[3], bottom)))


def _words_rows(page, bbox) -> List[List[str]]:
    """표 영역의 글자를 줄로 묶고 금액 열 위치로 칸을 나눈다. 첫 칸 = 첫 금액 열 왼쪽 글자(행 머리)."""
    words = _inside(page, bbox).extract_words(x_tolerance=1.5, y_tolerance=2)
    lines: List[List[dict]] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) <= LINE_GAP:
            lines[-1].append(w)
        else:
            lines.append([w])
    centers = sorted((w["x0"] + w["x1"]) / 2 for line in lines for w in line if money(_norm(w["text"])))
    if not centers:
        return []
    cols: List[List[float]] = [[centers[0]]]
    for c in centers[1:]:
        (cols[-1].append(c) if c - cols[-1][-1] <= COL_GAP else cols.append([c]))
    anchors = [sum(c) / len(c) for c in cols]
    half = min((b - a for a, b in zip(anchors, anchors[1:])), default=80.0) / 2
    rows = []
    for line in lines:
        row = [""] * (len(anchors) + 1)
        for w in sorted(line, key=lambda w: w["x0"]):
            x = (w["x0"] + w["x1"]) / 2
            j = min(range(len(anchors)), key=lambda k: abs(anchors[k] - x))
            slot = j + 1 if abs(anchors[j] - x) <= half else 0
            if slot == 0 and x > anchors[-1]:
                continue                        # 표 오른쪽 바깥 설명
            row[slot] += _norm(w["text"])
        rows.append(row)
    return rows


def read_tables(pdf, pages: Iterable[int]) -> List[Table]:
    """pdf(경로 또는 바이트)의 지정 쪽(1부터)에서 금액이 든 표를 두 방법으로 읽는다."""
    import pdfplumber
    src = io.BytesIO(pdf) if isinstance(pdf, (bytes, bytearray)) else str(pdf)
    out: List[Table] = []
    with pdfplumber.open(src) as doc:
        for no in sorted(set(pages)):
            if not 1 <= no <= len(doc.pages):
                continue
            page = doc.pages[no - 1]
            for t in page.find_tables():
                rows = [[_norm(c) for c in r] for r in t.extract()]
                if not any(money(c) for r in rows for c in r) and not any(
                        money(_norm(w["text"])) for w in _inside(page, t.bbox).extract_words()):
                    continue
                out.append(Table(no, tuple(t.bbox), "lines", rows))
                out.append(Table(no, tuple(t.bbox), "words", _words_rows(page, t.bbox)))
    return out


# ------------------------------------------------------------------ 소득 기준표 해석
def _first_money(row: List[str]) -> Optional[int]:
    return next((j for j, c in enumerate(row) if money(c)), None)


def _one_ratio(text: str) -> Optional[int]:
    found = set(RATIO.findall(text))
    return int(found.pop()) if len(found) == 1 else None


def _raw_cells(t: Table) -> List[Tuple[int, int, int, Optional[int]]]:
    """(가구원수, 비율, 금액, 가산). 가산 None = 머리글 비율이 1·2인 가산 전 값일 수 있어 풀어야 함(가구원수가 열인 표),
    0 = 칸의 비율이 확정(비율이 열인 표·한 줄 표)."""
    rows = t.rows
    first = next((i for i, r in enumerate(rows) if _first_money(r) is not None), None)
    if first is None:
        return []
    col_size: Dict[int, int] = {}
    col_adder: Dict[int, int] = {}
    col_ratio: Dict[int, int] = {}
    col_size_ratio: Dict[int, Dict[int, int]] = {}
    for j in range(max(len(r) for r in rows)):
        cells = [r[j] for r in rows[:first] if j < len(r)]
        head = "".join(cells)                  # 머리글이 여러 줄로 나뉜 표: '2인가구' / '(+10p%)'
        if SIZE.match(head):
            col_size[j] = int(SIZE.match(head).group(1))
            if ADDER.search(head):
                col_adder[j] = int(ADDER.search(head).group(1))
        ratio = [m.group(1) for m in map(HEAD_RATIO.fullmatch, cells) if m]
        per = PER_SIZE.search(head)
        if per:                                # 머리글이 가구원수별 실제 비율을 괄호로 적은 표(LH 고령자복지주택)
            col_ratio[j] = int(per.group(1))
            col_size_ratio[j] = {int(a): int(b) for a, b in SIZE_RATIO.findall(per.group(2))}
        elif len(ratio) == 1:
            col_ratio[j] = int(ratio[0])
    by_size = len(col_size) >= 3
    by_ratio = len(col_ratio) >= 2 and not by_size
    out = []
    for r in rows[first:]:
        k = _first_money(r)
        if k is None:
            continue
        head = r[:k]
        size = next((int(SIZE.match(c).group(1)) for c in head if SIZE.match(c)), None)
        if by_size:
            ratio = _one_ratio("".join(head))
            if ratio is not None:
                out += [(col_size[j], ratio, money(c), col_adder.get(j)) for j, c in enumerate(r)
                        if j in col_size and money(c)]
        elif by_ratio:
            if size is not None:
                out += [(size, col_size_ratio.get(j, {}).get(size, col_ratio[j]), money(c), 0) for j, c in enumerate(r)
                        if j in col_ratio and money(c)]
        else:   # 한 줄에 '1인 | 4,576,036원 이하 | 120%' (N3 p.5)
            ratios = [int(x) for c in r[k + 1:] for x in RATIO.findall(c)]
            if size is not None and len(ratios) == 1 and sum(1 for c in r if money(c)) == 1:
                out.append((size, ratios[0], money(r[k]), 0))
    return out


def _interval(amount: int, ratio: int) -> Tuple[float, float]:
    """금액이 기준액 × 비율의 반올림 또는 버림일 때 가능한 기준액 구간."""
    return (amount - 0.5) * 100 / ratio, (amount + 1) * 100 / ratio


def _fits(pairs: List[Tuple[int, int]]) -> bool:
    lo = max(_interval(a, r)[0] for r, a in pairs)
    hi = min(_interval(a, r)[1] for r, a in pairs)
    return lo <= hi


def income_cells(t: Table) -> Grid:
    """표 하나 → 소득 기준표 칸. 가산이 정해지지 않은 1·2인 칸은 같은 가구원수의 두 칸 이상으로 가산 폭을 푼다
    (0·10·20%p 중 하나만 맞아야 한다 — 못 풀면 그 가구원수 칸은 버린다)."""
    grid = Grid(t.page, t.method)
    raw = _raw_cells(t)
    for s in sorted({z for z, _, _, _ in raw}):
        items = [(r, a, ad) for z, r, a, ad in raw if z == s]
        given = {ad for _, _, ad in items if ad is not None}
        if given:
            choice = given.pop() if len(given) == 1 else None
        elif s >= 3:
            choice = 0
        else:
            ok = [ad for ad in (0, 10, 20) if len(items) >= 2 and _fits([(r + ad, a) for r, a, _ in items])]
            choice = ok[0] if len(ok) == 1 else None
        if choice is None:
            grid.dropped += len(items)
            continue
        grid.cells += [Cell(s, r + choice, a, t.page, t.method, choice) for r, a, _ in items]
    return grid


# ------------------------------------------------------------------ T2 검증
def consistent(grid: Grid) -> Optional[bool]:
    """같은 가구원수 칸들이 한 기준액으로 설명되는가. 두 칸 이상인 가구원수가 없으면 None(확인 불가)."""
    groups: Dict[int, List[Tuple[int, int]]] = {}
    for c in grid.cells:
        groups.setdefault(c.size, []).append((c.ratio, c.amount))
    checked = [pairs for pairs in groups.values() if len({r for r, _ in pairs}) >= 2]
    if not checked:
        return None
    return all(_fits(pairs) for pairs in checked)


def cross_check(grid: Grid, page_text: str) -> List[Cell]:
    """pypdf 텍스트(정규화)에 없는 금액의 칸 — 비어 있어야 한다."""
    return [c for c in grid.cells if f"{c.amount:,}" not in page_text]


def agree(a: Grid, b: Grid) -> Tuple[int, int]:
    """두 방법이 함께 낸 (가구원수, 비율) 칸 수와 그중 금액이 다른 칸 수."""
    ma = {(c.size, c.ratio): c.amount for c in a.cells}
    mb = {(c.size, c.ratio): c.amount for c in b.cells}
    both = set(ma) & set(mb)
    return len(both), sum(1 for k in both if ma[k] != mb[k])


def merge(grids: List[Grid]) -> Tuple[List[Cell], int]:
    """같은 쪽 여러 격자의 칸을 합친다. 같은 (쪽, 가구원수, 비율)에 다른 금액이 나오면 그 칸은 버리고 충돌로 센다."""
    seen: Dict[Tuple[int, int, int], set] = {}
    keep: Dict[Tuple[int, int, int], Cell] = {}
    for g in grids:
        if consistent(g) is False:
            continue
        for c in g.cells:
            key = (c.page, c.size, c.ratio)
            seen.setdefault(key, set()).add(c.amount)
            keep.setdefault(key, c)
    conflicts = {k for k, v in seen.items() if len(v) > 1}
    return [c for k, c in keep.items() if k not in conflicts], len(conflicts)


def load_references() -> Dict[str, dict]:
    out = {}
    for path in sorted((sv.RULES / "reference").glob("income_standard*.json")):
        ref = json.loads(path.read_text(encoding="utf-8"))
        if ref.get("status") != "CANDIDATE":        # 운영자 승인 전 후보가 잘못 들어와도 대조 기준으로 쓰지 않는다
            out[path.stem] = ref
    return out


@dataclass
class Family:
    """같은 기준·연도의 등록 기준표 묶음(예: 도시근로자 2025 = 행복주택·국민임대·영구임대·매입임대 표).
    비율 열이 달라도 가구원수별 100% 기준액은 같다 — 칸마다 기준액 × 비율로 맞는지 본다."""
    name: str
    base: Dict[int, Tuple[float, float]] = field(default_factory=dict)     # 1~6인 100% 기준액 구간
    rows: Dict[Tuple[int, int], int] = field(default_factory=dict)          # 7인 이상: 원문 표 행 그대로
    adder7: int = 0                                                         # 7인 이상 = 6인 + 1인당 가산(그 규칙의 공고)


def _ref_family(rid: str, ref: dict) -> Family:
    name = f"{'기준중위소득' if '중위' in ref.get('label', '') else '도시근로자'} {ref.get('year_basis')}"
    f = Family(name, adder7=int(ref.get("per_person_adder_7plus") or 0))
    for size, row in ref["table"].items():
        for ratio, v in row.items():
            s, r = int(size), int(ratio)
            if s >= 7:
                f.rows[(s, r)] = v
                continue
            lo, hi = _interval(v, r)
            old = f.base.get(s, (lo, hi))
            f.base[s] = (max(old[0], lo), min(old[1], hi))
    return f


def families(refs: Dict[str, dict]) -> List[Family]:
    """같은 기준·연도이면서 가구원수별 기준액이 서로 맞는 기준표끼리 묶는다. 맞지 않는 표(신혼희망타운 분양의 '3인 이하' 행처럼
    다른 기준액을 쓰는 표)는 따로 묶는다 — 한 표 때문에 묶음 전체의 기준액이 깨지지 않게."""
    out: List[Family] = []
    for rid, ref in refs.items():
        f = _ref_family(rid, ref)
        home = next((g for g in out if g.name.split(" (")[0] == f.name and all(
            max(g.base[s][0], f.base[s][0]) <= min(g.base[s][1], f.base[s][1]) for s in set(g.base) & set(f.base))), None)
        if home is None:
            f.name = f.name if not any(g.name == f.name for g in out) else f"{f.name} ({rid})"
            out.append(f)
            continue
        for s, (lo, hi) in f.base.items():
            old = home.base.get(s, (lo, hi))
            home.base[s] = (max(old[0], lo), min(old[1], hi))
        home.rows.update(f.rows)
        home.adder7 = max(home.adder7, f.adder7)
    return out


def predicts(f: Family, size: int, ratio: int, amount: int) -> bool:
    lo, hi = _interval(amount, ratio)
    if size in f.base:
        blo, bhi = f.base[size]
        return max(lo, blo) <= min(hi, bhi)
    if f.rows.get((size, ratio)) == amount:
        return True
    if f.adder7 and 6 in f.base:                 # 7인 이상 = 6인 기준액 + 1인당 가산 × 추가 인원
        blo, bhi = (x + f.adder7 * (size - 6) for x in f.base[6])
        return max(lo, blo) <= min(hi, bhi)
    return False


def compare_reference(cells: List[Cell], fams: List[Family]) -> Dict[str, List[Cell]]:
    """칸 단위 대조. 한 쪽에 기준이 다른 표가 섞이기도 한다(분양: 일반 표 + '3인 이하' 표) — 칸마다 모든 기준 묶음으로 본다.
    - same: 어느 묶음으로든 제 칸(가구원수·비율)과 맞음
    - misplaced(**틀린 칸**): 어느 묶음으로도 제 칸과는 안 맞는데 같은 쪽의 다른 칸 위치 값과 맞음 — 위치를 잘못 읽은 것
    - other: 어느 칸으로도 설명되지 않음(다른 연도·다른 기준의 표, 또는 기준표에 없는 규칙)"""
    out = {"same": [], "misplaced": [], "other": []}
    ratios_by_page: Dict[int, set] = {}
    for c in cells:
        ratios_by_page.setdefault(c.page, set()).add(c.ratio)
    for c in cells:
        if any(predicts(f, c.size, c.ratio, c.amount) for f in fams):
            out["same"].append(c)
        elif any(predicts(f, s, r, c.amount) for f in fams for s in range(1, 9) for r in ratios_by_page[c.page]
                 if (s, r) != (c.size, c.ratio)):
            out["misplaced"].append(c)
        else:
            out["other"].append(c)
    return out
