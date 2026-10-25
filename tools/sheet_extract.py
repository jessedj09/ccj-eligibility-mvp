# -*- coding: utf-8 -*-
"""결정론 추출기 + 검증 관문(P1 T3.2, docs/09 §6·§7) — 공고 원문에서 파라미터 시트의 빈칸을 채운다. AI 없음.

원칙
- 값은 원문에서 찾은 것만 쓴다. 날짜는 공고일에서 LH/SH 관행(공고일−N년 당일 / 다음 날)으로 후보를 만들고, **그 날짜가 원문에
  글자로 있을 때만** 채운다. 문장은 형제 공고(같은 템플릿의 정답 시트)의 문장에서 날짜만 이 공고 날짜로 바꿔 원문에 있을 때만 쓴다.
- 특정 공고 전용 문자열(공고 번호·단지 이름 등)을 쓰지 않는다 — 일반 패턴만(tests/test_t32_extract.py가 점검).
- 못 채운 빈칸은 '보류'다. 추출이 틀려도 보류로 빠지게 하는 것이 목표다(틀린 통과 0).

    ext = extract(pages, siblings)     # → {"template", "announcement_date", "params", "fields": {이름: Field}, ...}
    report = gate(ext, pdf, pages)     # 시트로 규칙을 만들어 인용문 대조(찾지 못한 인용문 = 그 조건 보류)
"""
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

import notice_candidates as nc  # noqa: E402
import source_verify as sv  # noqa: E402
import templates as T  # noqa: E402
from rule_engine import years_before  # noqa: E402

HELD, FILLED, ABSENT = "held", "filled", "absent"   # 보류 / 채움 / 원문에 해당 항목이 없음(값 None)


@dataclass
class Field:
    status: str                    # filled / held / absent
    value: object = None
    page: Optional[int] = None
    quote: Optional[str] = None    # 근거(원문 정규화 텍스트 일부)
    how: str = ""                  # 어떻게 찾았는지 / 왜 보류인지


# ------------------------------------------------------------------ 공통 도우미
def _shift(d: date, years: int, plus_one: bool) -> date:
    x = years_before(d, years)
    return x + timedelta(days=1) if plus_one else x


def _date_pattern(d: date) -> str:
    """정규화 텍스트에서 날짜 d를 찾는 패턴 — 2019.6.25 / 2019.06.25 / ’19.6.25 / '19.06.25 등."""
    return (rf"(?:{d.year}|[‘’'`]{d.year % 100:02d})\.0?{d.month}\.0?{d.day}(?!\d)")


def find_date(pages: List[str], d: date, near: str = "") -> Optional[tuple]:
    """날짜 d가 원문에 글자로 있으면 (쪽, 주변 텍스트). near가 주면 그 말이 앞뒤 40자 안에 있는 것만."""
    pat = re.compile(_date_pattern(d))
    for i, t in enumerate(pages, 1):
        for m in pat.finditer(t):
            around = t[max(0, m.start() - 40):m.end() + 40]
            if near and not re.search(near, around):
                continue
            return i, t[max(0, m.start() - 15):m.end() + 15]
    return None


def by_convention(pages, ann: date, years: int, near: str, plus_one: bool) -> Field:
    """발행 기관 관행(LH 혼인·신생아 = 공고일−N년 당일, 6세 이하 = 다음 날 / SH = 모두 다음 날)으로 정한 날짜가 원문에
    near 근처에 글자로 있으면 채운다. 다른 관행의 날짜로 바꿔 시도하지 않는다 — 근처의 다른 기준일(예: 6세 자녀 기준일)을
    혼인 기준일로 잘못 잡지 않게."""
    d = _shift(ann, years, plus_one)
    hit = find_date(pages, d, near)
    if hit:
        return Field(FILLED, d.isoformat(), hit[0], hit[1], f"공고일−{years}년{'+1일' if plus_one else ''}, 원문 확인")
    return Field(HELD, how=f"공고일−{years}년{'+1일' if plus_one else ''} 날짜가 '{near}' 근처에 없음")


def find_text(pages, pattern: str) -> Optional[tuple]:
    rx = re.compile(pattern)
    for i, t in enumerate(pages, 1):
        m = rx.search(t)
        if m:
            return i, m.group(0)
    return None


def on_page(pages, text: str) -> Optional[int]:
    n = sv.normalize(text)
    for i, t in enumerate(pages, 1):
        if n and n in t:
            return i
    return None


