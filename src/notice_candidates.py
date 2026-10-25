# -*- coding: utf-8 -*-
"""notice_candidates.py — 공고문 텍스트에서 등록·식별에 필요한 후보를 결정론으로 뽑는다(LLM 없음).

새 공고 등록 도구(tools/notice_intake.py)와 공고 업로드 화면(P0, src/notice_identify.py)이 함께 쓴다.
모두 '후보'다 — 판정에 직접 쓰지 않는다. 등록 공고 26건에서 공고일 26/26·접수기간 29/29·사업 유형 26/26·
기준일 리터럴 30/30을 후보에 올렸다(tests/test_e1_intake.py).
"""
import json
import re
from collections import Counter
from datetime import date, datetime
from typing import Dict, List, Optional

import source_verify as sv
from rule_data import LAYERS, load_notice, notice_ids

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
    for path in sorted((sv.RULES / "reference").glob("income_standard*.json")):
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


def registered_as(sha: str) -> Optional[str]:
    for nid in notice_ids():
        if sv.notice_doc(nid)["source"]["sha256"] == sha:
            return nid
    return None
