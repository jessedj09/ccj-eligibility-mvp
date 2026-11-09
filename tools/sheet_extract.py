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
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

import llm_slot as L  # noqa: E402
import notice_candidates as nc  # noqa: E402
import source_verify as sv  # noqa: E402
import templates as T  # noqa: E402
from rule_data import region_names  # noqa: E402
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


# ------------------------------------------------------------------ 값·핵심 표현으로 근거 다시 찾기(v3 ①, docs/10 §2-2)
RELOCATE_COVER = 0.65      # 형제 문장(숫자 가림)의 글자 중 원문 한 구간과 맞는 비율 하한
RELOCATE_CORE = 6          # 그 구간에 형제 문장과 그대로 같은 연속 글자가 이만큼은 있어야 한다(핵심 표현)
_VALUE = re.compile(r"\d[\d,]*(?:\.\d+)?(?:%|만원|억원|원|세|년|개월|회|㎡|인)")
_ROMAN = re.compile(r"I{1,3}|IV|V")


def _dates_of(text: str) -> set:
    out = set()
    for m in _TOKEN.finditer(text):
        y = int(m.group("y"))
        y = y if y > 999 else 2000 + y if y < 50 else 1900 + y
        try:
            out.add(date(y, int(m.group("m")), int(m.group("d"))))
        except ValueError:
            pass
    return out


def _values_of(n: str) -> set:
    """정규화 문장의 값 — 날짜를 뺀 금액·비율·나이·기간·면적(숫자 + 단위)."""
    return set(_VALUE.findall(_TOKEN.sub(" ", n)))


def relocate(pages: List[str], example: str) -> Optional[tuple]:
    """형제 문장(이 공고 날짜로 맞춘 것)과 **뜻이 같은 원문 구간**을 찾는다 — 표현이 조금 달라도(조사·괄호·앞뒤 수식어)
    값이 같으면 같은 근거로 본다. 조건: 숫자를 가린 글자의 65% 이상이 한 구간과 맞고, 6글자 이상 그대로 같은 핵심 표현이
    있고, 형제 문장의 **값(금액·비율·나이·기간)과 날짜가 모두** 그 구간에 있고, 로마 숫자(Ⅰ·Ⅱ 유형 구분)가 같다.
    → (맞은 비율, 쪽, 원문 정규화 구간) — 가장 잘 맞는 곳. 겹치는 창은 한 곳으로 보고, 서로 다른 곳이 같은 비율로 맞으면서
    내용이 다르면 고르지 않는다(보류)."""
    from difflib import SequenceMatcher
    e = sv.normalize(example)
    mask = lambda s: re.sub(r"\d", "#", s)                       # noqa: E731
    em = mask(e)
    if len(re.sub(r"[#\W]", "", em)) < 10:
        return None
    want_values, want_dates = _values_of(e), _dates_of(e)
    want_roman = sorted(_ROMAN.findall(re.sub(r"[^IVX]", " ", e)))
    pieces = {em[k:k + 6] for k in range(0, len(em) - 5, 3)}
    size = int(len(e) * 2) + 10          # 중간에 끼어든 괄호 설명(예: '(전 배우자였던 사람과 재혼하는 경우 …)')까지 담게
    places = []                                                  # [쪽, 시작, 끝, 맞은 비율, 구간]
    for i, t in enumerate(pages, 1):
        tm = mask(t)
        if not t or not any(p in tm for p in pieces):
            continue
        for start in range(0, max(1, len(t) - size + 1), 3):
            wm = tm[start:start + size]
            blocks = [b for b in SequenceMatcher(None, wm, em, autojunk=False).get_matching_blocks() if b.size >= 2]
            cover = sum(b.size for b in blocks) / len(em) if blocks else 0
            if cover < RELOCATE_COVER or max(b.size for b in blocks) < RELOCATE_CORE:
                continue
            s0, e0 = start + blocks[0].a, start + blocks[-1].a + blocks[-1].size
            w = t[s0:e0]
            if not want_values <= _values_of(w) or not want_dates <= _dates_of(w):
                continue
            if sorted(_ROMAN.findall(re.sub(r"[^IVX]", " ", w))) != want_roman:
                continue
            same = next((p for p in places if p[0] == i and s0 < p[2] and p[1] < e0), None)   # 겹치는 창 = 같은 곳
            if same is None:
                places.append([i, s0, e0, cover, w])
            elif cover > same[3]:
                same[1:] = [s0, e0, cover, w]
    if not places:
        return None
    places.sort(key=lambda p: -p[3])
    best = places[0]
    # 비슷하게 맞는 다른 곳이 '다른 내용'(글자 90% 미만 일치)이면 어느 쪽인지 모른다 — 요약표·본문처럼 같은 문장이
    # 한두 글자만 달리(의/인) 여러 번 나오는 것은 같은 근거
    rivals = [p for p in places[1:] if p[3] >= best[3] - 0.05
              and SequenceMatcher(None, mask(p[4]), mask(best[4]), autojunk=False).ratio() < 0.9]
    if rivals:
        return None
    return best[3], best[0], best[4]


@dataclass
class LLM:
    """LLM 슬롯과 LLM에게 보여 줄 쪽 텍스트(띄어쓰기 유지). 없으면 결정론만."""
    slot: object
    raw: List[str]


MIN_SIMILARITY = 0.35     # LLM이 고른 문장과 예시 문장의 글자 2-gram 겹침 하한 — 다른 조건의 문장을 고르는 것을 막는다


def llm_sentence(pages, llm: Optional[LLM], example: str, hint_pages=(), what="같은 역할의 조건 문장") -> Optional[tuple]:
    """LLM에게 예시와 같은 뜻의 문장을 찾게 하고, 원문에 실제로 있고 같은 주제일 때만 (쪽, 원문 문장)."""
    if llm is None or not example:
        return None
    look = list(dict.fromkeys([p for p in hint_pages if p] + L.pages_like(pages, example, 2)))[:3]
    got = llm.slot.find_sentence(llm.raw, look, what, example)
    if not got:
        return None
    snapped = snap(pages, got[0])
    if snapped is None:
        return None
    page, quote = snapped
    if len(quote) >= 8 and L.bigram_similarity(quote, example) >= MIN_SIMILARITY:
        return page, quote
    return None


SNAP_COVER = 0.85      # LLM 답의 글자 중 원문의 한 구간과 맞는 비율 하한


def snap(pages: List[str], answer: str) -> Optional[tuple]:
    """LLM 답을 '위치'로만 쓰고 인용문은 원문에서 직접 잘라 온다 — 답이 원문을 글자 한두 개 바꿔 옮겨도(띄어쓰기·조사)
    원문의 해당 구간을 그대로 쓴다. 답의 85% 이상이 한 쪽의 한 구간과 맞을 때만. → (쪽, 원문 정규화 텍스트)"""
    from difflib import SequenceMatcher
    a = sv.normalize(answer)
    if len(a) < 8:
        return None
    exact = on_page(pages, a)
    if exact:
        return exact, a
    # 답 길이만 한 창을 원문 위로 밀며 가장 잘 맞는 구간을 찾는다(앞뒤의 비슷한 문구에 끌려가지 않게).
    # 답의 6글자 조각이 하나라도 있는 쪽만 본다.
    pieces = {a[k:k + 6] for k in range(0, len(a) - 5, 3)}
    size = int(len(a) * 1.15) + 2
    best = None
    for i, t in enumerate(pages, 1):
        if not t or not any(p in t for p in pieces):
            continue
        for start in range(0, max(1, len(t) - size + 1), 2):
            w = t[start:start + size]
            blocks = [b for b in SequenceMatcher(None, w, a, autojunk=False).get_matching_blocks() if b.size >= 2]
            matched = sum(b.size for b in blocks)
            if matched / len(a) >= SNAP_COVER and (best is None or matched > best[0]):
                s0, e0 = blocks[0].a, blocks[-1].a + blocks[-1].size
                best = (matched, i, w[s0:e0])
    return (best[1], best[2]) if best else None


def adapt_quotes(pages, ann: date, siblings: List[dict], key_path, llm: Optional[LLM] = None) -> Dict[str, Field]:
    """형제 시트들의 문장(dict)을 이 공고 날짜로 바꿔 원문에 있는 것만 채운다. key_path: 시트 → 문장 dict.
    결정론으로 못 찾으면(llm이 있을 때) LLM에게 같은 뜻의 문장을 찾게 하고 검증한다."""
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
        placeholder = adapt(key_path(first)[k], date_mapping(date.fromisoformat(first["announcement_date"]), ann)) \
            if first else None
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
        if out[k].status == HELD:       # 형제마다 찾아 가장 잘 맞는 곳(형제마다 표현이 달라 한 형제만 맞을 수 있다)
            hits = []
            for s in siblings:
                src = key_path(s).get(k)
                if isinstance(src, str):
                    hit = relocate(pages, adapt(src, date_mapping(date.fromisoformat(s["announcement_date"]), ann)))
                    if hit:
                        hits.append((hit, s["notice_id"]))
            if hits:
                (_, page, text), sid = max(hits, key=lambda h: h[0][0])
                out[k] = Field(FILLED, text, page, text, f"형제 {sid} 문장과 값·핵심 표현이 같은 원문")
        if out[k].status == HELD and llm is not None and placeholder:
            hit = llm_sentence(pages, llm, placeholder)
            if hit:
                out[k] = Field(FILLED, hit[1], hit[0], sv.normalize(hit[1]), f"LLM({llm.slot.name}) — 원문 확인·주제 일치")
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
    if "국민임대" in program:          # G2: LH 표준 공고, G5: SH 국민임대(서울 거주)
        return "sh.national_rental" if issuer == "SH" else "lh.national_rental"
    if "영구임대" in program:          # G2: LH 영구임대 표준 공고, G5: SH 영구임대(서울 거주·1순위 가~자)
        return "sh.permanent_rental" if issuer == "SH" else "lh.permanent_rental"
    if program == "통합공공임대(일자리연계형)":   # 2026-11-09: 일자리연계형 지원주택(직업기준 + 일반형 신분)
        return None if issuer == "SH" else "lh.integrated_job"
    if "통합공공임대" in program:      # G2: LH 통합공공임대 일반형 — 일자리연계형 등 변형은 gate에서 막는다
        return None if issuer == "SH" else "lh.integrated_rental"
    if program == "토지임대부 분양주택":  # G3-3: SH 토지임대부 분양(LH 토지임대부는 아직 검증 전)
        return "sh.land_sale" if issuer == "SH" else None
    if program == "공공분양주택":       # G3: LH 공공분양 — SH 분양은 아직 검증 전
        return None if issuer == "SH" else "lh.public_sale"
    if program == "신혼희망타운(분양)":   # G3: LH 신혼희망타운 공공분양 — SH는 아직 검증 전
        return None if issuer == "SH" else "lh.newlywed_town_sale"
    if program == "공공분양(선택형)":     # G7: LH 선택형 공공임대(2024.1. 사전청약 기준 — 같은 금액 문구의 공고만)
        return None if issuer == "SH" else "lh.select_rental"
    if program == "공공분양(나눔형)":     # G6: LH 나눔형(2024.1. 사전청약 기준 — 같은 금액·비율 문구의 공고만)
        return None if issuer == "SH" else "lh.share_sale"
    if program == "행복주택" and issuer == "SH":   # SH 행복주택(2026년 1차 기준) — LH 행복주택 틀과 자격은 같고 문구·소득표가 다르다
        return "sh.happy_housing"
    if program == "다자녀 매입임대":      # SH 다자녀 매입임대(2026.5.29.) — LH 다자녀 매입임대는 아직 검증 전
        return "sh.multichild_rental" if issuer == "SH" else None
    if program == "고령자복지주택":       # G5: LH 고령자복지주택(영구임대형만 — 국민임대형 등은 gate가 막는다)
        return None if issuer == "SH" else "lh.elderly_welfare"
    if program == "공공임대주택":       # G4: LH 공공임대(10년·분양전환·50년) 예비입주자 — 최초 입주자 모집은 gate에서 막는다
        return None if issuer == "SH" else "lh.public_rental"
    for key, t in PROGRAM_TEMPLATE:
        if key in program and t:
            return None if issuer == "SH" and t.startswith("lh.") else t   # LH 틀은 SH 공고에 쓰지 않는다
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