# 형제 문장의 날짜를 이 공고 날짜로 바꾸기 — 형식(두 자리 연도·0 채움·띄어쓰기)은 그대로 둔다
_TOKEN = re.compile(r"(?P<pre>[‘’'`])?(?P<y>\d{4}|\d{2})(?P<s1>\.\s?)(?P<m>\d{1,2})(?P<s2>\.\s?)(?P<d>\d{1,2})(?P<dot>\.?)")


def adapt(sentence: str, mapping: Dict[date, date]) -> str:
    def sub(m):
        y = int(m.group("y"))
        y = y if y > 999 else 2000 + y if y < 50 else 1900 + y
        try:
            old = date(y, int(m.group("m")), int(m.group("d")))
        except ValueError:
            return m.group(0)
        new = mapping.get(old)
        if new is None:
            return m.group(0)
        yy = f"{new.year}" if len(m.group("y")) == 4 else f"{new.year % 100:02d}"
        mm = f"{new.month:02d}" if len(m.group("m")) == 2 and m.group("m").startswith("0") else f"{new.month}"
        dd = f"{new.day:02d}" if len(m.group("d")) == 2 and m.group("d").startswith("0") else f"{new.day}"
        return f"{m.group('pre') or ''}{yy}{m.group('s1')}{mm}{m.group('s2')}{dd}{m.group('dot')}"
    return _TOKEN.sub(sub, sentence)


def _role_dates(ann: date) -> Dict[str, date]:
    """문장 속 날짜의 역할 — 형제 공고와 이 공고 사이의 날짜 대응을 만드는 데 쓴다(LH·SH 관행 둘 다)."""
    out = {"ann": ann, "ann-1": ann - timedelta(days=1)}
    for n in (2, 5, 7, 19, 30, 40, 60, 65):
        out[f"-{n}"] = _shift(ann, n, False)
        out[f"-{n}+1"] = _shift(ann, n, True)
    return out


def date_mapping(old_ann: date, new_ann: date) -> Dict[date, date]:
    old, new = _role_dates(old_ann), _role_dates(new_ann)
    return {old[k]: new[k] for k in old}


def loose_pattern(sentence: str) -> Optional[re.Pattern]:
    """형제 문장에서 숫자와 로마 숫자(Ⅰ·Ⅱ — 정규화하면 I·II)만 자유롭게 둔 패턴. 문장이 짧으면(15자 미만) 쓰지 않는다."""
    n = sv.normalize(sentence)
    if len(re.sub(r"[\dIVX.,~%]", "", n)) < 15:
        return None
    out, i = [], 0
    while i < len(n):
        if n[i].isdigit():
            while i < len(n) and n[i].isdigit():
                i += 1
            out.append(r"\d+")
        elif n[i] in "IVX":
            while i < len(n) and n[i] in "IVX":
                i += 1
            out.append("[IVX]+")
        else:
            out.append(re.escape(n[i]))
            i += 1
    return re.compile("".join(out))


def loose_find(pages, sentence: str) -> Optional[tuple]:
    """숫자·로마 숫자만 다른 같은 문장이 원문에 **하나의 표현으로만** 있으면 (쪽, 원문 표현)."""
    rx = loose_pattern(sentence)
    if rx is None:
        return None
    hits = {}
    for i, t in enumerate(pages, 1):
        for m in rx.finditer(t):
            hits.setdefault(m.group(0), i)
    if len(hits) == 1:
        text, page = next(iter(hits.items()))
        return page, text
    return None


