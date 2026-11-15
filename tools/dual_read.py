# -*- coding: utf-8 -*-
"""dual_read.py — 공고문 핵심 값 이중 읽기(R1, docs/13 2-1 'LLM 보조 검토', docs/09 §22).

결정론 추출(sheet_extract → 규칙 문서)과 **다른 방법(LLM이 원문만 보고)** 으로 핵심 값을 한 번 더 읽어 조건마다 대조한다.
판정은 하지 않는다 — 대조 결과(일치 / 불일치 / 답 없음)는 공고 관문의 신호일 뿐이다(LLM 혼자 '지원 가능'을 만들지 못함).

이 파일의 0단계: 규칙 문서(등록 규칙 또는 자동 분석 초안) → 조건별 핵심 값 `facts(doc)`.
- 비교 단위 = (계층, 조건 키). 조건 키는 조건 id에서 공고 번호를 뗀 것(N30-G-assets → G-assets — 초안·등록이 같은 생성 틀이면 같다).
- 항목(kind): income(소득 비율 %·소득 상한 금액) · assets(총자산·부동산) · car(자동차) · date(기준일 리터럴) · region(지역 목록) · age(나이 경계).
- 값은 조건식의 리터럴과, 조건이 가리키는 결정표(`table`)에서 그 조건이 쓰는 출력(`term`) 열의 값 전부(가구원수·자녀 수별로 여럿).
"""
import re
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

KINDS = ("income", "assets", "car", "date", "region", "age")
REGION_FIELDS = ("residence_area", "school_area", "workplace_area", "income_base_area", "spouse_residence_area")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

Key = Tuple[str, str]                      # (계층, 조건 키)


def kind_of(field: str) -> Optional[str]:
    parts = set((field or "").split("/"))
    if parts & {"monthly_income", "household_income", "parents_monthly_income"} or "income(" in (field or ""):
        return "income"
    if parts & {"total_assets", "parents_total_assets", "real_estate_value"}:
        return "assets"
    if parts & {"car_value", "parents_car_value"}:
        return "car"
    if parts & set(REGION_FIELDS):
        return "region"
    if parts & {"age", "age_or_social_rookie"}:
        return "age"
    return None


def cond_key(cid: str) -> str:
    return cid.split("-", 1)[1] if "-" in cid else cid


def _walk(x, out: dict):
    """조건식에서 리터럴·term 이름·지역 목록·날짜를 모은다."""
    if isinstance(x, dict):
        if "date" in x and isinstance(x["date"], str) and DATE.match(x["date"]):
            out["dates"].add(x["date"])
        if "term" in x:
            out["terms"].add(x["term"])
        if "in" in x and isinstance(x["in"], list) and len(x["in"]) == 2:
            var, vals = x["in"]
            if isinstance(var, dict) and var.get("var") in REGION_FIELDS and isinstance(vals, list):
                out["regions"].add(frozenset(vals))
        if "lookup" in x and isinstance(x["lookup"], list) and len(x["lookup"]) == 3 and isinstance(x["lookup"][2], int):
            out["ratios"].add(x["lookup"][2])
        for k, v in x.items():
            if k in ("review_if_true", "detail", "code", "unknown_values"):
                continue
            _walk(v, out)
    elif isinstance(x, list):
        for v in x:
            _walk(v, out)
    elif isinstance(x, int) and not isinstance(x, bool):
        out["ints"].add(x)


def _term_values(doc: dict, table: Optional[str], terms: Iterable[str]) -> Dict[str, set]:
    t = (doc.get("tables") or {}).get(table or "")
    if not t:
        return {}
    outs = t.get("outputs", [])
    got: Dict[str, set] = {}
    for name in terms:
        if name not in outs:
            continue
        j = outs.index(name)
        for row in t.get("rows", []):
            out = row.get("out")
            if isinstance(out, list) and j < len(out) and isinstance(out[j], int) and not isinstance(out[j], bool):
                got.setdefault(name, set()).add(out[j])
    return got


