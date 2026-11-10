# -*- coding: utf-8 -*-
"""live_notices.py — 지금 모집 중인 LH·SH 공고 목록(실시간 공고 연결 1단계, docs/12).

공공데이터포털 API 응답 → 공고 한 줄(LiveNotice) → 판정과 잇기(사업 분류·판정 틀·등록 공고).

    rows = parse_lh_list(json)                    # LH 분양임대공고문 조회(15058530)
    w = lh_windows(detail_json)                   # LH 분양임대공고별 상세정보(15057999) — 단지별 청약 접수기간
    rows = parse_applyhome(json)                  # 청약홈 분양정보 조회(15098547) — LH·SH 공고만
    n = link(n)                                   # 사업 유형·판정 틀·등록 공고 N번호·판정 갈래

- 네트워크는 tools/collect_live_notices.py가 맡는다 — 이 모듈은 응답을 읽기만 해서 시험이 네트워크 없이 돈다.
- 공고문 PDF는 내려받지 않는다(LH·SH robots — 상세 API가 첨부 주소를 줘도 1단계는 링크만, 자동 분석은 사용자 결정 뒤).
- 개인정보 없음(공고 정보만).
"""
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from difflib import SequenceMatcher
from typing import Dict, List, Optional

LH_SOURCE, APPLYHOME_SOURCE = "lh", "applyhome"
# LH 상위 유형 코드 — 주택 공고만(01 토지·22 상가 등은 거른다). 05 분양주택은 잔여세대 매각 등
LH_TYPES = {"05": "분양주택", "06": "임대주택", "13": "매입임대", "39": "신혼희망타운"}
# 청약홈 사업주체 — LH·SH 공고만(민간 아파트는 판정 대상이 아니다)
ISSUER_NAMES = (("한국토지주택공사", "LH"), ("서울주택도시공사", "SH"), ("서울주택도시개발공사", "SH"), ("서울특별시 SH공사", "SH"))
# 제목에 사업 이름이 줄어 적힌 경우('남원노암 공공임대 50년 예비입주자모집') — LH 유형 이름으로 사업을 정한다(분류기가 못 정할 때만)
KIND_PROGRAM = {"영구임대": "영구임대주택", "국민임대": "국민임대주택", "공공임대": "공공임대주택", "행복주택": "행복주택"}
# 판정 틀이 있어도 자동 판정하지 않는 공고 — 입주자격 완화(공고 업로드 때도 차단: sheet_extract.RELAXED),
# 기업·기관에 주는 물량(기관공급 — 개인 모집이 아님)
NOT_JUDGED = re.compile(r"자격완화|선계약\s*후\s*검증|기관공급|대상기업|고령자복지형")
# '고령자복지형' 통합공공임대(2026-11-11): 일반형과 자격이 다른 하위 유형 — 일반형 틀로 판정하지 않는다(등록 공고면 그 규칙으로)
TITLE_TAG = re.compile(r"^\s*(?:\[[^\]]{1,12}\]\s*)+")      # '[정정공고]', '[중단공고][수의계약]' 같은 머리표

# 판정 갈래(흥신소 '지금 모집 중' — docs/12 설계 3)
REGISTERED, TEMPLATE, UNSUPPORTED = "registered", "template", "unsupported"


@dataclass(frozen=True)
class LiveNotice:
    source: str                         # lh / applyhome
    external_id: str                    # LH 공고 ID(PAN_ID) / 청약홈 주택관리번호
    title: str
    issuer: Optional[str]               # LH / SH
    kind: str                           # 출처의 유형 이름(영구임대·국민임대·신혼희망타운 …)
    region: str
    announced: Optional[str]            # 공고일 YYYY-MM-DD
    window_start: Optional[str]         # 청약 접수 시작(날짜)
    window_end: Optional[str]           # 청약 접수 마감(날짜)
    status: str                         # 출처의 상태(공고중·접수중·접수마감·정정공고중 …), 청약홈은 날짜로 계산
    url: str                            # 공식 상세 페이지
    detail_key: Dict[str, str] = field(default_factory=dict, compare=False)   # LH 상세 조회 인자
    # link()가 채운다
    program: Optional[str] = None       # 사업 유형(notice_candidates.classify)
    template: Optional[str] = None      # 판정 틀(sheet_extract.choose_template) — 없으면 None
    registered_id: Optional[str] = None  # 같은 공고로 보이는 등록 공고(N번호)
    route: Optional[str] = None         # registered / template / unsupported

    def as_dict(self) -> Dict:
        return asdict(self)