def adapt_quotes(pages, ann: date, siblings: List[dict], key_path) -> Dict[str, Field]:
    """형제 시트들의 문장(dict)을 이 공고 날짜로 바꿔 원문에 있는 것만 채운다. key_path: 시트 → 문장 dict."""
    keys = []
    for s in siblings:
        for k in key_path(s):
            if k not in keys:
                keys.append(k)
    out = {}
    for k in keys:
        # 보류여도 규칙은 만들 수 있게 형제 문장(날짜 맞춤)을 자리표시로 둔다 — 원문에 없으니 규칙을 만들면 그 조건이
        # '찾지 못한 인용문'으로 드러난다(검증 관문)
        first = next((s for s in siblings if isinstance(key_path(s).get(k), str)), None)
        placeholder = adapt(key_path(first)[k], date_mapping(date.fromisoformat(first["announcement_date"]), ann))             if first else None
        out[k] = Field(HELD, placeholder, how="형제 공고의 문장이 이 공고 원문에 없음")
        for s in siblings:
            src = key_path(s).get(k)
            if not isinstance(src, str):
                continue
            cand = adapt(src, date_mapping(date.fromisoformat(s["announcement_date"]), ann))
            p = on_page(pages, cand)
            if p:
                out[k] = Field(FILLED, cand, p, sv.normalize(cand), f"형제 {s['notice_id']} 문장(날짜 맞춤)")
                break
        if out[k].status == HELD:
            for s in siblings:
                src = key_path(s).get(k)
                hit = loose_find(pages, src) if isinstance(src, str) else None
                if hit:
                    out[k] = Field(FILLED, hit[1], hit[0], hit[1], f"형제 {s['notice_id']} 문장(숫자·Ⅰ/Ⅱ만 다른 원문 표현)")
                    break
    return out


# ------------------------------------------------------------------ 템플릿 정하기
PROGRAM_TEMPLATE = [("청년매입임대", "lh.youth_rental"), ("신혼·신생아 매입임대", None), ("든든전세", "lh.deundeun"),
                    ("장기전세주택2", "sh.jeonse2"), ("장기전세주택", "sh.jeonse"), ("장기미임대", "sh.vacant"),
                    ("미리내집", "sh.newlywed"), ("행복주택", "lh.happy_housing")]


def choose_template(issuer: Optional[str], program: Optional[str]) -> Optional[str]:
    if not program:
        return None
    if "신혼·신생아 매입임대" in program:
        return "sh.newlywed" if issuer == "SH" else "lh.newlywed_rental"
    for key, t in PROGRAM_TEMPLATE:
        if key in program and t:
            return t
    return None


def kind_of(program: str) -> str:
    return "II" if ("Ⅱ" in program or "미리내집" in program) else "I"


# ------------------------------------------------------------------ 템플릿별 추출
def _youth_rental(pages, ann, sib):
    f = {}
    lo, hi = _shift(ann, 40, True), years_before(ann, 19)
    hit = find_text(pages, _date_pattern(lo) + r"\.?~" + _date_pattern(hi) + r"\.?")
    f["birth_range"] = Field(FILLED, hit[1], hit[0], hit[1], "공고일−40년+1일 ~ 공고일−19년, 원문 확인") if hit else \
        Field(HELD, how="청년 출생일 범위가 원문에 없음")
    d30 = _shift(ann, 30, True)
    hit = find_date(pages, d30, "30세")
    f["under30"] = Field(FILLED, re.search(_date_pattern(d30) + r"\.?", hit[1]).group(0), hit[0], hit[1],
                         "공고일−30년+1일, 원문 확인") if hit else Field(HELD, how="만 30세 기준일이 원문에 없음")
    return f


def _newlywed_rental(pages, ann, sib, program):
    f = {"kind": Field(FILLED, kind_of(program), how="사업 유형(제목)에서")}
    f["marriage"] = by_convention(pages, ann, 7, "혼인신고", plus_one=False)
    f["child6"] = by_convention(pages, ann, 7, "출생", plus_one=True)
    f["newborn"] = by_convention(pages, ann, 2, "출생", plus_one=False)
    mq = find_text(pages, r"혼인신고일이[0-9.~‘’'`]{8,30}")
    f["marriage_quote"] = Field(FILLED, mq[1].rstrip("."), mq[0], mq[1], "'혼인신고일이 … ~ …' 문구") if mq else \
        Field(HELD, how="혼인 기간 문구 없음")
    for key, dkey in (("child6_quote", "child6"), ("newborn_quote", "newborn")):
        d = f[dkey]
        if d.status != FILLED:
            f[key] = Field(HELD, how=f"{dkey} 보류")
            continue
        hit = find_text(pages, _date_pattern(date.fromisoformat(d.value)) + r"\.?이후출생[가-힣‧·]{0,12}")
        f[key] = Field(FILLED, hit[1], hit[0], hit[1], "'…이후 출생' 문구") if hit else Field(HELD, how="기준일 문구 없음")
    return f