def _values(doc: dict, cond: dict, kind: str) -> FrozenSet:
    acc = {"ints": set(), "dates": set(), "terms": set(), "regions": set(), "ratios": set()}
    _walk(cond.get("check"), acc)
    for r in cond.get("readings", []) or []:
        _walk(r, acc)
    tv = _term_values(doc, cond.get("table"), acc["terms"])
    nums = set(acc["ints"]) | {v for vs in tv.values() for v in vs}
    if kind == "income":
        ratios = set(acc["ratios"]) | {v for k, vs in tv.items() if k.startswith("ratio") for v in vs}
        ratios |= {n for n in acc["ints"] if 30 <= n <= 300}
        return frozenset({("%", r) for r in ratios if 30 <= r <= 300} | {("원", n) for n in nums if n >= 1_000_000})
    if kind in ("assets", "car"):
        return frozenset(n for n in nums if n >= 1_000_000)
    if kind == "date":
        return frozenset(acc["dates"])
    if kind == "region":
        return frozenset(r for s in acc["regions"] for r in s)
    if kind == "age":
        return frozenset(n for n in acc["ints"] if 10 <= n <= 100)
    return frozenset()


def _conditions(conds: List[dict]):
    for c in conds or []:
        yield c
        for tr in c.get("tracks", []) or []:
            yield from _conditions(tr.get("conditions", []))


def facts(doc: dict) -> Dict[Key, Dict]:
    """규칙 문서 → {(계층, 조건 키): {'kind', 'values', 'page'}}. 날짜 리터럴은 어느 조건에 있든 date 항목으로 따로 센다."""
    out: Dict[Key, Dict] = {}
    for layer, ld in (doc.get("layers") or {}).items():
        for c in _conditions(ld.get("conditions", [])):
            if "check" not in c:
                continue
            page = (c.get("source") or {}).get("page")
            kind = kind_of(c.get("field", ""))
            if kind:
                vals = _values(doc, c, kind)
                if vals:
                    out[(layer, cond_key(c["id"]))] = {"kind": kind, "values": vals, "page": page}
            dates = _values(doc, c, "date")
            if dates and kind != "date":
                out[(layer, cond_key(c["id"]) + "#date")] = {"kind": "date", "values": dates, "page": page}
    return out


def layers(doc: dict) -> FrozenSet[str]:
    return frozenset((doc.get("layers") or {}).keys())


# ------------------------------------------------------------------ 1단계: 원문 글자 형태 · LLM 읽기 · 대조 신호
def _won(n: int) -> List[str]:
    """금액 n원이 원문에 적힐 수 있는 형태(정규화 텍스트 — 띄어쓰기 없음)."""
    forms = [f"{n:,}"]
    if n % 10_000 == 0:
        man = n // 10_000
        forms.append(f"{man:,}만")
        eok, rest = divmod(man, 10_000)
        if eok:
            forms.append(f"{eok}억{rest:,}만" if rest else f"{eok}억")
            if rest:
                forms.append(f"{eok}.{str(rest).rstrip('0').zfill(4).rstrip('0') or '0'}억" if rest % 1000 == 0 else "")
    if n % 1_000_000 == 0:
        forms.append(f"{n // 1_000_000:,}백만")
    if n % 1000 == 0:
        forms.append(f"{n // 1000:,}천")
    return [f for f in forms if f]


def text_forms(kind: str, v) -> List[str]:
    if kind in ("assets", "car") or (kind == "income" and isinstance(v, tuple) and v[0] == "원"):
        return _won(v[1] if isinstance(v, tuple) else v)
    if kind == "income":
        return [f"{v[1]}%", f"{v[1]}퍼센트"]
    if kind == "date":
        y, m, d = v.split("-")
        return [f"{y}.{int(m)}.{int(d)}", f"{y}.{m}.{d}", f"{y}년{int(m)}월{int(d)}일", f"{y[2:]}.{int(m)}.{int(d)}",
                f"{y[2:]}.{m}.{d}"]
    if kind == "age":
        return [f"만{v}세", f"{v}세"]
    if kind == "region":
        return [v, v.replace("특별시", "").replace("광역시", "").replace("특별자치도", "").replace("특별자치시", "")]
    return [str(v)]


def _region_groups() -> Dict[str, List[str]]:
    import json
    from pathlib import Path
    g = json.loads((Path(__file__).resolve().parent.parent / "rules/reference/regions.json").read_text(encoding="utf-8"))["groups"]
    out = {k: list(v) for k, v in g.items()}
    metro = [n for k, v in g.items() if k in ("광역시도", "경기도") for n in v]
    out["수도권"] = metro
    return out