def _sh_newlywed(pages, ann, sib, program, llm=None):
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
    f["quotes"] = adapt_quotes(pages, ann, same_kind + other, lambda s: s["params"]["quotes"], llm)
    inc = f["quotes"].get("income")
    if inc is not None and inc.status == FILLED:
        ratio = "70%" if f["kind"].value == "I" else "130%"
        if ratio not in sv.normalize(inc.value):
            f["kind"] = Field(HELD, how=f"소득 문장의 비율이 유형 {f['kind'].value}({ratio})와 다름 — 유형 확인 필요")
    return f


def _jeonse2(pages, ann, sib, program, llm=None):
    f = {"dates": {"marriage": by_convention(pages, ann, 7, "혼인", True),
                   "five": by_convention(pages, ann, 5, "소유", True)}}
    f["quotes"] = adapt_quotes(pages, ann, sib, lambda s: s["params"]["quotes"], llm)
    f["weak_quote"] = _weak_quote(pages)
    return f


def _weak_quote(pages) -> Field:
    hit = find_text(pages, r"주거약자형주택신청자는.{4,40}?중한개이상의")
    return Field(FILLED, hit[1], hit[0], hit[1], "'주거약자형 주택 신청자는 … 중 한 개 이상의' 문구") if hit else \
        Field(ABSENT, how="주거약자형 주택 신청자격 문구 없음")


def _jeonse(pages, ann, sib, program, llm=None):
    f = {}
    q = adapt_quotes(pages, ann, sib, lambda s: {k: v for k, v in s["params"]["quotes"].items() if isinstance(v, str)}, llm)
    a = find_text(pages, r"가액합산:[0-9,]+만원이하")
    c = find_text(pages, r"보건복지부장관이정하는금액:[0-9,]+만원이하")
    q["assets"] = Field(FILLED, a[1], a[0], a[1], "자산 한도 문구") if a else Field(HELD, how="자산 한도 문구 없음")
    q["car"] = Field(FILLED, c[1], c[0], c[1], "자동차 한도 문구") if c else Field(HELD, how="자동차 한도 문구 없음")
    minor = by_convention(pages, ann, 19, "미성년", True)
    q["minor_date"] = minor
    elderly = find_text(pages, r"만65세이상\[[^\]]{8,30}\]인2인이하무주택세대구성원")
    q["with_elderly"] = Field(FILLED, bool(elderly), elderly[0] if elderly else None, elderly[1] if elderly else None,
                              "고령자 우선공급 문구 " + ("있음" if elderly else "없음"))
    prio = adapt_quotes(pages, ann, sib, lambda s: s["params"]["quotes"].get("priority", {}), llm)
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


LAYER_HEAD = re.compile(r"\d-\d\.?(?:\([가-힣]{2,4}\))?(대학생|청년|신혼부부·한부모가족|고령자|산업단지근로자|주거급여수급자|"
                        r"지역전략산업종사자|주거약자)(?=계층|가족|입주자모집|■|–|-|\(|일반공급|○일반공급)")
EXTRA = {"고령자": ("elderly", "고령자"), "산업단지근로자": ("industrial", "산업단지 근로자"),
         "주거급여수급자": ("housing_benefit", "주거급여수급자"), "지역전략산업종사자": ("regional", "지역전략산업종사자")}
EXTRA_ARGS = {"elderly": lambda: {"home_quote": T.C3.ELDER_HOME},
              "housing_benefit": lambda: {"home_quote": "현재 무주택세대구성원인 주거급여수급자"},
              "industrial": dict, "regional": dict}


REGION_FIELDS = {"대학생": ["residence_area", "school_area"], "청년": ["residence_area", "income_base_area"],
                 "신혼부부": ["residence_area", "income_base_area", "spouse_residence_area", "spouse_income_base_area"],
                 "한부모": ["residence_area", "income_base_area"]}
REGION_NOTE = "거주지·소득 근거지(대학생은 재학 대학 소재지) 중 하나가 해당 주택건설지역 또는 연접 지역인지(이 공고는 1순위만 모집)"


# 1순위 지역 자격 문장: "해당 주택건설지역(서울특별시) 또는 연접지역(의정부시, 남양주시, …)이 거주지나 … 인 자"(띄어쓰기 없앤 원문)
FIRST_RANK = re.compile(r"해당주택건설지역\(([^()]+)\)(?:또는|및)연접지역\(([^()]+)\)(?:이|가)거주지[가-힣·]{0,30}?인자")
NOT_RECRUITED = re.compile(r"[0-9,·순위]{3,12}이번공고에서는모집하지않음")


def first_rank_areas(sentence: str) -> Optional[List[str]]:
    """1순위 자격 문장 → 지역 표준 이름 목록(주택건설지역 먼저). 이름 하나라도 지역 표준 이름표에 없으면 None(보류 — 모르는 지역을
    빼고 판정하면 틀린 '불가'가 나온다)."""
    m = FIRST_RANK.search(sentence)
    if not m:
        return None
    std = {sv.normalize(n): n for n in region_names()}
    out = []
    for raw in [m.group(1)] + m.group(2).split(","):
        n = re.sub(r"^(?:경기도|경기)(?=[가-힣]+[시군])", "", raw.strip())
        if n not in std:
            return None
        out.append(std[n])
    return out


def _region_rules(pages, layers, heads) -> Optional[dict]:
    """1순위만 모집하는 공고의 계층별 지역 자격(결정론, G1 2026-11-01). 계층 소제목 쪽부터 다음 소제목 전까지(최대 3쪽)에서
    1순위 자격 문장과 '2·3순위 이번 공고에서는 모집하지 않음' 문장을 **둘 다** 찾고 지역 이름을 모두 알아볼 때만 — 아니면 None."""
    out = {}
    for layer in layers:
        head = "신혼부부·한부모가족" if layer in ("신혼부부", "한부모") else layer
        start = heads.get(head)
        if not start:
            return None
        nxt = min([p for p in heads.values() if p > start], default=start + 3)
        first = nore = areas = None
        for i in range(start, min(nxt, start + 3) + 1):
            if i > len(pages):
                break
            t = pages[i - 1]
            m = FIRST_RANK.search(t)
            if m and first is None:
                areas = first_rank_areas(m.group(0))
                if areas is None:
                    return None
                first = m.group(0)
            n = NOT_RECRUITED.search(t)
            if n and nore is None:
                nore = n.group(0)
        if not (first and nore):
            return None
        out[layer] = dict(fields=REGION_FIELDS[layer], quote=[first, nore], note=REGION_NOTE, areas=areas)
    return out


def _llm_region(pages, llm: LLM, layers, heads) -> Optional[dict]:
    """1순위만 모집하는 공고의 계층별 지역 자격 문장. 템플릿 지역 목록(서울특별시 + 연접 13개 시)이 문장에 **전부** 있고
    목록 밖 지역 이름이 **없을** 때만 쓴다 — 목록이 다른 공고에 서울 목록을 쓰면 틀린 '불가'가 나온다."""
    adj = [sv.normalize(n) for n in T.C1.SEOUL_ADJ]
    others = [sv.normalize(n) for n in region_names() if n not in T.C1.SEOUL_ADJ]
    schema = {"type": "object", "properties": {"first_rank": {"type": "string"}, "not_recruited": {"type": "string"}},
              "required": ["first_rank", "not_recruited"]}
    out = {}
    for layer in layers:
        head = "신혼부부·한부모가족" if layer in ("신혼부부", "한부모") else layer
        start = heads.get(head) or 1
        prompt = (f"이 공고는 1순위 지역만 모집한다(2·3순위는 이번 공고에서 모집하지 않음). '{layer}' 계층의 1순위 자격 문장 — "
                  "'해당 주택건설지역(…) 또는 연접지역(…)이 거주지나 …인 자' 같은 문장 — 을 원문 그대로 first_rank에, "
                  "2·3순위를 이번 공고에서 모집하지 않는다는 문장을 원문 그대로 not_recruited에 복사하라.\n\n"
                  + L.page_block(llm.raw, [start, start + 1, start + 2]))
        got = llm.slot.ask(prompt, schema) or {}
        first, nore = str(got.get("first_rank", "")).strip(), str(got.get("not_recruited", "")).strip()
        nf = sv.normalize(first)
        if not (first and nore and on_page(pages, first) and on_page(pages, nore)):
            return None
        if not all(a in nf for a in adj) or any(o in nf for o in others):
            return None
        out[layer] = dict(fields=REGION_FIELDS[layer], quote=[first, nore], note=REGION_NOTE, areas=list(T.C1.SEOUL_ADJ))
    return out


