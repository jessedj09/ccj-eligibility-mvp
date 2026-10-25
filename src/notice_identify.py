# -*- coding: utf-8 -*-
"""notice_identify.py — 업로드한 공고문 PDF가 어떤 등록 공고인지 알아본다(공고 업로드 판정 P0, docs/09 ②).

판정은 하지 않는다. 결과는 네 가지다.
- REGISTERED: PDF 지문(sha256)이 등록 공고의 원문과 같다 → 그 공고의 검증된 규칙으로 판정해도 된다.
- SAME_NOTICE_OTHER_FILE: 지문은 다르지만 공고일·사업 유형(·단지명)이 등록 공고와 같다 → 같은 공고의 다른 파일
  (다시 내려받기·정정·재게시)일 수 있다. 정정 공고면 조건이 바뀌었을 수 있으므로 사용자가 확인한 뒤에만 판정한다.
- UNREGISTERED: 등록 공고가 아니다 → 판정하지 않고 공고일·접수기간·사업 유형 후보만 보인다.
- UNREADABLE: PDF가 아니거나 글자를 읽을 수 없다(스캔 이미지 등).

식별에 쓰는 값은 등록 규칙 데이터(공고일·사업·제목·원문 sha256)뿐이라 배포 서버에서 등록 PDF를 다시 읽지 않는다.
업로드 파일은 디스크에 남기지 않는다.
"""
import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import notice_candidates as nc
import source_verify as sv
from rule_data import load_notice, notice_ids

REGISTERED, SAME_NOTICE_OTHER_FILE, UNREGISTERED, UNREADABLE = (
    "REGISTERED", "SAME_NOTICE_OTHER_FILE", "UNREGISTERED", "UNREADABLE")


@dataclass
class Identification:
    status: str
    notice_id: Optional[str] = None
    reason: str = ""
    sha256: str = ""
    pages: int = 0
    issuer: Optional[str] = None
    program: Optional[str] = None
    announcement: Optional[str] = None                     # 공고일 후보(가장 많이 나온 것)
    windows: List[dict] = field(default_factory=list)      # 청약 접수기간 후보(청약·신청·접수 문맥만)
    similar: List[str] = field(default_factory=list)       # 같은 사업의 등록 공고(같은 공고는 아님)
    ambiguous: List[str] = field(default_factory=list)     # 공고일·사업이 같은데 단지를 가리지 못한 등록 공고


def _same_program(issuer: Optional[str], program: Optional[str], nid: str) -> bool:
    meta = load_notice(nid).meta
    return bool(program) and program.replace("SH ", "") in meta.get("program", "") and \
        (issuer is None or meta.get("issuer") == issuer)


def _site(nid: str) -> str:
    """제목 첫 단어(단지·지역 이름) — 공고일·사업이 같은 등록 공고끼리 가를 때 쓴다(예: 서울금천 vs 서울오류)."""
    return load_notice(nid).title.split()[0]


def identify_pages(sha: str, pages: List[str]) -> Identification:
    """텍스트로 식별(지문이 등록 공고와 다를 때). 테스트가 쪽 텍스트를 바꿔 넣을 수 있게 분리했다."""
    if not any(p.strip() for p in pages):
        return Identification(UNREADABLE, sha256=sha, pages=len(pages),
                              reason="글자를 읽을 수 없는 PDF입니다(스캔 이미지일 수 있음). 글자가 선택되는 PDF로 올려 주세요.")
    issuer, program = nc.classify(pages)
    anns = nc.announcement_candidates(pages)
    ann = anns[0]["date"] if anns else None
    ann_date = date.fromisoformat(ann) if ann else None
    windows = [w for w in nc.window_candidates(pages, ann_date) if w["apply"]]
    similar = nc.similar_notices(issuer, program)
    base = dict(sha256=sha, pages=len(pages), issuer=issuer, program=program, announcement=ann,
                windows=windows, similar=similar)

    same = [nid for nid in notice_ids()
            if ann and str(load_notice(nid).announcement_date) == ann and _same_program(issuer, program, nid)]
    if len(same) > 1:
        # 같은 날 같은 사업이 여럿 — 앞 두 쪽에서 단지 이름이 **가장 먼저** 나오는 공고(제목이 맨 앞에 온다).
        # 본문이 다른 단지를 함께 언급하기도 한다(예: 금천 공고 1쪽 "서울오류 행복주택과 중복신청 불가").
        head = "".join(pages[:2])
        found = sorted((head.find(_site(nid)), nid) for nid in same if _site(nid) in head)
        if found and (len(found) == 1 or found[0][0] < found[1][0]):
            same = [found[0][1]]
    if len(same) == 1:
        nid = same[0]
        return Identification(SAME_NOTICE_OTHER_FILE, nid, reason=(
            f"공고일({ann})과 사업 유형이 등록 공고 {nid}({load_notice(nid).title})와 같지만 파일이 다릅니다. "
            "다시 내려받은 같은 공고일 수도, 조건이 바뀐 정정 공고일 수도 있습니다."), **base)
    if len(same) > 1:
        return Identification(UNREGISTERED, reason="공고일·사업 유형이 같은 등록 공고가 여럿이라 어느 공고인지 가리지 못했습니다.",
                              ambiguous=same, **base)
    return Identification(UNREGISTERED, reason="아직 등록되지 않은 공고입니다.", **base)


def identify_pdf(data: bytes) -> Identification:
    sha = hashlib.sha256(data).hexdigest()
    for nid in notice_ids():
        if sv.notice_doc(nid)["source"]["sha256"] == sha:
            n = load_notice(nid)
            return Identification(REGISTERED, nid, reason=f"등록 공고 {nid}({n.title})의 원문과 같은 파일입니다.",
                                  sha256=sha, issuer=n.meta.get("issuer"), program=n.meta.get("program"),
                                  announcement=str(n.announcement_date))
    try:
        pages = sv.extract_pages_bytes(data, label="<업로드>", cache=False)
    except ValueError:
        return Identification(UNREADABLE, sha256=sha, reason="PDF 파일을 열 수 없습니다. 공고문 PDF가 맞는지 확인해 주세요.")
    return identify_pages(sha, pages)


def summary(ident: Identification) -> Dict[str, object]:
    """화면·로그용 요약."""
    return {"status": ident.status, "notice_id": ident.notice_id, "program": ident.program,
            "announcement": ident.announcement, "windows": len(ident.windows)}