def _sh_newlywed(pages, ann, sib, program):
    f = {"kind": Field(FILLED, kind_of(program), how="사업 유형(제목)에서")}
    dates = {"marriage": by_convention(pages, ann, 7, "혼인신고", True), "child6": by_convention(pages, ann, 7, "출생", True),
             "newborn": by_convention(pages, ann, 2, "출생", True)}
    minor = by_convention(pages, ann, 19, "출생|미성년", True)
    if minor.status == FILLED:
        dates["minor"] = minor
    f["dates"] = dates
    f["single_parent_minor"] = Field(FILLED, minor.status == FILLED, minor.page, minor.quote,
                                     "지원대상 한부모 미성년 기준일 " + ("있음" if minor.status == FILLED else "없음"))
    same_kind = [s for s in sib if s["params"].get("kind") == f["kind"].value]
    other = [s for s in sib if s not in same_kind]
    f["quotes"] = adapt_quotes(pages, ann, same_kind + other, lambda s: s["params"]["quotes"])
    inc = f["quotes"].get("income")
    if inc is not None and inc.status == FILLED:
        ratio = "70%" if f["kind"].value == "I" else "130%"
        if ratio not in sv.normalize(inc.value):
            f["kind"] = Field(HELD, how=f"소득 문장의 비율이 유형 {f['kind'].value}({ratio})와 다름 — 유형 확인 필요")
    return f


def _jeonse2(pages, ann, sib, program):
    f = {"dates": {"marriage": by_convention(pages, ann, 7, "혼인", True),
                   "five": by_convention(pages, ann, 5, "소유", True)}}
    f["quotes"] = adapt_quotes(pages, ann, sib, lambda s: s["params"]["quotes"])
    f["weak_quote"] = _weak_quote(pages)
    return f


def _weak_quote(pages) -> Field:
    hit = find_text(pages, r"주거약자형주택신청자는.{4,40}?중한개이상의")
    return Field(FILLED, hit[1], hit[0], hit[1], "'주거약자형 주택 신청자는 … 중 한 개 이상의' 문구") if hit else \
        Field(ABSENT, how="주거약자형 주택 신청자격 문구 없음")


def _jeonse(pages, ann, sib, program):
    f = {}
    q = adapt_quotes(pages, ann, sib, lambda s: {k: v for k, v in s["params"]["quotes"].items() if isinstance(v, str)})
    a = find_text(pages, r"가액합산:[0-9,]+만원이하")
    c = find_text(pages, r"보건복지부장관이정하는금액:[0-9,]+만원이하")
    q["assets"] = Field(FILLED, a[1], a[0], a[1], "자산 한도 문구") if a else Field(HELD, how="자산 한도 문구 없음")
    q["car"] = Field(FILLED, c[1], c[0], c[1], "자동차 한도 문구") if c else Field(HELD, how="자동차 한도 문구 없음")
    minor = by_convention(pages, ann, 19, "미성년", True)
    q["minor_date"] = minor
    elderly = find_text(pages, r"만65세이상\[[^\]]{8,30}\]인2인이하무주택세대구성원")
    q["with_elderly"] = Field(FILLED, bool(elderly), elderly[0] if elderly else None, elderly[1] if elderly else None,
                              "고령자 우선공급 문구 " + ("있음" if elderly else "없음"))
    prio = adapt_quotes(pages, ann, sib, lambda s: s["params"]["quotes"].get("priority", {}))
    if elderly:
        prio["elderly"] = Field(FILLED, elderly[1], elderly[0], elderly[1], "고령자 우선공급 문구")
    q["priority"] = prio
    f["quotes"] = q
    f["weak_quote"] = _weak_quote(pages)
    f["income"] = _jeonse_income(pages)
    return f


JS_RATIOS = {"60이하": dict(base=105, c1=115, c2=125, dual=140, ratio="105%(맞벌이 140%)"),
             "60초과": dict(base=150, c1=160, c2=170, dual=200, ratio="150%(맞벌이 200%)")}


def _standard_100() -> Dict[int, int]:
    """등록 소득 기준표(도시근로자 가구원수별 월평균소득)의 100% 금액 — 1·2인은 표의 120%·110%에서 되돌린다."""
    import json
    t = json.loads((sv.RULES / "reference" / "income_standard.json").read_text(encoding="utf-8"))["table"]
    out = {int(k): v["100"] for k, v in t.items() if "100" in v}
    out[1] = round(t["1"]["120"] / 1.2)
    out[2] = round(t["2"]["110"] / 1.1)
    return out