def _happy_housing(pages, ann, sib, program, title_text, llm=None):
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
        # "2019.10.2.이후출생" / "6세이하자녀(출생일2019.10.29.이후)"(N27 p.1)
        for mm in re.finditer(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\.?이후출생|출생일(\d{4})\.(\d{1,2})\.(\d{1,2})\.?이후", t):
            if mm.group(1) is None:                        # 둘째 표기 — 같은 모양(연·월·일 그룹)으로 맞춘다
                mm = re.match(r"출생일(\d{4})\.(\d{1,2})\.(\d{1,2})\.?이후", mm.group(0))
            d = _near_convention((i, mm.group(0), mm), ann, 7)
            if d:
                lit_c, hit = d, (i, mm.group(0))
                break
        if lit_c:
            break
    f["child"] = Field(FILLED, lit_c, hit[0], hit[1], "'…이후 출생' 리터럴(공고일−7년 무렵)") if lit_c else \
        Field(ABSENT, None, how="6세 기준일 리터럴 없음 — 공고일에서 도출")
    only_first = find_text(pages, r"이번공고에서는모집하지않음")
    region = _region_rules(pages, layers, heads) if (only_first and layers) else None      # 결정론 먼저(G1)
    llm_region = _llm_region(pages, llm, layers, heads) if (only_first and layers and not region and llm is not None) else None
    if region:
        f["region"] = Field(FILLED, region, only_first[0], only_first[1], "1순위 자격 문장 — 지역 이름 모두 표준 이름표에 있음")
    elif llm_region:
        f["region"] = Field(FILLED, llm_region, only_first[0], only_first[1], f"LLM({llm.slot.name}) — 지역 목록·원문 확인")
    elif only_first:
        f["region"] = Field(HELD, None, only_first[0], only_first[1], "1순위 지역만 모집 — 계층별 지역 조건 문장을 확인하지 못함")
    else:
        f["region"] = Field(ABSENT, {}, how="2·3순위 미모집 문구 없음")
    f["overrides"] = Field(ABSENT, {}, how="템플릿과 표현이 다른 문장은 규칙을 만든 뒤 '찾지 못한 인용문'으로 드러난다")
    f["weak"] = _happy_weak(pages, layers, heads)
    return f


SH_HAPPY_EXTRA = ("고령자", "주거급여수급자")
# 자산·자동차 한도(만원): '…총자산 기준 X만원 이하 · 출생자녀 1명: Y [단, 그 전 미성년 자녀 추가: Z] · 2명 이상: Z' (N68 p.22~23)
SH_MONEY_TAIL = r".{0,80}?1명인경우:([\d,]+)만원이하.{0,80}?추가로있는경우:([\d,]+)만원이하.{0,80}?2명이상인경우:([\d,]+)만원이하"
SH_MONEY_RX = {"student": r"대학생계층은총자산기준([\d,]+)만원이하", "youth": r"청년계층\(세대주가아닌경우본인만\)은총자산기준([\d,]+)만원이하",
               "base": r"신혼부부계층·고령자는총자산기준([\d,]+)만원이하", "car": r"현재가치기준자동차가액은([\d,]+)만원이하"}
# 소득표 연도: 1인 칸(1인 +20%p) 금액으로 알아본다 — 등록된 SH 행복주택 소득표만
SH_HAPPY_INCOME_MARK = {"2025": "4,576,036", "2024": "4,317,797"}


def _sh_happy_money(pages, layers):
    text = "".join(pages)
    money, lost = {}, []
    year = [y for y, mark in SH_HAPPY_INCOME_MARK.items() if mark in text]
    money["income"] = year[0] if len(year) == 1 else None
    if money["income"] is None:
        lost.append("소득기준표 연도(등록된 SH 행복주택 소득표와 1인 금액이 다름)")
    need = {"student": "대학생" in layers, "youth": "청년" in layers, "car": True,
            "base": bool({"신혼부부", "한부모"} & set(layers)) or "고령자" in layers}
    for key, rx in SH_MONEY_RX.items():
        m = re.search(rx + SH_MONEY_TAIL, text)
        vals = [int(x.replace(",", "")) for x in m.groups()] if m else None
        if vals and vals[2] == vals[3] and vals[0] < vals[1] < vals[2]:
            money[key] = vals[:3]
        else:
            money[key] = None
            if need[key]:
                lost.append(f"{key} 한도 문구(기준·출생자녀 1명·2명 이상)")
    return money, lost


def _sh_happy(pages, ann):
    """SH 행복주택: 계층 소제목·한부모 6세 기준일은 LH 행복주택 추출기와 같은 방식으로 읽는다. 1순위 지역만 모집·주거약자 갈래·
    산업단지근로자 등 그 밖의 계층이 있는 공고는 판정 틀(2026년 1차 기준)과 달라 보류한다."""
    f = _happy_housing(pages, ann, [], "행복주택", "", None)
    out = {"layers": f["layers"]}
    extra = list(f["extra_layers"].value)
    other = [x for x in extra if x not in SH_HAPPY_EXTRA]
    out["extra_layers"] = Field(HELD, extra, how=f"판정 틀에 없는 계층 {other}") if other else \
        Field(FILLED, extra, how="추가 계층 소제목(고령자·주거급여수급자)")
    out["child"] = f["child"] if f["child"].status == FILLED else Field(HELD, None, how="한부모 6세 이하 자녀 출생 기준일 리터럴 없음")
    money, lost = _sh_happy_money(pages, list(f["layers"].value or []) + extra)
    out["money"] = Field(HELD, money, how=f"읽지 못한 금액: {lost}") if lost else \
        Field(FILLED, money, how="소득표 연도(1인 금액)·자산·자동차 한도(출생자녀 가산 포함) 문구")
    variant = [k for k in ("region", "weak") if f[k].status != ABSENT] + (["marriage"] if f["marriage"].status == FILLED else [])
    if variant:
        out["layers"] = Field(HELD, f["layers"].value, how=f"판정 틀과 다른 갈래 {variant}(1순위 지역만 모집·주거약자·혼인 기준일 리터럴)")
    return out


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


ELDER_ITEM = re.compile(r"고령자\(만?65세이상인(?:자|사람)\)(?!는위에표기하지않|는제외|제외)")
ELDER_EXCLUDED = re.compile(r"고령자\(만?65세이상인(?:자|사람)\)(?:는위에표기하지않|는제외|제외)")


def _weak_elderly(pages, page: int) -> Optional[bool]:
    """주거약자 정의에 65세 이상 고령자가 들어가는가 — 그 쪽(과 다음 쪽)에서 항목으로 있으면 True, '표기하지 않음·제외'면 False,
    둘 다 없으면 None(보류 — 단정하면 고령자에게 틀린 가능·불가가 난다). N5 p.11은 제외 문장, N2 p.6은 항목."""
    text = "".join(pages[page - 1: page + 1])
    if ELDER_EXCLUDED.search(text):
        return False
    return True if ELDER_ITEM.search(text) else None


def _on(pages, pattern: str) -> Optional[str]:
    hit = find_text(pages, pattern)
    return hit[1] if hit else None


def _happy_weak(pages, layers, heads) -> Field:
    # 가운뎃점 없이 쓴 공고도 있다(N28 p.9 "3-1.신혼부부한부모가족공급대상자의요건을…")
    hit = find_text(pages, r"신혼부부[·ㆍ.]?한부모가족[가-힣의 ]{0,12}요건을모두갖추고아래주거약?자의요건을갖춘(?:사람|자)")
    if hit and {"신혼부부", "한부모"} <= set(layers):
        quotes = [hit[1]]
        if on_page(pages, DISABLED):
            quotes.append(DISABLED)
        return Field(FILLED, dict(bases=["신혼부부", "한부모"], elderly=bool(on_page(pages, "65세이상")), page=hit[0],
                                  quotes=quotes), hit[0], hit[1], "'…요건을 모두 갖추고 아래 주거약자의 요건을 갖춘' 문구")
    # G1(2026-11-01): 다른 계층 묶음의 주거약자 문구
    # N2 p.6 "대학생계층의입주자격요건을갖춘자로서아래의주거약자에해당하는자" → 그 계층 + 주거약자
    one = find_text(pages, r"(대학생|청년)계층의입주자격요건을갖춘자로서아래의주거약자에해당하는자")
    if one and re.search(r"(대학생|청년)", one[1]).group(1) in layers:
        base = re.search(r"(대학생|청년)", one[1]).group(1)
        elderly = _weak_elderly(pages, one[0])
        if elderly is None:
            return Field(HELD, None, one[0], one[1], "주거약자 정의에 고령자가 들어가는지 원문에서 확인하지 못함")
        elder_q = ELDER_ITEM.search("".join(pages[one[0] - 1: one[0] + 1])) if elderly else None
        quotes = [one[1]] + ([elder_q.group(0)] if elder_q else []) + ([DISABLED] if on_page(pages, DISABLED) else [])
        return Field(FILLED, dict(bases=[base], elderly=elderly, page=one[0], quotes=quotes), one[0], one[1],
                     "'○○계층의 입주자격요건을 갖춘 자로서 아래의 주거약자' 문구")
    # N5 p.11 "지역전략산업종사자,청년,대학생중하나의자격요건을충족하면서주거약자(장애인등)에해당" → 트랙 중 하나 + 주거약자
    names = r"(?:지역전략산업종사자|산업단지근로자|청년|대학생)"
    tr = find_text(pages, rf"{names}(?:,{names})+중하나의자격요건을충족하면서주거약자(?:\(장애인등\))?에해당")
    if tr:
        tracks = re.findall(names, tr[1].split("중하나")[0])
        if all(t in layers or t in heads for t in tracks):
            elderly = _weak_elderly(pages, tr[0])
            if elderly is None:
                return Field(HELD, None, tr[0], tr[1], "주거약자 정의에 고령자가 들어가는지 원문에서 확인하지 못함")
            quotes = [tr[1]] + ([DISABLED] if on_page(pages, DISABLED) else [])
            return Field(FILLED, dict(tracks=tracks, elderly=elderly, page=tr[0], quotes=quotes), tr[0], tr[1],
                         "'○○, ○○ 중 하나의 자격요건을 충족하면서 주거약자' 문구")
    if "주거약자" in heads:
        return Field(HELD, None, heads["주거약자"], None, "주거약자 주택형 소제목 — 대상 계층 묶음을 원문에서 확인하지 못함")
    return Field(ABSENT, None, how="신혼부부·한부모 주거약자 요건 문구 없음(고령자 배정 주거약자용은 고령자 계층으로 판정)")


# ------------------------------------------------------------------ 국민임대(G2)
# 고령자 전용 주택형: N32 p.3 "○○단지46형고령자임대주택은(공고일현재65세이상만신청)가능하며"
ELDERLY_TYPE = r"[가-힣0-9]{0,20}\d+형고령자[가-힣]*주택은?\(공고일현재65세이상만신청\)가능"


def _national_rental(pages):
    hit = find_text(pages, ELDERLY_TYPE)
    won = find_text(pages, re.escape("총자산가액(원)자동차가액(원)"))     # N58 p.5: 원 단위 한 표
    return {"elderly_quote": Field(FILLED, hit[1], hit[0], hit[1], "'○○형 고령자임대주택은(공고일현재65세이상만신청)' 문구")
            if hit else Field(ABSENT, None, how="고령자 전용 주택형 문구 없음"),
            "money": Field(FILLED, "won", won[0], won[1], "자산 한도 표가 원 단위('총자산가액(원)')") if won else
            Field(FILLED, "million", how="원 단위 표 머리말 없음 — 표준(백만원·만원 단위) 표기")}


# ------------------------------------------------------------------ 영구임대(G2)
# 거주 요건: N33 p.1 "현재○○시에거주(주민등록이등재)하는무주택세대구성원중영구임대주택입주적격자에한합니다",
#           N34 p.1 "현재○○시에거주(주민등록등재)하는무주택세대구성원이지원가능하며"
RESIDENCE = r"([가-힣]{1,6}[시군])에거주\(주민등록이?등재\)하는무주택세대구성원[가-힣]{0,20}"
ADULT = r"「민법」상미성년자\(19세미만\)는공급신청할수없습니다|신청자는민법상성년자\(만19세\)이어야합니다"
WEAK_TYPE = r"\d+[A-Z]?\d?형(?:\(주거약자용주택\))?은주거약자에한하여신청가능합니다"


def _permanent_rental(pages):
    from rule_data import region_groups
    known = {n for names in region_groups().values() for n in names}
    f = {}
    hit = find_text(pages, RESIDENCE)
    city = re.match(RESIDENCE, hit[1]).group(1).removeprefix("현재") if hit else None
    f["city"] = Field(FILLED, city, hit[0], hit[1], "'○○시에 거주(주민등록 등재)하는 무주택세대구성원' 문구") \
        if city in known else Field(HELD, None, hit[0] if hit else None, hit[1] if hit else None,
                                    "거주 요건 시·군을 원문에서 확인하지 못함(표준 지역 이름이 아님)" if hit else "거주 요건 문구 없음")
    f["residence_quote"] = Field(FILLED, hit[1], hit[0], hit[1], "거주 요건 문장") if hit else \
        Field(HELD, "무주택세대구성원", how="거주 요건 문장 없음")
    hit = find_text(pages, ADULT)
    f["adult_quote"] = Field(FILLED, hit[1], hit[0], hit[1], "성년 요건 문장") if hit else \
        Field(HELD, "「민법」상 미성년자(19세 미만)는 공급신청할 수 없습니다", how="성년 요건 문장을 찾지 못함")
    hit = find_text(pages, WEAK_TYPE)
    f["weak_quote"] = Field(FILLED, hit[1], hit[0], hit[1], "'○○형은 주거약자에 한하여 신청 가능' 문구") if hit else \
        Field(ABSENT, None, how="주거약자용 주택형 문구 없음")
    return f


# ------------------------------------------------------------------ SH 국민임대(G5)
# 공통 자격: N53 p.22 "입주자모집공고일(2026.08.20.)현재서울특별시에거주하는성년자인무주택세대구성원으로서"
SH_ELIGIBILITY = r"현재서울특별시에거주하는성년자인무주택세대구성원(?:으로서)?"
SH_ADULT = r"「?민법」?상미성년자\(만?19세미만\)는공급신청할수없습니다"
SH_INCOME70 = r"해당세대의월평균소득이전년도도시근로자가구원수별가구당월평균소득의70퍼센트이하인사람"
# 서울 밖 거주자도 받는 단지: N53 p.22 "상계장암지구1,2단지는서울특별시외의정부시,남양주시,양주시,포천시에거주하는사람도신청가능"
SH_NEAR_SENT = r"[가-힣0-9]{0,12}지구[0-9,·]+단지는서울특별시외(?P<cities>[가-힣,·]+?)에거주하는사람도신청가능"
SH_NEAR_CITIES = ("의정부시", "남양주시", "양주시", "포천시")     # gen_c6_public.SH_NEAR와 같아야 한다(테스트가 확인)
SH_WEAK = r"(?:①~⑦|1~7)중한개이상의자격을갖춘사람\(공급신청자본인\)만신청가능"


def _sh_national_rental(pages):
    f = {}
    for key, rx, how, fallback in (
            ("eligibility_quote", SH_ELIGIBILITY, "공통 신청자격 문장(서울 거주·성년·무주택세대구성원)", "무주택세대구성원"),
            ("adult_quote", SH_ADULT, "성년 요건 문장", "미성년자"),
            ("income_quote", SH_INCOME70, "소득 기준 문장(70% 이하)", "월평균소득")):
        hit = find_text(pages, rx)
        f[key] = Field(FILLED, hit[1], hit[0], hit[1], how) if hit else Field(HELD, fallback, how=f"{how}을 찾지 못함")
    hit = find_text(pages, SH_NEAR_SENT)
    if hit:
        cities = set(re.split(r"[,·]", re.match(SH_NEAR_SENT, hit[1]).group("cities")))
        f["near_quote"] = (Field(FILLED, hit[1], hit[0], hit[1], "서울 밖 일부 시 거주자도 받는 단지 문구")
                           if cities == set(SH_NEAR_CITIES) else
                           Field(HELD, hit[1], hit[0], hit[1], f"서울 밖 거주 허용 시가 판정 틀과 다름({','.join(sorted(cities))})"))
    elif find_text(pages, r"서울특별시외[^■]{0,40}?(?:신청가능|신청할수있)"):
        f["near_quote"] = Field(HELD, "서울특별시외", how="서울 밖 거주자도 받는 문구가 있으나 형식을 읽지 못함")
    else:
        f["near_quote"] = Field(ABSENT, None, how="서울 밖 거주 허용 문구 없음")
    hit = find_text(pages, SH_WEAK)
    f["weak_quote"] = Field(FILLED, hit[1], hit[0], hit[1], "일반공급(주거약자) 신청자격 문구") if hit else         Field(ABSENT, None, how="일반공급(주거약자) 문구 없음")
    # 판(소득 기준표·자산 한도): 원문 자산 표 리터럴이 판정 틀의 판과 같을 때만 그 판. 모르는 금액이면 기본 판 — 인용문을 못 찾아 보류된다
    import gen_c6_public as G
    ed = next(((k, h) for k, e in G.SH_NATIONAL_EDITION.items() for h in [find_text(pages, re.escape(e["quotes"][0]))] if h), None)
    f["edition"] = Field(FILLED, ed[0], ed[1][0], ed[1][1], "자산 표 '기본' 행 금액이 판정 틀의 판과 같음") if ed else         Field(FILLED, "2026", how="자산 표 금액이 판정 틀의 어느 판과도 다름 — 기본 판(자산·소득 조건은 인용문을 못 찾아 보류)")
    return f


# ------------------------------------------------------------------ SH 영구임대(G5)
# N54 p.7 "모집공고일(2025.11.13.)현재서울특별시에거주하는성년자인무주택세대구성원으로,영구임대주택입주자자격에해당되며"
SHP_ELIGIBILITY = r"현재서울특별시에거주하는성년자인무주택세대구성원으로,?영구임대주택입주자자격에해당되며"
SHP_INCOME70 = r"월평균소득의70퍼센트이하\(가구원수1명-90%,가구원수2명-80%\)이고"
# 총자산·자동차 한도는 판정 틀의 리터럴(gen_c6_public.SHP_B1 — 2억3,700만·4,563만)과 같은 문구일 때만 채운다.
# 다른 금액이면(다음 해 기준) 보류 — 리터럴로 판정하지 않게.
SHP_ASSET = "(23,700)만원이하"
SHP_CAR = "개별자동차가액(4,563)만원이하"


def _sh_permanent_rental(pages):
    f = {}
    for key, rx, how, fallback in (
            ("eligibility_quote", SHP_ELIGIBILITY, "공통 신청자격 문장(서울 거주·성년·무주택세대구성원)", "무주택세대구성원"),
            ("adult_quote", SH_ADULT, "성년 요건 문장", "미성년자"),
            ("income_quote", SHP_INCOME70, "소득 기준 문장(70% 이하)", "월평균소득")):
        hit = find_text(pages, rx)
        f[key] = Field(FILLED, hit[1], hit[0], hit[1], how) if hit else Field(HELD, fallback, how=f"{how}을 찾지 못함")
    for key, lit, how in (("asset_quote", SHP_ASSET, "총자산 한도 2억3,700만원"), ("car_quote", SHP_CAR, "자동차 한도 4,563만원")):
        page = on_page(pages, lit)
        f[key] = Field(FILLED, lit, page, lit, how) if page else \
            Field(HELD, lit, how=f"{how} 문구가 없음(다른 기준 연도일 수 있음)")
    return f


# ------------------------------------------------------------------ LH 고령자복지주택(G5)
# N55 p.5 "입주자모집공고일(2026.08.20.)현재만65세이상(1961.08.20.이전출생자)으로서무주택세대구성원요건을만족하고",
# N61·N62 p.4 "…현재만65세이상으로서무주택세대구성원요건을만족하고"(출생일 없음)
ELD_ELIGIBILITY = r"현재만65세이상(?:\(\d{4}\.\d{2}\.\d{2}\.이전출생자?\))?으로서무주택세대구성원요건을만족하고"
# 2순위: N55 "…으로서월평균소득70%(1인90%,2인80%)이하인사람", N61·N62 "…으로서소득70%(1인90%,2인80%)이하인자"
ELD_MERIT = r"(?:월평균)?소득70%\(1인90%,2인80%\)이하인자?"
ELD_GENERAL = r"50%\(1인70%,2인60%\)이하인자"
# 판정 틀은 영구임대형 리터럴(총자산 24,500만·자동차 4,542만) — 제목·첫 쪽에 '고령자복지주택(영구임대)'가 있을 때만
ELD_KIND = r"고령자복지주택\(영구임대\)"


# SH 다자녀 매입임대(2026.5.29. p.6·p.9): 공통 자격 문장, 3순위 소득·자산 금액은 이 공고의 리터럴일 때만 채운다(다른 해 금액이면 보류)
MULTI_ELIGIBILITY = r"두명이상의직계비속\(태아를포함하며,「민법」상미성년자로한정함\)을양육하고,무주택세대구성원으로서"
MULTI_LITERALS = (("income_quote", "70%이하5,717,9006,161,5416,528,8906,934,3847,339,8797,745,373", "3순위 소득 70% 표(2025년도)"),
                  ("asset_quote", "총자산가액:34,500만원이하", "총자산 34,500만원"),
                  ("car_quote", "자동차가액(현재가치기준):4,542만원이하", "자동차 4,542만원"))


# 통합공공임대 일자리연계형(전주 p.10 / 담양 p.9): 직업기준 종류와 문장
JOB_REGIONAL = r"지역전략산업에종사하는사람등[가-힣]{1,10}(?:시장|군수|구청장|도지사)이지역전략산업의육성을위해필요하다고인정한사람"
JOB_EARNER = r"「소득세법」제19조제1항또는제20조제1항에따른사업소득또는근로소득이있는사람"


def _integrated_job(pages):
    for kind, rx, how in (("regional", JOB_REGIONAL, "직업기준 '지역전략산업 종사자'(지자체·기관 인정)"),
                          ("earner", JOB_EARNER, "직업기준 '사업·근로소득자'")):
        hit = find_text(pages, rx)
        if hit:
            return {"job_kind": Field(FILLED, kind, hit[0], hit[1], how), "job_quote": Field(FILLED, hit[1], hit[0], hit[1], how)}
    return {"job_kind": Field(HELD, None, how="직업기준을 읽지 못함(판정 틀에 없는 직업기준일 수 있음)"),
            "job_quote": Field(HELD, None, how="직업기준 문장을 찾지 못함")}


def _sh_multichild(pages):
    hit = find_text(pages, MULTI_ELIGIBILITY)
    f = {"eligibility_quote": Field(FILLED, hit[1], hit[0], hit[1], "공통 신청자격 문장(미성년 자녀 2명 이상·무주택세대구성원)")
         if hit else Field(HELD, None, how="공통 신청자격 문장을 찾지 못함")}
    for key, lit, how in MULTI_LITERALS:
        page = on_page(pages, lit)
        f[key] = Field(FILLED, lit, page, lit, how) if page else \
            Field(HELD, None, how=f"{how} 문구가 없음(다른 기준 연도일 수 있음)")
    return f


def _elderly_welfare(pages):
    hit = find_text(pages[:3], ELD_KIND)
    f = {"kind": Field(FILLED, "영구임대", hit[0], hit[1], "제목·첫 쪽의 '고령자복지주택(영구임대)'") if hit else
         Field(HELD, None, how="영구임대형 고령자복지주택인지 확인하지 못함(국민임대형 등은 판정 틀이 다름)")}
    for key, rx, how, fallback in (
            ("eligibility_quote", ELD_ELIGIBILITY, "공통 신청자격 문장(65세 이상·무주택세대구성원)", "무주택세대구성원"),
            ("merit_quote", ELD_MERIT, "2순위(국가유공자 등) 소득 70% 문구", "월평균소득"),
            ("general_quote", ELD_GENERAL, "3순위(일반) 소득 50% 문구", "월평균소득")):
        hit = find_text(pages, rx)
        f[key] = Field(FILLED, hit[1], hit[0], hit[1], how) if hit else Field(HELD, fallback, how=f"{how}을 찾지 못함")
    for key, lit, how in (("asset_quote", "가액합산기준24,500만원이하", "총자산 한도 2억4,500만원"),
                          ("car_quote", "개별자동차가액4,542만원이하", "자동차 한도 4,542만원")):
        page = on_page(pages, lit)
        f[key] = Field(FILLED, lit, page, lit, how) if page else Field(HELD, lit, how=f"{how} 문구가 없음(다른 기준일 수 있음)")
    return f


# ------------------------------------------------------------------ LH 나눔형 공공분양(G6)
# 판정 틀은 2024.1. LH 나눔형 사전청약 공고의 리터럴(2023년도 금액, 맞벌이 140%, 총자산 379백만) — 같은 문구일 때만 채운다.
# 다른 해 공고(2024.3. 개정 뒤: 맞벌이 200%, 신생아 특별공급)는 필수 값이 보류돼 자동 판정하지 않는다.
SHARE_LITERALS = (("youth_income_quote", "청년도시근로자가구원수별가구당월평균소득액의140%4,695,438원", "청년 본인 소득 140% 금액"),
                  ("asset_quote", "379,000천원이하", "세대 총자산 3억7,900만원"),
                  ("youth_asset_quote", "289백만원이하", "청년 본인 총자산 2억8,900만원"),
                  ("parents_quote", "(부모)1,083백만원이하", "청년 부모 총자산 10억8,300만원"),
                  ("dual_quote", "맞벌이도시근로자가구당월평균소득액의140%9,113,233원", "신혼부부 맞벌이 140% 금액"))


# 2026 판(개정 뒤 본청약, N63): 이 문구가 모두 있으면 2026 판으로 판정한다(하나라도 없으면 2024 판 문구로 — 그것도 없으면 보류)
SHARE_2026_LITERALS = (("youth_income_quote", "청년특별공급도시근로자가구원수별가구당월평균소득액의140%5,338,708", "청년 본인 소득 140% 금액(2025년도)"),
                       ("asset_quote", "362,000천원이하", "세대 총자산 3억6,200만원"),
                       ("youth_asset_quote", "276,000천원이하", "청년 본인 총자산 2억7,600만원"),
                       ("parents_quote", "1,035,000천원이하", "청년 부모 총자산 10억3,500만원"),
                       ("dual_quote", "(본인및배우자가모두소득이있는경우200%)이하인분", "맞벌이 200% 문구"))


def _share_sale(pages):
    f = {"residence": Field(FILLED, "수도권", *find_text(pages, r"수도권\[서울특별시,경기도,인천광역시\]"),
                            how="'수도권[서울특별시, 경기도, 인천광역시]' 거주 문구")
         if find_text(pages, r"수도권\[서울특별시,경기도,인천광역시\]") else
         Field(HELD, None, how="수도권 거주 요건 문구를 확인하지 못함")}
    if all(on_page(pages, lit) for _, lit, _ in SHARE_2026_LITERALS):
        f["edition"] = Field(FILLED, "2026", how="2026 판(개정 뒤 본청약) 금액 문구가 모두 있음")
        for key, lit, how in SHARE_2026_LITERALS:
            page = on_page(pages, lit)
            f[key] = Field(FILLED, lit, page, lit, how)
        return f
    f["edition"] = Field(FILLED, "2024", how="2026 판 금액 문구가 모두 있지 않음 — 2024 판 문구로 확인")
    for key, lit, how in SHARE_LITERALS:
        page = on_page(pages, lit)
        f[key] = Field(FILLED, lit, page, lit, how) if page else \
            Field(HELD, None, how=f"{how} 문구가 없음(다른 기준 연도·개정 뒤 공고일 수 있음)")
    return f


# ------------------------------------------------------------------ LH 선택형 공공임대(G7)
# 판정 틀은 2024.1. LH 선택형 사전청약 공고의 리터럴(2023년도 금액, 다자녀 3명, 총자산 379백만) — 같은 문구일 때만 채운다.
SELECT_LITERALS = (("youth_income_quote", "청년특별공급도시근로자가구원수별가구당월평균소득액의140%4,695,438", "청년 본인 소득 140% 금액"),
                   ("asset_quote", "379,000천원이하", "세대 총자산 3억7,900만원"),
                   ("youth_asset_quote", "289,000천원이하", "청년 본인 총자산 2억8,900만원"),
                   ("parents_quote", "1,083,000천원", "청년 부모 총자산 10억8,300만원"),
                   ("dual_quote", "맞벌이도시근로자가구원수별가구당월평균소득액의140%9,405,477원", "신혼부부 맞벌이 140% 금액(3인)"))


# 2026 판(개정 뒤 6년 분양전환 공공임대 최초 모집, N64): 이 문구가 모두 있으면 2026 판
SELECT_2026_LITERALS = (("youth_income_quote", "청년특별공급도시근로자가구원수별가구당월평균소득액의140%5,338,708", "청년 본인 소득 140% 금액(2025년도)"),
                        ("asset_quote", "362,000천원이하", "세대 총자산 3억6,200만원"),
                        ("youth_asset_quote", "276,000천원이하", "청년 본인 총자산 2억7,600만원"),
                        ("parents_quote", "1,035,000천원이하", "청년 부모 총자산 10억3,500만원"),
                        ("dual_quote", "가구원수가2명인경우에는140%(본인및배우자가모두소득이있는경우에는200%)", "2인 가구·맞벌이 200% 문구"))


def _select_rental(pages):
    hit = find_text(pages, r"수도권\[서울특별시,경기도,인천광역시\]")
    f = {"residence": Field(FILLED, "수도권", hit[0], hit[1], "'수도권[서울특별시, 경기도, 인천광역시]' 거주 문구") if hit else
         Field(HELD, None, how="수도권 거주 요건 문구를 확인하지 못함")}
    if all(on_page(pages, lit) for _, lit, _ in SELECT_2026_LITERALS):
        f["edition"] = Field(FILLED, "2026", how="2026 판(개정 뒤 6년 분양전환) 금액 문구가 모두 있음")
        for key, lit, how in SELECT_2026_LITERALS:
            page = on_page(pages, lit)
            f[key] = Field(FILLED, lit, page, lit, how)
        return f
    f["edition"] = Field(FILLED, "2024", how="2026 판 금액 문구가 모두 있지 않음 — 2024 판 문구로 확인")
    for key, lit, how in SELECT_LITERALS:
        page = on_page(pages, lit)
        f[key] = Field(FILLED, lit, page, lit, how) if page else \
            Field(HELD, None, how=f"{how} 문구가 없음(다른 기준 연도·개정 뒤 공고일 수 있음)")
    return f


# ------------------------------------------------------------------ 공공임대 예비입주자(G4)
# 신청 자격 문장: N37 "현재수도권에거주(주민등록표등본기준)하는무주택세대구성원", N39 "현재주택건설지역(경기도,서울특별시,
# 인천광역시)에거주하는무주택세대구성원", 거주 요건이 없는 공고는 "현재무주택세대구성원으로서"
ELIGIBILITY = r"현재(?P<area>[^■]{0,60}?)무주택세대구성원"
CAPITAL_WORDS = ("서울", "인천", "경기")
ACCOUNT_FREE = r"(?:청약저축|입주자저축)가입여부[^■]{0,40}?(?:관계없이|상관없|불문)"
ACCOUNT_JOINED = r"2순위[^■]{0,60}?(?:청약저축포함\)|입주자저축)에가입되어있고"
ACCOUNT_MIN = r"2순위[^■]{0,60}?에가입하여(?P<n>\d+)(?P<u>개월|월|년)이(?:지난|경과된)[^■]{0,40}?(?P<c>\d+)회이상"
ADULT_SENT = r"「민법」상미성년자\(만?19세미만\)는공급신청할수없습니다"
# 재당첨 제한: 계약·신청 불가 문구(N37·N38) + "재당첨제한기간내에있는분…신청할수없습니다"(G4 처음 보는 공고 결과를 본 뒤 보강 —
# N42·N43에서 이 문장을 놓쳐 조항 장부가 '보류'로 막았다)
REWIN = r"재당첨제한[^■.]{0,30}?(?:불가|없으며|없습니다)|재당첨제한기간내에있는분"


def _public_rental(pages):
    f = {}
    hit = find_text(pages, ELIGIBILITY)
    if hit is None:
        f["eligibility_quote"] = Field(HELD, None, how="신청 자격 문장('현재 … 무주택세대구성원')을 찾지 못함")
        f["residence"] = Field(HELD, None, how="신청 자격 문장 없음")
    else:
        area = re.match(ELIGIBILITY, hit[1]).group("area")
        f["eligibility_quote"] = Field(FILLED, hit[1], hit[0], hit[1], "신청 자격 문장")
        if "에거주" not in area:
            f["residence"] = Field(FILLED, None, hit[0], hit[1], "자격 문장에 거주 요건 없음")
        elif "수도권" in area or all(w in area for w in CAPITAL_WORDS):
            f["residence"] = Field(FILLED, "수도권", hit[0], hit[1], "수도권(서울·인천·경기) 거주")
        elif area.startswith("국내"):
            f["residence"] = Field(FILLED, None, hit[0], hit[1], "국내 거주(지역 제한 없음)")
        else:
            f["residence"] = Field(HELD, None, hit[0], hit[1], f"거주 요건 지역을 알아보지 못함: {area[:30]}")
    free, joined, least = find_text(pages, ACCOUNT_FREE), find_text(pages, ACCOUNT_JOINED), find_text(pages, ACCOUNT_MIN)
    if free:
        f["account"] = Field(FILLED, None, free[0], free[1], "청약저축 가입 여부와 관계없이 신청")
        f["account_quote"] = Field(ABSENT, None, how="청약통장 요건 없음")
    elif least:
        m = re.search(ACCOUNT_MIN, least[1])
        months = int(m.group("n")) * (12 if m.group("u") == "년" else 1)
        f["account"] = Field(FILLED, {"months": months, "count": int(m.group("c"))}, least[0], least[1], "2순위 최소 가입기간·납입횟수")
        f["account_quote"] = Field(FILLED, least[1], least[0], least[1], "2순위 요건 문장")
    elif joined:
        f["account"] = Field(FILLED, "가입", joined[0], joined[1], "2순위도 청약통장 가입 필요")
        f["account_quote"] = Field(FILLED, joined[1], joined[0], joined[1], "2순위 요건 문장")
    else:
        f["account"] = Field(HELD, None, how="청약통장 요건(관계없음·2순위 가입 요건)을 원문에서 확인하지 못함")
        f["account_quote"] = Field(ABSENT, None, how="청약통장 요건 문장 없음")
    hit = find_text(pages, ADULT_SENT)
    f["adult_quote"] = (Field(FILLED, hit[1], hit[0], hit[1], "성년 요건 문장") if hit else
                        Field(ABSENT, None, how="성년 요건 별도 문장 없음(자격 문장을 인용)"))
    hit = find_text(pages, REWIN)
    f["rewin_quote"] = (Field(FILLED, hit[1], hit[0], hit[1], "재당첨 제한 문구") if hit else
                        Field(ABSENT, None, how="재당첨 제한 문구 없음"))
    return f


# ------------------------------------------------------------------ 신혼희망타운 공공분양(G3)
# 단순형(잔여세대): N45 "입주자저축가입여부,과거당첨여부,소득및자산요건을불문하며", "현재전국에거주(주민등록표등본기준)하는만19세
# 이상의무주택세대구성원", <표1> 유형 문장. 정규형: N46 "현재수도권[…]에거주하면서아래조건(1~4)을모두갖춘신혼부부" 등
NH_OPEN = r"(?:입주자|청약)저축가입여부[^■]{0,40}?불문"
NH_HEAD = r"현재(?P<area>전국|수도권)에거주\(주민등록표등본기준\)하는만19세이상의무주택세대구성원"
NH_TYPE_OPEN = {"신혼부부": "혼인기간이7년이내또는6세이하자녀", "예비신혼부부": "혼인을계획중이며,입주전까지혼인사실을증명할수있는자",
                "한부모": "를둔부또는모"}
NH_TYPE_FULL = r"현재수도권\[[^\]]{0,30}\]에거주하면서아래조건\(1~4\)을모두갖춘"
NH_TYPE_NAME = {"신혼부부": "신혼부부", "예비신혼부부": "예비신혼부부", "한부모": "한부모가족"}


def _newlywed_town_sale(pages):
    f = {}
    hit = find_text(pages, NH_OPEN)
    f["open_quote"] = (Field(FILLED, hit[1], hit[0], hit[1], "저축·당첨·소득·자산 불문 문구 — 단순형") if hit else
                       Field(ABSENT, None, how="불문 문구 없음 — 정규형"))
    if hit:
        head = find_text(pages, NH_HEAD)
        f["eligibility_quote"] = (Field(FILLED, head[1], head[0], head[1], "거주·나이 문장") if head else
                                  Field(HELD, None, how="단순형의 거주·나이 문장을 찾지 못함"))
        area = re.match(NH_HEAD, head[1]).group("area") if head else None
        f["residence"] = (Field(FILLED, "수도권" if area == "수도권" else None, head[0], head[1], f"{area} 거주") if head else
                          Field(HELD, None, how="거주 요건을 확인하지 못함"))
        found = {k: find_text(pages, re.escape(v)) for k, v in NH_TYPE_OPEN.items()}
    else:
        f["eligibility_quote"] = Field(ABSENT, None, how="정규형 — 유형별 자격 문장을 인용")
        found = {k: find_text(pages, NH_TYPE_FULL + name) for k, name in NH_TYPE_NAME.items()}
        f["residence"] = (Field(FILLED, "수도권", how="유형별 자격 문장이 모두 '수도권에 거주하면서'") if all(found.values()) else
                          Field(HELD, None, how="유형별 자격 문장(수도권 거주)을 모두 찾지 못함"))
    f["layer_quotes"] = {k: (Field(FILLED, v[1], v[0], v[1], "유형 자격 문장") if v else
                             Field(HELD, None, how=f"{k} 자격 문장을 찾지 못함")) for k, v in found.items()}
    return f


# ------------------------------------------------------------------ LH 공공분양(G3)
# 유형별 자격 문장 "현재수도권[서울특별시,경기도,인천광역시]에거주하면서아래조건(1~N)을모두갖춘분"(N49), 공급대상의 전용면적
SALE_RESIDENCE = r"현재(?P<area>[^■]{0,40}?)에거주하면서아래조건"
SALE_SUPPLY = r"공급대상:[^❚■]{0,160}"


def _public_sale(pages):
    f = {}
    hits = [m.group("area") for p in pages for m in re.finditer(SALE_RESIDENCE, p)]
    if hits and all("수도권" in a or all(w in a for w in CAPITAL_WORDS) for a in hits):
        f["residence"] = Field(FILLED, "수도권", how=f"유형별 자격 문장 {len(hits)}개 모두 수도권 거주")
    else:
        f["residence"] = Field(HELD, None, how="유형별 자격 문장의 거주 요건을 확인하지 못함" if hits else "유형별 자격 문장 없음")
    hit = find_text(pages[:2], SALE_SUPPLY)
    sizes = [int(x) for x in re.findall(r"(\d{2,3})(?:\.\d+)?m2", hit[1])] if hit else []
    if sizes:
        f["small"] = Field(FILLED, any(x <= 60 for x in sizes), hit[0], hit[1], f"공급대상 전용면적 {sizes}")
        f["large"] = Field(FILLED, any(x > 60 for x in sizes), hit[0], hit[1], f"공급대상 전용면적 {sizes}")
    else:
        f["small"] = f["large"] = Field(HELD, None, how="공급대상 전용면적을 찾지 못함")
    return f


# ------------------------------------------------------------------ SH 토지임대부 분양(G3-3)
# 유형별 자격 문장 "현재서울특별시또는인천광역시,경기도에거주하면서아래조건(1~N)을모두갖춘분"(N51), "「주택법」제63조에의한투기과열지구"
def _sh_land_sale(pages):
    f = {}
    hits = [m.group("area") for p in pages for m in re.finditer(SALE_RESIDENCE, p)]
    if hits and all("수도권" in a or all(w in a for w in CAPITAL_WORDS) for a in hits):
        f["residence"] = Field(FILLED, "수도권", how=f"유형별 자격 문장 {len(hits)}개 모두 서울·인천·경기 거주")
    else:
        f["residence"] = Field(HELD, None, how="유형별 자격 문장의 거주 요건을 확인하지 못함" if hits else "유형별 자격 문장 없음")
    hit = find_text(pages, r"투기과열지구로서,?1순위자격")
    f["overheated"] = (Field(FILLED, True, hit[0], hit[1], "투기과열지구 — 1순위 요건 강화") if hit else
                       Field(HELD, None, how="투기과열지구 여부(생애최초 1순위 요건)를 원문에서 확인하지 못함"))
    return f


# ------------------------------------------------------------------ 전체
def extract(pages: List[str], siblings_of=None, llm: Optional[LLM] = None) -> Dict:
    """siblings_of(template) → 형제 정답 시트 목록(같은 템플릿, 평가 시 다듬기용 공고만). llm이 있으면 결정론이 못 채운
    빈칸만 LLM에게 묻는다(검증을 통과해야 채움)."""
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
          "lh.deundeun": dict, "sh.vacant": dict, "lh.national_rental": lambda: _national_rental(pages),
          "lh.permanent_rental": lambda: _permanent_rental(pages), "lh.integrated_rental": dict,
          "lh.public_rental": lambda: _public_rental(pages),
          "lh.newlywed_town_sale": lambda: _newlywed_town_sale(pages),
          "lh.public_sale": lambda: _public_sale(pages),
          "sh.land_sale": lambda: _sh_land_sale(pages),
          "sh.national_rental": lambda: _sh_national_rental(pages),
          "sh.permanent_rental": lambda: _sh_permanent_rental(pages),
          "lh.elderly_welfare": lambda: _elderly_welfare(pages), "sh.multichild_rental": lambda: _sh_multichild(pages),
          "lh.integrated_job": lambda: _integrated_job(pages),
          "lh.share_sale": lambda: _share_sale(pages),
          "lh.select_rental": lambda: _select_rental(pages),
          "sh.newlywed": lambda: _sh_newlywed(pages, ann, sib, program, llm),
          "sh.jeonse2": lambda: _jeonse2(pages, ann, sib, program, llm),
          "sh.jeonse": lambda: _jeonse(pages, ann, sib, program, llm),
          "lh.happy_housing": lambda: _happy_housing(pages, ann, sib, program, pages[0][:200], llm),
          "sh.happy_housing": lambda: _sh_happy(pages, ann)}[template]
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


