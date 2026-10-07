# -*- coding: utf-8 -*-
"""source_verify.py — 규칙 데이터(rules/*.json)의 원문 근거가 공고문 PDF와 맞는지 자동 대조.

검사 항목
1. 조건의 `source.quote`(문자열 또는 {page, text})가 **표시된 쪽**에 실제로 있는가.
2. 결정표 `source.quote`(수치)가 표시된 쪽에 있는가.
3. 기준값 표(소득기준표)의 모든 수치가 `cited_pages`가 가리키는 각 공고문의 쪽에 있는가.
4. 공고문 PDF의 sha256이 데이터에 기록된 값과 같은가.

`source.derivation`(공고문에 없는 지침·도출 설명)은 PDF 대조 대상이 아니며 개수만 보고한다.
PDF 텍스트는 글자 사이에 공백이 끼므로 모든 공백을 제거하고, 원문자·전각 표기를 정규화해 비교한다.
"""

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

PROJECT = Path(__file__).resolve().parent.parent
RULES = PROJECT / "rules"
PDF_GLOB = {"N1": "*공릉*.pdf", "N2": "*관악봉천*.pdf", "N3": "*번동3*.pdf"}

# PDF는 ➀(U+2780 계열)를 쓰고 데이터는 ①을 쓰는 등 표기가 섞여 있다.
_DINGBAT = {chr(0x2780 + i): chr(0x2460 + i) for i in range(10)}
_DINGBAT.update({chr(0x278A + i): chr(0x2460 + i) for i in range(10)})
_DINGBAT.update({"“": '"', "”": '"', "‘": "'", "’": "'"})


def normalize(text: str) -> str:
    text = "".join(_DINGBAT.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", text)


@lru_cache(maxsize=None)
def pdf_path(nid: str) -> Path:
    return next((PROJECT / "sample_lh").glob(PDF_GLOB[nid]))


@lru_cache(maxsize=None)
def pdf_pages(nid: str) -> List[str]:
    from pypdf import PdfReader
    return [normalize(p.extract_text() or "") for p in PdfReader(str(pdf_path(nid))).pages]


def page_has(nid: str, page: int, text: str) -> bool:
    pages = pdf_pages(nid)
    return 1 <= page <= len(pages) and normalize(text) in pages[page - 1]


@dataclass
class Report:
    checked: int = 0
    derivations: int = 0
    problems: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _check(report: Report, nid: str, where: str, page: int, text: str) -> None:
    report.checked += 1
    if page_has(nid, page, text):
        return
    found = [i + 1 for i, p in enumerate(pdf_pages(nid)) if normalize(text) in p]
    hint = f" (다른 쪽에는 있음: {found})" if found else " (어느 쪽에도 없음)"
    report.problems.append(f"{nid} {where}: p.{page}에 '{text}' 없음{hint}")


def _check_source(report: Report, nid: str, where: str, source: dict) -> None:
    if "derivation" in source:
        report.derivations += 1
    for q in source.get("quote", []):
        if isinstance(q, dict):
            _check(report, nid, where, q["page"], q["text"])
        else:
            _check(report, nid, where, source["page"], q)


def verify_notice(nid: str) -> Report:
    doc = json.loads((RULES / "notices" / f"{nid}.json").read_text(encoding="utf-8"))
    report = Report()
    report.checked += 1
    if hashlib.sha256(pdf_path(nid).read_bytes()).hexdigest() != doc["source"]["sha256"]:
        report.problems.append(f"{nid}: PDF sha256이 데이터에 기록된 값과 다름 — 공고문이 바뀌었거나 데이터가 오래됨")
    for layer, ls in doc["layers"].items():
        for c in ls["conditions"]:
            if "quote" not in c["source"]:
                if c["check"] is not True:      # 입주 전 확인(check: true) 외에는 인용문이 있어야 한다
                    report.problems.append(f"{nid} {layer}/{c['id']}: source.quote 없음")
                continue
            _check_source(report, nid, f"{layer}/{c['id']}", c["source"])
    for name, t in doc.get("tables", {}).items():
        _check_source(report, nid, f"table:{name}", t["source"])
    return report


def verify_income_reference() -> Report:
    """공고문마다 필요한 비율 행만 싣기 때문에, 각 수치는 `cited_pages`의 어느 공고·쪽에든 있으면 된다."""
    ref = json.loads((RULES / "reference" / "income_standard.json").read_text(encoding="utf-8"))
    report = Report()
    numbers = [v for row in ref["table"].values() for v in row.values()] + [ref["per_person_adder_7plus"]]
    for n in numbers:
        report.checked += 1
        text = f"{n:,}"
        where = [(nid, pg) for nid, pages in ref["cited_pages"].items() for pg in pages if page_has(nid, pg, text)]
        if not where:
            report.problems.append(f"income_standard: {text} 이(가) cited_pages({ref['cited_pages']}) 어디에도 없음")
    return report


def verify_all() -> Dict[str, Report]:
    result = {nid: verify_notice(nid) for nid in PDF_GLOB}
    result["income_standard"] = verify_income_reference()
    return result