def _round(x: float) -> int:
    return int(x + 0.5)


def _jeonse_income(pages) -> Field:
    """장기전세 면적대별 소득 상한 = 기준 연도 도시근로자 소득 × 비율(원 단위 반올림). 등록 기준표로 계산한 금액이 원문에
    **전부** 있을 때만 채운다(다른 연도 기준표를 쓰는 공고는 금액이 달라 보류). 자산·자동차 한도는 원문 표에서 읽는다."""
    text = "".join(pages)
    base = _standard_100()
    data, missing = {}, []
    for band, r in JS_RATIOS.items():
        rows = {}
        for key, start in (("base", 1), ("c1", 2), ("c2", 3), ("dual", 2)):
            vals = [None if size < start else _round(base[size] * r[key] / 100) for size in range(1, 7)]
            missing += [v for v in vals if v is not None and f"{v:,}" not in text]
            rows[key] = vals
        rows["ratio"] = r["ratio"]
        data[band] = rows
    m = re.search(r"총자산([\d,]+)만원([\d,]+)만원([\d,]+)만원자동차([\d,]+)만원([\d,]+)만원([\d,]+)만원", text)
    if missing or not m:
        why = f"계산한 금액 {len(missing)}개가 원문에 없음(다른 기준 연도일 수 있음)" if missing else "자산·자동차 한도 표 없음"
        return Field(HELD, how="면적대별 소득 상한: " + why)
    nums = [int(x.replace(",", "")) * 10000 for x in m.groups()]
    data["assets"], data["cars"] = nums[:3], nums[3:]
    return Field(FILLED, data, None, m.group(0), "등록 기준표 × 비율로 계산한 금액이 원문에 모두 있음, 자산·자동차는 원문 표")


LAYER_HEAD = re.compile(r"\d-\d\.(?:\([가-힣]{2,4}\))?(대학생|청년|신혼부부·한부모가족|고령자|산업단지근로자|주거급여수급자|"
                        r"지역전략산업종사자|주거약자)(?=계층|가족|입주자모집|■|–|-|\(|일반공급)")
EXTRA = {"고령자": ("elderly", "고령자"), "산업단지근로자": ("industrial", "산업단지 근로자"),
         "주거급여수급자": ("housing_benefit", "주거급여수급자"), "지역전략산업종사자": ("regional", "지역전략산업종사자")}
EXTRA_ARGS = {"elderly": lambda: {"home_quote": T.C3.ELDER_HOME},
              "housing_benefit": lambda: {"home_quote": "현재 무주택세대구성원인 주거급여수급자"},
              "industrial": dict, "regional": dict}