def field_label(template: Optional[str], path: str) -> str:
    """보류 빈칸 경로 → 화면에 보일 이름(템플릿 빈칸 설명의 앞부분). 모르는 경로·범위 점검 문구는 그대로."""
    head = path.partition(".")[0]
    if head == "announcement_date" and ":" not in path:
        return "모집공고일"
    p = next((p for p in T.TEMPLATES.get(template, {}).get("params", []) if p.name == head), None)
    return p.note.split(" — ")[0] if p and ":" not in path else path


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


MISSING_QUOTE = re.compile(r"^(?P<layer>[^/]+)/(?P<cid>N\d+-[A-Za-z0-9-]+): '(?P<quote>.+)'$")


def _llm_overrides(ext: Dict, doc: Dict, missing: List[str], pages, llm: LLM) -> Dict[str, list]:
    """행복주택: 템플릿 문구가 이 공고에 없는 조건 → 같은 뜻의 원문 문장으로 바꾼 인용문 목록(조건 접미사 → 문장들)."""
    out = {}
    for m in missing:
        mm = MISSING_QUOTE.match(m)
        if not mm or mm.group("layer") not in doc["layers"]:
            continue
        cond = next((c for c in doc["layers"][mm.group("layer")]["conditions"] if c["id"] == mm.group("cid")), None)
        if cond is None:
            continue
        hit = llm_sentence(pages, llm, mm.group("quote"), hint_pages=[cond["source"].get("page")])
        if not hit:
            continue
        suffix = mm.group("cid").split("-", 1)[1]
        keep = out.get(suffix) or [q["text"] if isinstance(q, dict) else q for q in cond["source"]["quote"]]
        out[suffix] = keep + [hit[1]]
    return out