def _group_aliases(name: str) -> List[str]:
    """시·군 이름이 속한 묶음을 원문이 부르는 이름('경기도'·'경기'·'수도권')."""
    out = []
    for g, members in _region_groups().items():
        if name in members and g != "광역시도":
            out += [g, g.replace("도", "")] if g.endswith("도") else [g]
    return out


NUM_PAREN = re.compile(r"\((\d[\d,.]*)\)")         # '(345)백만원'·'(4,542)만원'(LH 국민임대) — 괄호를 벗겨 대조


def unparen(text: str) -> str:
    return NUM_PAREN.sub(lambda m: m.group(1), text)


def in_text(kind: str, v, text: str) -> bool:
    text = unparen(text)
    if kind == "region" and any(a in text for a in _group_aliases(v)):
        return True
    return any(f and f in text for f in text_forms(kind, v))


MONEY_RX = re.compile(r"(?:(\d+(?:\.\d+)?)억)?(?:([\d,]+)백만)?(?:([\d,]+)만)?(?:([\d,]+)천)?(?:([\d,]{5,}))?원")


def parse_value(kind: str, s: str):
    """LLM이 적은 값 문자열 → 비교용 값(못 읽으면 None)."""
    import source_verify as sv
    t = unparen(sv.normalize(s or ""))
    if kind in ("assets", "car"):
        m = MONEY_RX.search(t + ("" if t.endswith("원") else "원"))
        if not m or not any(m.groups()):
            return None
        eok, bman, man, chun, won = m.groups()
        n = int(float(eok) * 100_000_000) if eok else 0
        n += int(bman.replace(",", "")) * 1_000_000 if bman else 0
        n += int(man.replace(",", "")) * 10_000 if man else 0
        n += int(chun.replace(",", "")) * 1000 if chun else 0
        n += int(won.replace(",", "")) if won else 0
        return n or None
    if kind == "income":
        m = re.search(r"(\d{2,3})(?:%|퍼센트)", t)
        if m:
            return ("%", int(m.group(1)))
        n = parse_value("assets", s)                  # 비율 대신 상한 금액을 적은 표(SH 소득표 등)
        return ("원", n) if n and n >= 1_000_000 else None     # 1인당 가산액(57만 원 등)은 상한이 아님
    if kind == "date":
        m = re.search(r"(\d{2,4})[.년-]\s*(\d{1,2})[.월-]\s*(\d{1,2})", t)
        if not m:
            return None
        y = int(m.group(1))
        y = y + 2000 if y < 100 else y
        return f"{y:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if kind == "age":
        m = re.search(r"(\d{2})세", t)
        return int(m.group(1)) if m else None
    if kind == "region":
        return region_name(t)
    return None


def region_name(t: str) -> Optional[str]:
    """LLM이 적은 지역 → 표준 이름(rules/reference/regions.json). '의정부'·'서울'처럼 줄여 적어도 하나로 정해지면 그 이름."""
    import json
    from pathlib import Path
    names = [n for g in json.loads((Path(__file__).resolve().parent.parent / "rules/reference/regions.json")
                                   .read_text(encoding="utf-8"))["groups"].values() for n in g]
    if t in names:
        return t
    groups = _region_groups()
    for g in groups:
        if t in (g, g.replace("도", "") if g.endswith("도") else g) and g != "광역시도":
            return "묶음:" + g                          # '경기도'·'수도권' — 비교 때 구성 시·군으로 펼친다
    hit = [n for n in names if text_forms("region", n)[1] == t or n.startswith(t)] if len(t) >= 2 else []
    return hit[0] if len(hit) == 1 else None