def _happy_housing(pages, ann, sib, program, title_text):
    f = {"base": Field(FILLED, "N1" if "신혼희망타운" in program else "N3", how="사업 유형(신혼희망타운 여부)")}
    heads = {}
    for i, t in enumerate(pages, 1):
        for m in LAYER_HEAD.finditer(t):
            heads.setdefault(m.group(1), i)
    layers = []
    for h in ("대학생", "청년", "신혼부부·한부모가족"):
        if h in heads:
            layers += ["신혼부부", "한부모"] if h == "신혼부부·한부모가족" else [h]
    f["layers"] = Field(FILLED if layers else HELD, layers, how="'N-M. ○○계층' 소제목" if layers else "계층 소제목 없음")
    extra = {}
    for name, (builder, anchor) in EXTRA.items():
        if name in heads:
            extra[name] = dict(builder=builder, args=EXTRA_ARGS[builder](), anchor=anchor, hint=heads[name])
    f["extra_layers"] = Field(FILLED, extra, how="추가 계층 소제목")
    m = find_text(pages, r"(\d{4})\.(\d{1,2})\.(\d{1,2})\.?이후혼인신고")
    lit_m = _near_convention(m, ann, 7)
    f["marriage"] = Field(FILLED, lit_m, m[0], m[1], "'…이후 혼인신고' 리터럴") if lit_m else \
        Field(ABSENT, None, how="혼인 기준일 리터럴 없음 — 공고일에서 LH 관행으로 도출")
    lit_c, hit = None, None
    for i, t in enumerate(pages, 1):
        for mm in re.finditer(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\.?이후출생", t):
            d = _near_convention((i, mm.group(0), mm), ann, 7)
            if d:
                lit_c, hit = d, (i, mm.group(0))
                break
        if lit_c:
            break
    f["child"] = Field(FILLED, lit_c, hit[0], hit[1], "'…이후 출생' 리터럴(공고일−7년 무렵)") if lit_c else \
        Field(ABSENT, None, how="6세 기준일 리터럴 없음 — 공고일에서 도출")
    only_first = find_text(pages, r"이번공고에서는모집하지않음")
    f["region"] = Field(HELD, None, only_first[0], only_first[1], "1순위 지역만 모집 — 계층별 지역 조건 문구는 결정론 추출 미구현") \
        if only_first else Field(ABSENT, {}, how="2·3순위 미모집 문구 없음")
    f["overrides"] = Field(ABSENT, {}, how="템플릿과 표현이 다른 문장은 규칙을 만든 뒤 '찾지 못한 인용문'으로 드러난다")
    f["weak"] = _happy_weak(pages, layers, heads)
    return f


def _near_convention(hit, ann, years):
    if not hit:
        return None
    mobj = hit[2] if len(hit) > 2 else re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", hit[1])
    try:
        d = date(int(mobj.group(1)), int(mobj.group(2)), int(mobj.group(3)))
    except ValueError:
        return None
    return d.isoformat() if abs((d - years_before(ann, years)).days) <= 2 else None


DISABLED = "「장애인복지법」 제2조제2항에 해당하는 장애인"


def _happy_weak(pages, layers, heads) -> Field:
    hit = find_text(pages, r"신혼부부·한부모가족[가-힣의 ]{0,12}요건을모두갖추고아래주거약?자의요건을갖춘(?:사람|자)")
    if hit and {"신혼부부", "한부모"} <= set(layers):
        quotes = [hit[1]]
        if on_page(pages, DISABLED):
            quotes.append(DISABLED)
        return Field(FILLED, dict(bases=["신혼부부", "한부모"], elderly=bool(on_page(pages, "65세이상")), page=hit[0],
                                  quotes=quotes), hit[0], hit[1], "'…요건을 모두 갖추고 아래 주거약자의 요건을 갖춘' 문구")
    if "주거약자" in heads:
        return Field(HELD, None, heads["주거약자"], None, "주거약자 주택형 소제목 — 대상 계층 묶음은 결정론 추출 미구현")
    return Field(ABSENT, None, how="신혼부부·한부모 주거약자 요건 문구 없음(고령자 배정 주거약자용은 고령자 계층으로 판정)")


# ------------------------------------------------------------------ 전체
def extract(pages: List[str], siblings_of=None) -> Dict:
    """siblings_of(template) → 형제 정답 시트 목록(같은 템플릿, 평가 시 다듬기용 공고만)."""
    issuer, program = nc.classify(pages)
    anns = nc.announcement_candidates(pages)
    template = choose_template(issuer, program)
    out = {"template": template, "issuer": issuer, "program": program,
           "announcement_date": Field(FILLED, anns[0]["date"], anns[0]["page"], anns[0]["quote"], "공고일 후보 1순위")
           if anns else Field(HELD, how="공고일을 찾지 못함"), "fields": {}}
    if not template or not anns:
        return out
    ann = date.fromisoformat(anns[0]["date"])
    sib = siblings_of(template) if siblings_of else []
    fn = {"lh.youth_rental": lambda: _youth_rental(pages, ann, sib),
          "lh.newlywed_rental": lambda: _newlywed_rental(pages, ann, sib, program),
          "lh.deundeun": dict, "sh.vacant": dict,
          "sh.newlywed": lambda: _sh_newlywed(pages, ann, sib, program),
          "sh.jeonse2": lambda: _jeonse2(pages, ann, sib, program),
          "sh.jeonse": lambda: _jeonse(pages, ann, sib, program),
          "lh.happy_housing": lambda: _happy_housing(pages, ann, sib, program, pages[0][:200])}[template]
    out["fields"] = fn()
    return out


def _value(x):
    """시트 값. 보류 빈칸은 자리표시 값이 있으면 그대로 쓴다(규칙을 만들 수 있게 — 그 조건은 검증 관문에서 보류로 드러남)."""
    if isinstance(x, Field):
        return x.value
    if isinstance(x, dict):
        return {k: _value(v) for k, v in x.items() if not (isinstance(v, Field) and v.status == HELD and v.value is None)}
    return x


def held_paths(fields, prefix="") -> List[str]:
    out = []
    for k, v in fields.items():
        if isinstance(v, Field) and v.status == HELD:
            out.append(prefix + k)
        elif isinstance(v, dict):
            out += held_paths(v, prefix + k + ".")
    return out


def to_sheet(ext: Dict, nid: str = "NEW") -> Dict:
    """추출 결과 → 파라미터 시트(보류 빈칸은 빠짐 — 그대로는 규칙을 못 만들 수 있다)."""
    params = {k: _value(v) for k, v in ext["fields"].items()}
    params = {k: v for k, v in params.items() if v is not None or k in ("marriage", "child", "weak")}
    if ext["template"] == "lh.happy_housing":
        params.setdefault("region", {})
        params.setdefault("weak", None)
    if ext["template"] in ("sh.jeonse2", "sh.jeonse") and ext["fields"].get("weak_quote") is not None \
            and ext["fields"]["weak_quote"].status != FILLED:
        params.pop("weak_quote", None)
    return {"notice_id": nid, "template": ext["template"], "issuer": ext["issuer"], "program": ext["program"] or "",
            "title": "", "announcement_date": _value(ext["announcement_date"]), "params": params,
            "meta": {"notes": [], "unsupported": []}}


def field_report(ext: Dict) -> Dict:
    def walk(x):
        if isinstance(x, Field):
            return asdict(x)
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        return x
    return {"template": ext["template"], "announcement_date": walk(ext["announcement_date"]), "fields": walk(ext["fields"])}


# ------------------------------------------------------------------ 검증 관문
CRITICAL_QUOTE_KEYS = {"assets", "car", "minor_date", "with_elderly"}


def is_critical(template: str, path: str) -> bool:
    """보류된 빈칸이 판정에 직접 쓰이는 값인지(기준일·한도·계층 구성 등). 인용 위치만 정하는 문장은 아님."""
    head, _, rest = path.partition(".")
    if head == "announcement_date":
        return True
    spec = {p.name: p for p in T.TEMPLATES[template]["params"]}
    p = spec.get(head)
    if p is None:
        return True
    if p.kind == "quotes":
        return rest.split(".")[0] in CRITICAL_QUOTE_KEYS
    if head == "weak":      # 주거약자 변형 계층만 영향 — 그 계층을 만들지 않고(보류) 나머지 계층은 판정한다
        return False
    return p.critical


def _sanity(ext) -> List[str]:
    """값 범위 점검 — 원문에서 찾았더라도 터무니없는 값이면 보류로."""
    problems = []
    ann = ext["announcement_date"]
    if ann.status == FILLED and not (date(2015, 1, 1) <= date.fromisoformat(ann.value) <= date(2035, 12, 31)):
        problems.append("announcement_date: 범위 밖")
    inc = ext["fields"].get("income")
    if isinstance(inc, Field) and inc.status == FILLED:
        if not all(1e8 <= a <= 3e9 for a in inc.value["assets"]) or not all(1e7 <= c <= 2e8 for c in inc.value["cars"]):
            problems.append("income: 자산·자동차 한도 범위 밖")
    return problems


def gate(ext: Dict, pdf, pages: List[str], nid: str = "NEW") -> Dict:
    """추출 시트로 규칙을 만들어 본다. 결과:
    - held: 보류된 빈칸, critical_held: 그중 판정에 직접 쓰이는 것(있으면 이 공고는 자동 판정하지 않는다 — P2 규칙)
    - missing: 원문에서 찾지 못한 인용문(그 조건은 보류), doc: 만들어진 규칙(만들 수 없으면 None, blocked에 이유)"""
    held = held_paths(ext["fields"])
    if ext["announcement_date"].status != FILLED:
        held.insert(0, "announcement_date")
    problems = _sanity(ext)
    critical = [p for p in held if ext["template"] and is_critical(ext["template"], p)] + problems
    out = dict(template=ext["template"], held=held, critical_held=critical, missing=[], doc=None, blocked=None)
    if not ext["template"]:
        out["blocked"] = "사업 유형(템플릿)을 정하지 못함"
        return out
    try:
        out["doc"], out["missing"] = T.build(to_sheet(ext, nid), pdf, pages)
    except (KeyError, TypeError, ValueError) as e:     # 필수 빈칸이 보류라 규칙을 만들 수 없음
        out["blocked"] = f"규칙을 만들 수 없음: {type(e).__name__} {e}"
    return out