def _check_key(c: Dict) -> str:
    """조건의 판정식(공고 번호 접두어를 뗀 것) — 같으면 같은 조건이다."""
    return re.sub(r'"N\d+-|"DRAFT-|"NEW-', '"X-', json.dumps(c["check"], ensure_ascii=False, sort_keys=True))


def phrasebook(suffix: str, check_key: str, exclude: str = "") -> List[str]:
    """표현 사전(v3 ①-2): 같은 조건(같은 조건 접미사·같은 판정식)을 다른 등록 공고들은 원문에서 어떻게 적었나 — 그 인용문들.
    exclude: 평가할 때 자기 공고의 등록 표현을 빼려고(정답 누출 방지)."""
    from rule_data import notice_ids
    out = []
    for n in notice_ids():
        if n == exclude:
            continue
        for ld in sv.notice_doc(n)["layers"].values():
            for c in ld["conditions"]:
                if c["id"].split("-", 1)[1] == suffix and _check_key(c) == check_key:
                    for q in c["source"]["quote"]:
                        t = q["text"] if isinstance(q, dict) else q
                        if t not in out:
                            out.append(t)
    return out


def _find_quote(pages, text: str) -> Optional[str]:
    """원문에 그 문장이 있으면 원문 표현 — 그대로 → 숫자만 다름 → 값·핵심 표현이 같은 구간."""
    if on_page(pages, sv.normalize(text)):
        return text
    hit = loose_find(pages, text)
    if hit:
        return hit[1]
    hit = relocate(pages, text)
    return hit[2] if hit else None


