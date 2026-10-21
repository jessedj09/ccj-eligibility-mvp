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
SAMPLE_DIRS = ("sample_lh", "sample_sh")

# PDF는 ➀(U+2780 계열)를 쓰고 데이터는 ①을 쓰는 등 표기가 섞여 있다.
_DINGBAT = {chr(0x2780 + i): chr(0x2460 + i) for i in range(10)}
_DINGBAT.update({chr(0x278A + i): chr(0x2460 + i) for i in range(10)})
_DINGBAT.update({"“": '"', "”": '"', "‘": "'", "’": "'"})


def normalize(text: str) -> str:
    # 일부 PDF(예: SH 공공한옥 공고)는 단어 사이 공백 자리에 NUL 같은 제어문자를 넣는다 - 공백처럼 지운다
    text = "".join(ch for ch in text if ch >= " " or ch in "\t\n\r")
    text = "".join(_DINGBAT.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", text)


def notice_doc(nid: str) -> dict:
    return json.loads((RULES / "notices" / f"{nid}.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def pdf_path(nid: str) -> Path:
    """공고 데이터의 source.document 파일을 sample_lh/·sample_sh/에서 찾는다."""
    name = notice_doc(nid)["source"]["document"]
    for d in SAMPLE_DIRS:
        if (PROJECT / d / name).exists():
            return PROJECT / d / name
    raise FileNotFoundError(f"{nid}: 공고문 PDF '{name}'을 {SAMPLE_DIRS}에서 찾지 못했습니다")


# 쪽 단위 추출 실패 기록: {pdf 경로: [실패한 쪽 번호]}. 예: pypdf 6.21은 SH 장기미임대 PDF p.26(주택목록, KSCms-UHC-H 글꼴)에서
# UnicodeDecodeError를 낸다(6.19는 경고만). 한 쪽이 실패해도 나머지 대조는 계속하고, 그 쪽은 빈 텍스트로 둔다 —
# 그 쪽에 인용문이 있으면 대조에서 '없음'으로 드러나므로 조용히 통과하지 않는다.
EXTRACTION_FAILURES: Dict[str, List[int]] = {}


def extract_pages(path) -> List[str]:
    """PDF 전 쪽의 정규화 텍스트. 생성 스크립트(tools/gen_*.py)도 이 함수를 쓴다."""
    import logging
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    pages = []
    for i, page in enumerate(PdfReader(str(path)).pages, 1):
        try:
            pages.append(normalize(page.extract_text() or ""))
        except Exception:   # noqa: BLE001 — 라이브러리 내부 디코딩 오류 등, 쪽 단위로 격리
            EXTRACTION_FAILURES.setdefault(str(path), []).append(i)
            pages.append("")
    return pages


@lru_cache(maxsize=None)
def pdf_pages(nid: str) -> List[str]:
    return extract_pages(pdf_path(nid))


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


def all_conditions(conditions):
    """계층 조건 전부 — 순위·유형 묶음(tracks) 안의 조건까지 내려간다(C4)."""
    for c in conditions:
        yield c
        for t in c.get("tracks", []):
            yield from all_conditions(t["conditions"])


def verify_notice(nid: str) -> Report:
    doc = notice_doc(nid)
    report = Report()
    report.checked += 1
    if hashlib.sha256(pdf_path(nid).read_bytes()).hexdigest() != doc["source"]["sha256"]:
        report.problems.append(f"{nid}: PDF sha256이 데이터에 기록된 값과 다름 — 공고문이 바뀌었거나 데이터가 오래됨")
    for layer, ls in doc["layers"].items():
        for c in all_conditions(ls["conditions"]):
            if "quote" not in c["source"]:
                if c.get("check") is not True:  # 입주 전 확인(check: true) 외에는 인용문이 있어야 한다
                    report.problems.append(f"{nid} {layer}/{c['id']}: source.quote 없음")
                continue
            _check_source(report, nid, f"{layer}/{c['id']}", c["source"])
    for name, t in doc.get("tables", {}).items():
        _check_source(report, nid, f"table:{name}", t["source"])
    return report


def verify_income_reference(ref_id: str = "income_standard") -> Report:
    """소득 기준표(rules/reference/<ref_id>.json) 대조 — 두 겹.
    1) 공고별: 이 기준표를 쓰는 공고마다 `required_in_every_notice` 값이 그 공고의 `cited_pages` 쪽에 모두 있어야 한다.
       기준표를 쓰는 공고가 `cited_pages`에 없으면 그것도 불일치다(새 공고를 추가하고 대조를 빠뜨리는 것을 막는다).
    2) 전체: 표의 모든 값(7인 이상 가산액 포함)이 어느 공고의 cited_pages에든 있어야 한다."""
    from rule_data import notice_ids
    ref = json.loads((RULES / "reference" / f"{ref_id}.json").read_text(encoding="utf-8"))
    report = Report()
    cited = ref["cited_pages"]
    for nid in notice_ids():
        if f'"{ref_id}"' not in json.dumps(notice_doc(nid), ensure_ascii=False):
            continue
        if nid not in cited:
            report.problems.append(f"{ref_id}: {nid}가 이 소득 기준표를 쓰지만 cited_pages에 없음")
            continue
        for size, ratio in ref.get("required_by_notice", {}).get(nid, ref["required_in_every_notice"]):
            report.checked += 1
            text = f"{ref['table'][str(size)][str(ratio)]:,}"
            if not any(page_has(nid, pg, text) for pg in cited[nid]):
                report.problems.append(f"{ref_id}: {nid} p.{cited[nid]}에 {size}인 {ratio}% {text}원 없음")
    numbers = [v for row in ref["table"].values() for v in row.values()]
    if ref.get("per_person_adder_7plus"):
        numbers.append(ref["per_person_adder_7plus"])
    for n in numbers:
        report.checked += 1
        text = f"{n:,}"
        if not any(page_has(nid, pg, text) for nid, pages in cited.items() for pg in pages):
            report.problems.append(f"{ref_id}: {text} 이(가) 어느 공고의 cited_pages에도 없음")
    return report


def verify_all() -> Dict[str, Report]:
    from rule_data import notice_ids
    result = {nid: verify_notice(nid) for nid in notice_ids()}
    for path in sorted((RULES / "reference").glob("income_standard*.json")):
        result[path.stem] = verify_income_reference(path.stem)
    return result