def _d(s: Optional[str]) -> Optional[str]:
    """'2026.11.09' / '20261109' / '2026-11-09' → '2026-11-09'(아니면 None)."""
    if not s:
        return None
    m = re.match(r"^\s*(\d{4})[.\-]?(\d{1,2})[.\-]?(\d{1,2})", s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return None


def _ds(resp, name: str) -> List[Dict]:
    """LH 응답(묶음 목록) 안의 이름 붙은 표."""
    for part in resp if isinstance(resp, list) else []:
        if isinstance(part, dict) and name in part:
            return part[name] or []
    return []


def clean_title(title: str) -> str:
    return TITLE_TAG.sub("", title or "").strip()


def parse_lh_list(resp) -> List[LiveNotice]:
    """LH 분양임대공고문 조회 응답 → 주택 공고만(LH_TYPES)."""
    out = []
    for r in _ds(resp, "dsList"):
        upp = r.get("UPP_AIS_TP_CD", "")
        if upp not in LH_TYPES:
            continue
        out.append(LiveNotice(
            source=LH_SOURCE, external_id=r.get("PAN_ID", ""), title=(r.get("PAN_NM") or "").strip(), issuer="LH",
            kind=r.get("AIS_TP_CD_NM") or LH_TYPES[upp], region=r.get("CNP_CD_NM") or "",
            announced=_d(r.get("PAN_NT_ST_DT")), window_start=None, window_end=_d(r.get("CLSG_DT")),
            status=r.get("PAN_SS") or "", url=r.get("DTL_URL") or "",
            detail_key={k: r.get(k, "") for k in ("PAN_ID", "CCR_CNNT_SYS_DS_CD", "SPL_INF_TP_CD", "UPP_AIS_TP_CD",
                                                    "AIS_TP_CD")}))
    return out


def lh_total(resp) -> int:
    rows = _ds(resp, "dsList")
    try:
        return int(rows[0].get("ALL_CNT", 0)) if rows else 0
    except ValueError:
        return 0


def lh_windows(detail) -> Optional[Dict[str, str]]:
    """LH 상세 응답의 단지별 청약 접수기간(dsSplScdl) → 가장 이른 시작·가장 늦은 마감. 없으면 None(목록의 마감일을 쓴다)."""
    starts, ends = [], []
    for r in _ds(detail, "dsSplScdl"):
        s, e = _d(r.get("SBSC_ACP_ST_DT")), _d(r.get("SBSC_ACP_CLSG_DT"))
        if s:
            starts.append(s)
        if e:
            ends.append(e)
    if not starts and not ends:
        return None
    return {"window_start": min(starts) if starts else None, "window_end": max(ends) if ends else None}


def with_detail(n: LiveNotice, detail) -> LiveNotice:
    w = lh_windows(detail)
    return replace(n, **w) if w else n


def _issuer(owner: str) -> Optional[str]:
    owner = (owner or "").replace(" ", "")
    return next((iss for name, iss in ISSUER_NAMES if name.replace(" ", "") in owner), None)


def _status_by_dates(start: Optional[str], end: Optional[str], today: date) -> str:
    t = today.isoformat()
    if start and t < start:
        return "접수예정"
    if end and t > end:
        return "접수마감"
    return "접수중" if start or end else ""


def parse_applyhome(resp, today: Optional[date] = None) -> List[LiveNotice]:
    """청약홈 분양정보 조회 응답 → LH·SH 공고만. 접수 시작은 특별공급이 있으면 그 시작일."""
    today = today or date.today()
    out = []
    for r in (resp or {}).get("data", []) if isinstance(resp, dict) else []:
        issuer = _issuer(r.get("BSNS_MBY_NM", ""))
        if not issuer:
            continue
        start = _d(r.get("SPSPLY_RCEPT_BGNDE")) or _d(r.get("RCEPT_BGNDE"))
        end = _d(r.get("RCEPT_ENDDE")) or _d(r.get("GNRL_RNK2_ETC_AREA_ENDDE"))
        out.append(LiveNotice(
            source=APPLYHOME_SOURCE, external_id=str(r.get("HOUSE_MANAGE_NO", "")), title=(r.get("HOUSE_NM") or "").strip(),
            issuer=issuer, kind=r.get("HOUSE_SECD_NM") or r.get("HOUSE_DTL_SECD_NM") or "", region=r.get("SUBSCRPT_AREA_CODE_NM") or "",
            announced=_d(r.get("RCRIT_PBLANC_DE")), window_start=start, window_end=end,
            status=_status_by_dates(start, end, today), url=r.get("PBLANC_URL") or r.get("HMPG_ADRES") or ""))
    return out


# ------------------------------------------------------------------ 판정과 잇기
def _norm(s: str) -> str:
    return re.sub(r"[\s\[\]()·.,'\"‘’“”\-_]", "", clean_title(s))


# 제목 비교에서 뺄 말 — 공고 종류 꼬리말과 괄호 속 날짜('26.10.27)
SHORT_DROP = re.compile(r"\(['\d.\s]+\)|최초|추가|입주자|예비|모집|공고문?")


def _parens(s: str) -> frozenset:
    """제목 괄호 속 하위 유형(날짜·회차 제외) — '(일반형)'·'(고령자복지형)'이 다르면 다른 공고."""
    out = set()
    for x in re.findall(r"\(([^()]*)\)", clean_title(s)):
        x = re.sub(r"\s", "", x)
        if x and not re.fullmatch(r"['\d.\-~,]+|본청약|사전청약", x):
            out.add(x)
    return frozenset(out)


def _norm_short(s: str) -> str:
    return _norm(SHORT_DROP.sub("", clean_title(s)))


def _registered_index():
    from rule_data import load_notice, notice_ids
    out = []
    for nid in notice_ids():
        n = load_notice(nid)
        out.append((nid, n.meta.get("issuer"), n.announcement_date.isoformat(), _norm(n.title or ""),
                    _program_key(n.meta.get("program")), _parens(n.title or "")))
    return out


_INDEX = None


def _program_key(program: Optional[str]) -> str:
    """사업 이름 비교용 — 'SH '·'주택'·괄호를 뗀다('행복주택' = 'SH 행복주택', '국민임대주택' = '국민임대')."""
    return re.sub(r"^SH |주택|\(.*?\)|\s", "", program or "")


def registered_match(n: LiveNotice, index=None, program: Optional[str] = None) -> Optional[str]:
    """같은 공고로 보이는 등록 공고 — 발행 기관·공고일·사업이 같고 제목이 비슷(0.7 이상)할 때만. 애매하면 None(새 공고로 둔다).
    같은 날 같은 기관의 다른 사업 공고('SH 2026년 1차 행복주택' / 'SH 2026년 다자녀 매입임대')는 제목 틀이 비슷해 사업으로 가른다."""
    global _INDEX
    if index is None:
        if _INDEX is None:
            _INDEX = _registered_index()
        index = _INDEX
    title = _norm(n.title)
    short = _norm_short(n.title)
    best, best_r = None, 0.0
    want = _program_key(program)
    mine = _parens(n.title)
    for nid, issuer, ann, t, prog, *rest in index:
        if issuer != n.issuer or ann != n.announced or not t or (want and prog and want != prog):
            continue
        theirs = rest[0] if rest else frozenset()
        if mine and theirs and mine != theirs:          # 하위 유형이 다름(평창장평 일반형·고령자복지형)
            continue
        r = max(SequenceMatcher(None, title, t).ratio(), SequenceMatcher(None, short, _norm_short(t)).ratio())
        if r > best_r:
            best, best_r = nid, r
    return best if best_r >= 0.7 else None


def link(n: LiveNotice, index=None) -> LiveNotice:
    """사업 유형·판정 틀·등록 공고·판정 갈래를 채운다(분류는 공고 업로드와 같은 함수)."""
    import sys
    from pathlib import Path
    import notice_candidates as nc
    tools = str(Path(__file__).resolve().parent.parent / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import sheet_extract as X
    import draft
    marker = "i-sh.co.kr" if n.issuer == "SH" else "LH청약플러스"
    _, program = nc.classify([clean_title(n.title) + " " + n.kind, marker])
    if program is None and n.source == LH_SOURCE:
        program = KIND_PROGRAM.get(n.kind)
    if n.source == LH_SOURCE and n.kind.startswith("행복주택"):
        # LH 유형이 행복주택이면 행복주택 — 제목의 '신혼희망타운'으로 분양이 되지 않게(2026-11-11 구리갈매 A-1BL)
        program = "행복주택(신혼희망타운)" if "신혼희망" in n.kind else "행복주택"
    template = X.choose_template(n.issuer, program)
    if template not in draft.PASSING:
        template = None
    if NOT_JUDGED.search(n.title):
        template = None
    reg = registered_match(n, index, program)
    route = REGISTERED if reg else TEMPLATE if template else UNSUPPORTED
    return replace(n, program=program, template=template, registered_id=reg, route=route)


def is_open(n: LiveNotice, today: Optional[date] = None) -> bool:
    """아직 마감하지 않은 공고(마감일이 오늘 이후이거나 모름)."""
    t = (today or date.today()).isoformat()
    return n.status not in ("접수마감", "모집완료", "중단공고") and (n.window_end is None or n.window_end >= t)


# ------------------------------------------------------------------ 같은 공고 묶기(2단계 ①, 2026-11-10)
# 보여 줄 때만 묶는다 — 저장된 행(출처별 원본)은 그대로 둔다.
# ① LH 정정공고: 원 공고는 '정정공고중'으로 남고 '[정정공고]'가 붙은 새 공고가 따로 온다 — 머리표를 뗀 제목이 글자까지 같으면 한 공고.
#    괄호 안이 다르면 다른 공고다(평창장평 '(일반형)'·'(고령자복지형)', 경기남부권 '(무순위, 유주택자 가능)'·'(…무주택세대구성원)').
# ② LH와 청약홈에 같이 올라온 분양 공고: 기관·공고일·마감일이 같고 제목의 단지 부분이 거의 같으면(0.85) 한 공고 — LH 쪽이 대표.
ROUTE_RANK = {REGISTERED: 0, TEMPLATE: 1, UNSUPPORTED: 2}
CORE_DROP = re.compile(r"\((?:본청약|사전청약)\)|잔여세대|추가|입주자|모집|공고문?|[\s\[\]()]")


def _exact(title: str) -> str:
    return re.sub(r"\s", "", clean_title(title))


def _core(title: str) -> str:
    return CORE_DROP.sub("", clean_title(title).replace("[", "(").replace("]", ")"))


def _primary_first_pick(rows: List[Dict]) -> Dict:
    return min(rows, key=lambda r: (r["source"] != LH_SOURCE, r.get("status") == "정정공고중",
                                    "" if r.get("announced") is None else _neg(str(r["announced"]))))


def _neg(s: str) -> str:
    """나중 날짜가 앞에 오게(문자열 날짜 뒤집기)."""
    return "".join(chr(0x10FFFF - ord(c)) for c in s)


def _merge(rows: List[Dict]) -> Dict:
    lead = _primary_first_pick(rows)
    out = dict(lead)
    others = [r for r in rows if r is not lead]
    for k in ("window_start", "window_end", "registered_id", "program", "template"):
        if out.get(k) is None:
            out[k] = next((r[k] for r in others if r.get(k) is not None), None)
    best = min(rows, key=lambda r: ROUTE_RANK.get(r.get("route"), 3))
    out["route"] = best.get("route")
    if best.get("registered_id"):
        out["registered_id"] = best["registered_id"]
    out["related"] = [{"source": r["source"], "external_id": r["external_id"], "title": r["title"], "status": r.get("status"),
                       "url": r.get("url")} for r in others]
    return out


def merge_duplicates(rows: List[Dict]) -> List[Dict]:
    """저장된 공고 행(dict) → 같은 공고를 하나로 묶은 목록. 각 행에 'related'(묶인 다른 행)를 붙인다. 순서는 처음 나온 순서."""
    groups: List[List[Dict]] = []
    exact: Dict[tuple, List[Dict]] = {}
    for r in rows:
        k = (r["source"], r.get("issuer"), _exact(r["title"]))
        if k in exact:
            exact[k].append(r)
        else:
            exact[k] = [r]
            groups.append(exact[k])
    lh_groups = [g for g in groups if g[0]["source"] == LH_SOURCE]
    merged: List[List[Dict]] = []
    for g in groups:
        if g[0]["source"] != APPLYHOME_SOURCE:
            merged.append(g)
            continue
        a = g[0]
        host = next((h for h in lh_groups
                     if any(h_r.get("issuer") == a.get("issuer") and str(h_r.get("announced")) == str(a.get("announced"))
                            and str(h_r.get("window_end")) == str(a.get("window_end"))
                            and SequenceMatcher(None, _core(h_r["title"]), _core(a["title"])).ratio() >= 0.85
                            for h_r in h)), None)
        if host is not None:
            host.extend(g)
        else:
            merged.append(g)
    return [_merge(g) if len(g) > 1 else dict(g[0], related=[]) for g in merged]