def _relocated_overrides(doc: Dict, missing: List[str], pages, nid: str = "") -> Dict[str, list]:
    """행복주택(결정론, v3 ①): 템플릿 문구가 이 공고에 없는 조건 → 그 문구를 ① 값·핵심 표현이 같은 원문 구간으로,
    ② 안 되면 표현 사전(같은 조건의 다른 공고 원문 표현)에서 이 공고에 있는 것으로 바꾼 인용문 목록(조건 접미사 → 문장들).
    못 찾은 문구는 그대로 두어 보류로 남긴다."""
    out = {}
    for m in missing:
        mm = MISSING_QUOTE.match(m)
        if not mm or mm.group("layer") not in doc["layers"]:
            continue
        cond = next((c for c in doc["layers"][mm.group("layer")]["conditions"] if c["id"] == mm.group("cid")), None)
        if cond is None:
            continue
        suffix = mm.group("cid").split("-", 1)[1]
        found = _find_quote(pages, mm.group("quote"))
        if found is None:
            book = [t for t in phrasebook(suffix, _check_key(cond), exclude=nid) if t != mm.group("quote")]
            found = next((f for f in (_find_quote(pages, t) for t in book) if f), None)
        if found is None:
            continue
        quotes = out.get(suffix) or [q["text"] if isinstance(q, dict) else q for q in cond["source"]["quote"]]
        # 생성 스크립트가 못 찾은 문구를 목록에서 이미 뺐으면(날짜 문구 등) 찾은 문장을 덧붙인다
        out[suffix] = [found if q == mm.group("quote") else q for q in quotes] if mm.group("quote") in quotes \
            else quotes + [found]
    return out