MONEY_TXT = r"\(?[\d,.]+\)?(?:억[\d,]*만?|백만|만|천)?원"
QUESTIONS = {   # (묻는 말, 쪽 고르기 — 키워드 바로 뒤에 값이 붙은 곳, 인용에 있어야 할 낱말)
    "assets": ("총자산(또는 부동산) 기준 금액 — 'OO원 이하' 같은 상한 금액. 출산자녀 수·가구원수별로 다르면 모두",
               r"(?:총자산|자산|부동산)[^\d]{0,40}" + MONEY_TXT, r"자산|부동산"),
    "car": ("자동차가액 기준 금액 — 'OO원 이하' 같은 상한 금액. 출산자녀 수별로 다르면 모두",
            r"자동차[^\d]{0,40}" + MONEY_TXT, r"자동차|차량"),
    "income": ("월평균소득 기준 비율(%) — '월평균소득의 OO% 이하' 같은 비율. 맞벌이·가구원수별로 다르면 모두",
               r"소득[^\d]{0,40}\d{2,3}%", r"소득"),
    "date": ("혼인신고일·자녀 출생일·졸업일 등 자격을 가르는 기준 날짜('YYYY.M.D. 이후' 같은 날짜)",
             r"\d{2,4}\.\d{1,2}\.\d{1,2}\.?(?:\(\S\))?이후", r"이후|이전|출생|혼인|졸업"),
    "region": ("신청할 수 있는 거주 지역(1순위 등 지역 요건에 적힌 시·도·시군 이름)", r"(?:거주|소재)[^\d]{0,30}(?:시|도|군)", r"거주|소재|지역"),
    "age": ("나이 기준('만 OO세 이상/이하')", r"만\d{2}세", r"세"),
}
READ_SYSTEM = ("너는 한국 공공주택 입주자모집공고문에서 자격 기준 값을 찾아 적는 도구다. 판단·계산·추측을 하지 말고 공고문에 적힌 값만 적는다. "
               "값마다 그 값이 들어 있는 원문 구절을 **글자 그대로** 짧게 복사한다. 찾지 못하면 빈 목록.")
SCHEMA = {"type": "object", "properties": {"values": {"type": "array", "items": {
    "type": "object", "properties": {"value": {"type": "string"}, "quote": {"type": "string"}, "page": {"type": "integer"}},
    "required": ["value", "quote", "page"]}}}, "required": ["values"]}


def pick_pages(norm_pages: List[str], kind: str, layer: str, top: int = 2) -> List[int]:
    """결정론 근거 쪽과 무관하게 — 그 항목 키워드 바로 뒤에 값(금액·비율·날짜)이 붙은 곳이 많은 쪽(계층 이름이 있으면 가산)."""
    rx = re.compile(QUESTIONS[kind][1])
    lay = re.sub(r"\(.*?\)", "", layer)
    score = [(len(rx.findall(t)) * (2 if lay and lay in t else 1), i + 1) for i, t in enumerate(norm_pages)]
    return [p for s, p in sorted(score, reverse=True)[:top] if s > 0]


def near(kind: str, v, quote: str, must: str) -> bool:
    """값 글자가 인용 안에서 항목 낱말 뒤 40자 안에 있어야 그 항목의 값으로 인정(표 한 줄에 '총자산 …원 자동차 …원'이 함께 있을 때
    자동차 값으로 총자산 금액을 쓰지 않게). 날짜·지역·나이는 인용 안에 낱말과 값이 함께 있으면 된다."""
    if not in_text(kind, v, quote):
        return False
    if kind not in ("assets", "car", "income"):
        return bool(re.search(must, quote))
    for m in re.finditer(must, quote):
        tail = quote[m.end():m.end() + 60]
        if in_text(kind, v, tail):
            return True
    return False


def llm_read(slot, raw_pages: List[str], norm_pages: List[str], layer: str, kind: str) -> List[Tuple[object, str, int]]:
    """LLM이 원문만 보고 읽은 값 → [(값, 인용, 쪽)] — 인용이 그 쪽 원문에 글자 그대로 있고 값 글자가 인용 안에 있는 것만."""
    import source_verify as sv
    from llm_slot import page_block
    pages = pick_pages(norm_pages, kind, layer)
    if not pages:
        return []
    what, _, must = QUESTIONS[kind]
    prompt = (f"공급 대상(계층): {layer}\n찾을 것: {what}\n\n위 계층에 적용되는 값만 적어라(다른 계층 값은 빼라). "
              f"값은 최대 6개, 각 값의 원문 구절(40자 이내, 값이 들어 있는 부분)과 쪽 번호([p.N])를 함께.\n\n{page_block(raw_pages, pages, 2500, layer + ' ' + what)}")
    out = slot.ask(prompt, SCHEMA)
    got = []
    for item in (out or {}).get("values", []) if isinstance(out, dict) else []:
        quote = sv.normalize(str(item.get("quote", "")))
        qplain = unparen(quote)
        page = item.get("page") if isinstance(item.get("page"), int) else 0
        where = [p for p in ([page] if 1 <= page <= len(norm_pages) else []) + pages if quote and quote in norm_pages[p - 1]]
        v = parse_value(kind, str(item.get("value", "")))
        if not where or v is None or not near(kind, v, qplain, must):
            continue                                   # 원문에 없는 인용·값 = 답 없음(지어낸 답을 쓰지 않음)
        got.append((v, quote, where[0]))
    return got