NO_EVIDENCE = "(근거 문장 없음)"


def _build(ext: Dict, nid: str, pdf, pages: List[str]):
    """시트로 규칙을 만들고, 찾지 못한 인용문에 **근거 문장이 하나도 없는 조건**도 더한다 — 생성 스크립트가 날짜가 든 템플릿
    문구를 빼고 나면 인용문 목록이 비는 일이 있다(2026-10-28 발견: N8 한부모 6세 이하 자녀). 근거 없는 조건은 보류."""
    doc, missing = T.build(to_sheet(ext, nid), pdf, pages)

    def walk(layer, conds):
        for c in conds:
            if c.get("tracks"):
                for t in c["tracks"]:
                    walk(layer, t["conditions"])
            elif not c.get("source", {}).get("quote"):     # 등록 규칙에는 0개(도출 설명만 있는 조건도 원문 문장은 있다)
                missing.append(f"{layer}/{c['id']}: '{NO_EVIDENCE}'")
    for layer, ld in doc["layers"].items():
        walk(layer, ld["conditions"])
    return doc, missing


def gate(ext: Dict, pdf, pages: List[str], nid: str = "NEW", llm: Optional[LLM] = None) -> Dict:
    """추출 시트로 규칙을 만들어 본다. 결과:
    - held: 보류된 빈칸, critical_held: 그중 판정에 직접 쓰이는 것(있으면 이 공고는 자동 판정하지 않는다 — P2 규칙)
    - missing: 원문에서 찾지 못한 인용문(그 조건은 보류), doc: 만들어진 규칙(만들 수 없으면 None, blocked에 이유)"""
    held = held_paths(ext["fields"])
    if ext["announcement_date"].status != FILLED:
        held.insert(0, "announcement_date")
    problems = _sanity(ext)
    critical = [p for p in held if ext["template"] and is_critical(ext["template"], p)] + problems
    out = dict(template=ext["template"], held=held, critical_held=critical, missing=[], doc=None, blocked=None,
               stale=[], restrictions=[])
    if not ext["template"]:
        out["blocked"] = "사업 유형(템플릿)을 정하지 못함"
        return out
    relaxed = relaxed_notice(pages) or variant_notice(ext["template"], pages)
    if relaxed:
        out["blocked"] = relaxed
        return out
    try:
        out["doc"], out["missing"] = _build(ext, nid, pdf, pages)
    except (KeyError, TypeError, ValueError) as e:     # 필수 빈칸이 보류라 규칙을 만들 수 없음
        # 화면에 그대로 나가는 이유 — 내부 오류 문구 대신 보류 빈칸을 알린다(critical_held가 있으면 그 안내가 쓰인다)
        out["build_error"] = f"{type(e).__name__} {e}"
        if not critical:
            out["blocked"] = "공고문에서 판정 규칙을 만드는 데 필요한 값을 모두 찾지 못해 자동 판정하지 않습니다."
        return out
    if ext["template"] == "lh.happy_housing" and out["missing"]:
        ov = _relocated_overrides(out["doc"], out["missing"], pages, nid)
        if ov:
            ext["fields"]["overrides"] = Field(FILLED, ov, how=f"값·핵심 표현이 같은 원문 — 표현이 다른 조건 {len(ov)}개")
            out["doc"], out["missing"] = _build(ext, nid, pdf, pages)
    if llm is not None and ext["template"] == "lh.happy_housing" and out["missing"]:
        ov = _llm_overrides(ext, out["doc"], out["missing"], pages, llm)
        if ov:
            ext["fields"]["overrides"] = Field(FILLED, ov, how=f"LLM({llm.slot.name}) — 표현이 다른 조건 {len(ov)}개")
            out["doc"], out["missing"] = _build(ext, nid, pdf, pages)
    # P2 선행 안전장치: 기준표 연도(인용문에 금액 없는 조건), 템플릿에 없는 새 제한 문구
    kind = ext["fields"].get("kind").value if isinstance(ext["fields"].get("kind"), Field) else None
    out["stale"] = reference_guard(out["doc"], pages, ext["template"], kind)
    if out["stale"]:                     # 기준 연도가 바뀐 공고 — 운영자가 승인한 새 기준표가 있으면 그 표로(docs/09 §21 T3)
        doc2, swaps = swap_successors(out["doc"], pages)
        if swaps:
            stale2 = reference_guard(doc2, pages, ext["template"], kind)
            if len(stale2) < len(out["stale"]):
                out["doc"], out["stale"], out["swaps"] = doc2, stale2, swaps
    out["missing"] += out["stale"]
    out["missing"] += table_positions(out["doc"], pdf, pages)
    out["restrictions"] = new_restrictions(out["doc"], pages)
    return out


# ------------------------------------------------------------------ P2 선행 안전장치 (docs/09 §17)
LOOKUP_REF = re.compile(r'"lookup":\s*\[\s*"(income_standard[^"]*)"')


def _walk(conditions):
    for c in conditions:
        yield c
        for t in c.get("tracks", []):
            yield from _walk(t["conditions"])


def _reference(ref_id: str) -> dict:
    import json
    return json.loads((sv.RULES / "reference" / f"{ref_id}.json").read_text(encoding="utf-8"))


def _own_required(ref: dict) -> List[str]:
    return sorted({f"{ref['table'][str(s)][str(r)]:,}" for s, r in ref.get("required_in_every_notice", [])})


def required_reference_values(ref_id: str, template: str, kind=None) -> List[str]:
    """새 공고에 있어야 할 기준표 대표 금액 — 같은 템플릿(같은 유형) 등록 공고들이 공통으로 싣는 금액."""
    ref = _reference(ref_id)
    if ref.get("successor_of"):          # 승인된 새 기준표 — 아직 같은 템플릿 등록 공고가 없으니 그 표의 '모든 공고가 싣는 칸'
        return _own_required(ref)
    sets = []
    for nid in T.sheet_ids():
        sheet = T.gold_sheet(nid)
        if sheet["template"] != template or (kind is not None and sheet["params"].get("kind") != kind):
            continue
        if nid not in ref.get("cited_pages", {}):
            continue
        req = ref.get("required_by_notice", {}).get(nid, ref.get("required_in_every_notice", []))
        sets.append({f"{ref['table'][str(s)][str(r)]:,}" for s, r in req})
    return sorted(set.intersection(*sets)) if sets else []


def reference_guard(doc: Dict, pages: List[str], template: str, kind=None) -> List[str]:
    """기준표를 직접 참조하는 조건 중, 그 기준표의 대표 금액이 원문에 없으면(다른 기준 연도) 그 조건을 보류 대상으로 돌려준다.
    인용문에 금액이 없는 조건(예: 청년매입 3순위 본인 소득)이 연도가 바뀌어도 그대로 통과하는 것을 막는다."""
    text = "".join(pages)
    out = []
    for layer, ld in doc["layers"].items():
        for c in _walk(ld["conditions"]):
            for ref_id in set(LOOKUP_REF.findall(json_dumps(c.get("check", {})))):
                need = required_reference_values(ref_id, template, kind)
                lost = [v for v in need if v not in text]
                if lost:
                    out.append(f"{layer}/{c['id']}: '기준표 {ref_id} 금액 {lost[0]}원 등 {len(lost)}개가 원문에 없음(다른 기준 연도)'")
    return out


def successors() -> Dict[str, List[dict]]:
    """승인된 새 기준표 — rules/reference/의 'successor_of'가 있는 표(후보 상태 CANDIDATE는 제외). 옛 표 id → 새 표들(최근 연도 먼저).
    후보는 src/reference_candidates.py가 만들고, 운영자가 원문과 대조해 등록한다(docs/08 '새 기준표 등록')."""
    out: Dict[str, List[dict]] = {}
    for path in sorted((sv.RULES / "reference").glob("income_standard*.json")):
        ref = _reference(path.stem)
        if ref.get("successor_of") and ref.get("status") != "CANDIDATE":
            out.setdefault(ref["successor_of"], []).append(ref)
    for refs in out.values():
        refs.sort(key=lambda r: str(r.get("year_basis") or ""), reverse=True)
    return out


def swap_successors(doc: Dict, pages: List[str]):
    """규칙이 참조하는 기준표마다, 승인된 새 표의 '모든 공고가 싣는 칸' 금액이 이 공고 원문에 전부 있으면 그 표로 바꾼 규칙.
    → (새 규칙, {옛 표: 새 표}). 바꿀 표가 없으면 (doc, {})."""
    import json
    text = "".join(pages)
    blob = json.dumps(doc, ensure_ascii=False)
    swaps = {}
    for old in sorted(set(LOOKUP_REF.findall(blob))):
        for new in successors().get(old, []):
            need = _own_required(new)
            if need and all(v in text for v in need):
                swaps[old] = new["id"]
                break
    for old, new in swaps.items():
        blob = blob.replace(f'"{old}"', f'"{new}"')
    return (json.loads(blob), swaps) if swaps else (doc, {})


def _money_out(out) -> List[int]:
    return [a for a in (out or []) if isinstance(a, int) and not isinstance(a, bool) and a >= 1_000_000]


def table_positions(doc: Dict, pdf, pages: List[str]) -> List[str]:
    """가구원수별 금액 결정표(size → 금액)의 금액이 원문 표에서 **다른 가구원수 칸에만** 있으면 그 표를 보류한다(docs/09 §21 T4).
    인용문 대조는 '금액이 그 쪽 어딘가에 있음'만 보므로, 값이 다른 가구원수 자리에 들어가도 통과할 수 있다. 원문 표에서 그 금액을
    찾지 못하면 판단하지 않는다(인용문 대조에 맡김). 표 읽기(src/pdf_tables.py)를 쓸 수 없으면 아무것도 하지 않는다."""
    want: Dict[int, List[tuple]] = {}
    for name, t in doc.get("tables", {}).items():
        page = t.get("source", {}).get("page")
        if "size" not in t.get("columns", []) or not page:
            continue
        for row in t.get("rows", []):
            size = row.get("when", {}).get("size")
            if isinstance(size, int) and not isinstance(size, bool):
                want.setdefault(page, []).extend((name, size, a) for a in _money_out(row.get("out")))
    if not want:
        return []
    try:
        import pdf_tables as P
        cells, _ = P.merge([P.income_cells(t) for t in P.read_tables(pdf, want)])
    except Exception:      # noqa: BLE001 — pdfplumber 없음·읽기 실패: 위치 확인 없이 지금처럼
        return []
    sizes: Dict[tuple, set] = {}
    for c in cells:
        sizes.setdefault((c.page, c.amount), set()).add(c.size)
    out = []
    for page, items in want.items():
        for name, size, amount in items:
            seen = sizes.get((page, amount))
            if seen and size not in seen:
                out.append(f"table:{name}: '{amount:,}원이 원문 표 p.{page}에서 {sorted(seen)}인 칸에 있음({size}인 행에 쓰임)'")
    return out


def json_dumps(x) -> str:
    import json
    return json.dumps(x, ensure_ascii=False)


RESTRICTION = [re.compile(p) for p in (r"이번공고에서는모집하지않", r"[가-힣·()]{2,20}거주자만(?:신청|공급)",
                                       r"현재[가-힣]{2,10}(?:특별시|광역시|도|시)에거주하는")]


def new_restrictions(doc: Dict, pages: List[str]) -> List[tuple]:
    """지역·모집 제한 문구 중 만든 규칙의 어느 조건도 인용하지 않는 것 — 템플릿에 없는 제한이 새로 생겼을 수 있다."""
    quotes = [sv.normalize(q["text"] if isinstance(q, dict) else q)
              for ld in doc["layers"].values() for c in _walk(ld["conditions"]) for q in c["source"].get("quote", [])]
    out = []
    for i, t in enumerate(pages, 1):
        for rx in RESTRICTION:
            for m in rx.finditer(t):
                key = m.group(0)[:10]
                if not any(key in q for q in quotes):
                    out.append((i, m.group(0)))
    return sorted(set(out))


# 입주자격 완화 공고(G2 2026-11-01 — 화성동탄 행복주택·화성서부권 국민임대): 이번 공고에 한해 소득·자산 요건을 빼거나 기간 요건을
# 넓힌다. 템플릿은 평상시 요건이라 '지원 불가'가 틀릴 수 있으므로 자동 판정하지 않는다(등록 28건에는 이 표현이 없다).
RELAXED = re.compile(r"입주자격완화|【완화조건】|완화기준은해당공고에한하여")


# 변형 공고: 통합공공임대 일자리연계형 지원주택은 직업·근무지 요건과 거주기간이 일반형과 달라 일반형 틀로 판정하지 않는다(G2).
# 공공임대 틀은 예비입주자 모집만 — 최초 입주자 모집(특별·일반공급, 소득·자산 기준)은 다른 사업이다(G4).
VARIANT = {"lh.youth_rental": (re.compile(r"자립준비청년"), True,      # 보호종료 5년 이내 등 — 나이 기준일이 없다(2026-11-08)
                                "청년매입임대 '{}' 우선공급 공고(p.1) — 보호종료·시설 퇴소 요건이 일반 청년과 달라 자동 판정하지 않습니다"),
           "lh.integrated_rental": (re.compile(r"일자리연계형"), True,
                                    "통합공공임대 '{}' 공고(p.1) — 직업·근무지 요건이 일반형과 달라 자동 판정하지 않습니다"),
           "lh.public_rental": (re.compile(r"예비입주자"), False,
                                "공공임대 최초 입주자 모집 공고(p.1에 '예비입주자' 없음) — 특별·일반공급과 소득·자산 기준이 있어 "
                                "예비입주자 모집 틀로 판정하지 않습니다")}


def variant_notice(template: Optional[str], pages: List[str]) -> Optional[str]:
    """block_if_found=True면 표지(첫 쪽)에 그 표현이 있을 때, False면 없을 때 막는다."""
    if template not in VARIANT:
        return None
    rx, block_if_found, msg = VARIANT[template]
    m = rx.search("".join(pages[:1]))
    if block_if_found:
        return msg.format(m.group()) if m else None
    return None if m else msg


def relaxed_notice(pages: List[str]) -> Optional[str]:
    for i, p in enumerate(pages):
        m = RELAXED.search(p)
        if m:
            return (f"입주자격 완화 공고(p.{i + 1} '{m.group()}') — 이번 공고에 한해 소득·자산·기간 요건이 평상시와 달라 "
                    "자동 판정하지 않습니다")
    return None


def held_condition_ids(doc: Dict, missing: List[str]) -> set:
    """찾지 못한 인용문·기준표가 걸린 조건 ID. 메시지는 '<계층>/<조건 ID>: …' 또는 'table:<표 이름>: …'.
    조건 ID에 '/'가 들어가도(DRAFT-R7/R7b) 정확히 맞추고, 표 인용문을 못 찾으면 그 표를 쓰는 조건을 모두 보류한다."""
    tables = {m.split(": ", 1)[0][len("table:"):] for m in missing if m.startswith("table:")}
    out = set()
    for ld in doc["layers"].values():
        for c in _walk(ld["conditions"]):
            check = json.dumps(c.get("check", {}), ensure_ascii=False)
            if any(f"/{c['id']}: " in m for m in missing) or                     any(c.get("table") == t or f'"{t}"' in check for t in tables):
                out.add(c["id"])
    return out


def affected_conditions(conditions, condition_ids) -> set:
    """보류 대상 조건(트랙 안쪽 포함)을 품은 최상위 조건 ID."""
    def ids(c):
        yield c.rule_id
        for t in c.tracks or []:
            for cc in t.conditions:
                yield from ids(cc)
    return {c.rule_id for c in conditions if any(i in condition_ids for i in ids(c))}


def adjust_verdict(result, affected: set, restricted: bool) -> str:
    """초안 판정: 보류 대상 조건이 판정에 쓰였거나 새 제한 문구가 있으면 '지원 가능'을 '수동 확인'으로 낮춘다.
    '지원 불가'는 불충족 조건이 전부 보류 대상일 때만 '수동 확인'으로."""
    v = result.verdict
    if v == "ELIGIBLE" and (affected or restricted):
        return "MANUAL_REVIEW"
    if v == "INELIGIBLE" and affected and set(result.failed) <= affected:
        return "MANUAL_REVIEW"
    return v