class OllamaReader:
    """읽기 슬롯(모델 바꿔 끼우기) — llm_slot.OllamaSlot과 같은 캐시·전송, 시스템 지시만 '값 읽기'로. ask(prompt, schema) → dict|None."""

    def __init__(self, model: Optional[str] = None, **kw):
        from llm_slot import DEFAULT_MODEL, OllamaSlot
        self._s = OllamaSlot(model or DEFAULT_MODEL, **kw)
        self.name = self._s.name

    def ask(self, prompt: str, schema: dict) -> Optional[dict]:
        import llm_slot
        old, llm_slot.SYSTEM = llm_slot.SYSTEM, READ_SYSTEM     # 캐시 키에 시스템 지시가 들어가 문장 찾기 답과 섞이지 않음
        try:
            return self._s.ask(prompt, schema)
        finally:
            llm_slot.SYSTEM = old

    @property
    def stats(self):
        return {"calls": self._s.calls, "cached": self._s.cached, "failed": self._s.failed, "seconds": round(self._s.seconds, 1)}


class ClaudeReader:
    """Claude API 읽기 슬롯 — 자리만 둔다. 키 사용은 사용자 승인 뒤(docs/13 2-1, 메모 api-key-ask-first)."""

    def __init__(self, *a, **kw):
        raise NotImplementedError("Claude API 읽기는 사용자 승인 뒤 연결합니다")


def reader(name: str):
    """'ollama:gemma4:e2b' · 'gemma4:e2b' → OllamaReader, 'claude:…' → ClaudeReader."""
    if name.startswith("claude"):
        return ClaudeReader(name)
    return OllamaReader(name.split("ollama:", 1)[-1] if name else None)


AGREE, PARTIAL, DISAGREE, NONE = "일치", "부분", "불일치", "답 없음"


def signal(llm_values: Iterable, cond_values: Iterable, layer_values: Iterable, kind: str, text: str) -> str:
    """조건 하나의 신호. 결정론 값을 하나도 빼지 않는다 — 가산을 더한 비율·나이 경계처럼 원문에 숫자로 없는 값이 있으면 '일치'가 될 수 없다(중립). 바꿔 넣은 값이 가려져 '일치'가 되는 일을 막는다.
    - 일치: 이 조건의 (원문에 적힌) 값 전부를 LLM이 읽었고, LLM 값이 모두 이 계층의 결정론 값 안에 있음 — 통과 신호
    - 불일치: LLM이 읽은 값 중 이 계층 결정론 값에 없는 것이 있음 — 보류·대기열 앞으로
    - 부분: LLM 값이 결정론 값 안에 있지만 일부만 읽음 — 중립(일부러 바꾼 한 칸을 '일치'로 넘기지 않게)
    - 답 없음: 중립"""
    V = set(llm_values)
    if kind == "region":                                 # 묶음 이름(경기도·수도권)은 구성 시·군으로 펼친다
        groups = _region_groups()
        V = {m for v in V for m in (groups[v[3:]] if isinstance(v, str) and v.startswith("묶음:") else [v])}

    S = set(cond_values)
    U = set(layer_values) | S
    if not V:
        return NONE
    if not V <= U:
        return DISAGREE
    return AGREE if S and S <= V else PARTIAL


def compare(draft: Dict[Key, Dict], truth: Dict[Key, Dict]) -> Dict[str, List]:
    """초안 facts와 정답(등록) facts 대조 — same / differ / draft_only / truth_only (조건 키 기준)."""
    out = {"same": [], "differ": [], "draft_only": [], "truth_only": []}
    for k in sorted(set(draft) | set(truth)):
        if k not in truth:
            out["draft_only"].append(k)
        elif k not in draft:
            out["truth_only"].append(k)
        elif draft[k]["values"] == truth[k]["values"]:
            out["same"].append(k)
        else:
            out["differ"].append(k)
    return out
