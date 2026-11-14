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

LH_SOURCE, APPLYHOME_SOURCE, SEOUL_SOURCE = "lh", "applyhome", "seoul_housing"
CLOSED_STATUS = ("접수마감", "모집완료", "중단공고", "모집마감")
# LH 상위 유형 코드 — 주택 공고만(01 토지·22 상가 등은 거른다). 05 분양주택은 잔여세대 매각 등
LH_TYPES = {"05": "분양주택", "06": "임대주택", "13": "매입임대", "39": "신혼희망타운"}
# 청약홈 사업주체 — LH·SH 공고만(민간 아파트는 판정 대상이 아니다)
ISSUER_NAMES = (("한국토지주택공사", "LH"), ("서울주택도시공사", "SH"), ("서울주택도시개발공사", "SH"), ("서울특별시 SH공사", "SH"))
# 제목에 사업 이름이 줄어 적힌 경우('남원노암 공공임대 50년 예비입주자모집') — LH 유형 이름으로 사업을 정한다(분류기가 못 정할 때만)
KIND_PROGRAM = {"영구임대": "영구임대주택", "국민임대": "국민임대주택", "공공임대": "공공임대주택", "행복주택": "행복주택"}
# 판정 틀이 있어도 자동 판정하지 않는 공고 — 입주자격 완화(공고 업로드 때도 차단: sheet_extract.RELAXED),
# 기업·기관에 주는 물량(기관공급 — 개인 모집이 아님)
NOT_JUDGED = re.compile(r"자격완화|선계약\s*후\s*검증|기관공급|대상기업|고령자복지형|민간임대|선착순")
# '선착순'(2026-11-14): LH 청년 매입임대 선착순 예비입주자 모집 — 남은 물량을 순서대로 주며 자격이 완화될 수 있어 원문을 보기 전에는
# 일반 모집 틀로 판정하지 않는다(공고문이 분석되면 그 결과로 — 입주자격 완화는 sheet_extract.RELAXED가 잡는다)
# '민간임대'(2026-11-14): 민간임대 청년안심주택(역세권 청년주택)은 사업자마다 모집 — 공공임대 청년안심주택 틀로 판정하지 않는다
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


def lh_pdf_url(detail) -> Optional[str]:
    """LH 상세 응답의 공고문 PDF 주소(dsAhflInfo — '공고문(PDF)'). 2026-11-14 사용자 결정으로 수집 작업이 이 주소의 공고문을
    내려받아 자동 분석한다(robots가 /lhapply/lhFile.do를 막지만 공식 API가 주는 주소 — 비영리·공익 목적, 사용자 판단)."""
    for r in _ds(detail, "dsAhflInfo"):
        url, kind = (r.get("AHFL_URL") or "").strip(), (r.get("SL_PAN_AHFL_DS_CD_NM") or "")
        if url.startswith("http") and "PDF" in kind.upper() and "공고" in kind:
            return url
    return None


def with_detail(n: LiveNotice, detail) -> LiveNotice:
    w = lh_windows(detail) or {}
    pdf = lh_pdf_url(detail)
    if pdf:
        w["detail_key"] = dict(n.detail_key, pdf=pdf)
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
        # 꼬리말('국민임대주택 예비입주자 모집 공고')을 뗀 단지·사업 부분으로만 — 전체 제목은 꼬리말이 같아 다른 단지도 비슷하게 나온다
        # (2026-11-13: 화성동탄 ↔ 인천논현 국민임대가 0.7을 넘음)
        r = SequenceMatcher(None, short, _norm_short(t)).ratio()
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
    if program is None or program in SH_GENERIC:      # 제목에 띄어쓰기·'ㆍ'가 있어 분류표(띄어쓰기 없는 원문용)가 못 잡는 사업 이름
        program = sh_title_program(n.title, n.kind) or program        # (2026-11-14: LH '청년 매입임대주택' 등이 판정 안 함이던 결함)
        if n.issuer != "SH" and program and program.startswith("SH "):
            program = program[3:]
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
    return n.status not in CLOSED_STATUS and (n.window_end is None or n.window_end >= t)


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


SOURCE_RANK = {LH_SOURCE: 0, SEOUL_SOURCE: 1, APPLYHOME_SOURCE: 2}


def _primary_first_pick(rows: List[Dict]) -> Dict:
    return min(rows, key=lambda r: (SOURCE_RANK.get(r["source"], 3), r.get("status") == "정정공고중",
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
    # 주택포털이 대표면 접수기간은 청약홈 값(특별·순위별 접수일이 구조화돼 있다)
    ah = next((r for r in rows if r["source"] == APPLYHOME_SOURCE and r.get("window_start")), None)
    if ah is not None and lead["source"] == SEOUL_SOURCE:
        out["window_start"], out["window_end"] = ah["window_start"], ah["window_end"]
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
    # 주택포털과 청약홈의 같은 SH 분양 공고 — 주택관리번호로 묶는다
    by_house = {str((r.get("detail_key") or {}).get("house_no")): g for g in groups for r in g
                if r["source"] == SEOUL_SOURCE and (r.get("detail_key") or {}).get("house_no")}
    merged: List[List[Dict]] = []
    for g in groups:
        if g[0]["source"] != APPLYHOME_SOURCE:
            merged.append(g)
            continue
        a = g[0]
        if str(a["external_id"]) in by_house:
            by_house[str(a["external_id"])].extend(g)
            continue
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


# ------------------------------------------------------------------ SH — 서울시 주택포털(2단계 ②-5, 2026-11-12)
# SH는 공식 API가 없고 i-sh.co.kr robots가 게시판·첨부를 막는다. 서울시 주택포털(housing.seoul.go.kr, robots Allow: /, 서울시 저작권 정책 —
# 공공누리)의 SH 공공임대·공공분양 목록과 상세 요약을 읽는다(공고명·날짜·상태 같은 사실 정보만, 원문 링크로 보냄). 해외 IP(GitHub 서버)에서
# 접속되는 것을 확인했다(2026-11-12). 마이홈포털 웹은 해외 IP를 막아 쓰지 않는다.
SEOUL_BASE = "https://housing.seoul.go.kr"
SEOUL_LISTS = (("임대", "/site/main/sh/publicLease/list?cp={}"), ("분양", "/site/main/sh/publicSale/01/list?cp={}"))
SEOUL_HEAD = ("번호", "청약유형", "공고명", "공고게시일", "발표일")
# 목록에 섞인 모집공고 아닌 글(당첨자·서류심사 발표, 일정 연기, 주택정보 추가, 예비자 순번 안내)
SEOUL_NOT_NOTICE = re.compile(r"당첨자|발표|결과|연기|취소|주택정보|명단|합격|선정자|경쟁률|예비\s*\d\s*차|안내\s*$")
# 분류기가 제목만으로는 뭉뚱그려 답하는 사업 이름 — 제목의 사업 이름으로 다시 정한다(판정 틀과 같은 이름)
SH_GENERIC = {"매입임대주택", "분양주택", "도시형생활주택", "공공임대주택"}
SH_TITLE_PROGRAM = (
    # 'Ⅱ'가 사업 이름 앞(신생아Ⅱ 매입임대·신생아 II (전세형) — LH 제목)이나 뒤(매입임대주택Ⅱ — SH 제목)에 온다. '신혼부부Ⅰ/Ⅱ'(옛 이름)와
    # '매입임대' 없이 '신혼·신생아Ⅱ(전세형) 예비입주자 모집'만 적은 LH 제목도 있다 — 이 이름은 매입임대 공고(제목·유형에 '매입임대')에서만 쓴다.
    # LH 공고면 link가 'SH '를 뗀다
    (re.compile(r"신혼\s*(?:[·ㆍ.]?\s*신생아|부부)\s*(?:Ⅱ|II)(?!I)|신혼\s*[·ㆍ.]?\s*신생아\s*매입임대\s*(?:주택)?\s*(?:Ⅱ|2|II)"
                r"|미리내집\s*\(\s*신혼"), "SH 신혼·신생아 매입임대Ⅱ"),
    (re.compile(r"신혼\s*(?:[·ㆍ.]?\s*신생아|부부)\s*(?:Ⅰ|I)(?!I)|신혼\s*[·ㆍ.]?\s*신생아\s*(?:Ⅰ|I)?\s*매입임대"), "SH 신혼·신생아 매입임대Ⅰ"),
    (re.compile(r"다자녀\s*매입임대"), "다자녀 매입임대"),
    (re.compile(r"청년\s*매입임대"), "청년매입임대"),        # SH 청년 매입임대(2026-11-14 판정 틀) — 자립준비청년·기숙사형·위국헌신은 아래에서 뺀다
    (re.compile(r"토지임대부\s*분양"), "토지임대부 분양주택"),
    (re.compile(r"국민임대"), "국민임대주택"),
    (re.compile(r"영구임대"), "영구임대주택"),
)


class SeoulFormatError(ValueError):
    """주택포털 화면 구조가 바뀜 — 수집기가 실패로 알린다(조용히 0건이 되지 않게)."""


def sh_title_program(title: str, kind: str = "") -> Optional[str]:
    """제목의 사업 이름(SH·LH 공통 — 2026-11-14부터 LH 매입임대 제목에도). 판정 틀 없는 변형 사업이면 None."""
    t = clean_title(title)
    if re.search(r"자립준비청년|기숙사형|위국헌신|공공한옥|이공계", t):   # 판정 틀 없는 변형 사업
        return None
    rental = "매입임대" in t + kind
    return next((p for rx, p in SH_TITLE_PROGRAM if rx.search(t) and (rental or "신혼·신생아" not in p)), None)


def _html_text(s: str) -> str:
    import html as _h
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", s, flags=re.S)
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def parse_seoul_list(page_html: str, kind: str) -> List[Dict]:
    """주택포털 SH 목록 한 쪽 → 행(청약유형·공고명·게시일·발표일·모집상태·상세 경로). 머리글이 다르면 SeoulFormatError."""
    import html as _h
    t = re.sub(r"<script.*?</script>|<style.*?</style>", "", page_html, flags=re.S)
    trs = re.findall(r"<tr.*?</tr>", t, flags=re.S)
    if not trs:
        raise SeoulFormatError("목록 표가 없습니다")
    head = [_html_text(x) for x in re.findall(r"<th.*?</th>", trs[0], flags=re.S)]
    if tuple(head[:5]) != SEOUL_HEAD:
        raise SeoulFormatError(f"목록 머리글이 바뀌었습니다: {head[:7]}")
    out = []
    for r in trs[1:]:
        c = [_html_text(x) for x in re.findall(r"<td.*?</td>", r, flags=re.S)]
        link = re.findall(r'href="([^"]+)"', r)
        if len(c) < 6 or not link:
            continue
        out.append({"type": c[1], "title": re.sub(r"^-->\s*", "", c[2]).strip(), "posted": _d(c[3]), "winners": _d(c[4]),
                    "status": c[5] if kind == "임대" else "", "view": _h.unescape(link[0]), "kind": kind})
    return out


def seoul_text(view_html: str) -> str:
    """상세 화면 → 요약 본문(제목·공고일·유형 … 상세 정보)."""
    x = _html_text(view_html)
    i, j = x.find("제목"), x.find("목록 #content_wrap")
    return x[i if i >= 0 else 0: j if j > 0 else None]


_APPLY = re.compile(r"접수|신청|청약\s*일정")
_NOT_APPLY = re.compile(r"서류|당첨|발표|계약|입주|열람|추첨|결과|제출|공개|동호|소명|선정|자격심사|방법|문의|사전청약|포기")
_D = r"(?:(20\d{2})\s*[.\-년]\s*)?(\d{1,2})\s*[.\-월]\s*(\d{1,2})\s*\.?\s*일?"
_RANGE = re.compile(_D + r"\s*(?:\([^)]{1,4}\))?\s*(?:\d{1,2}\s*[:시]\s*\d{0,2}\s*분?)?\s*[~∼～\-]\s*(?:" + _D + r"|(\d{1,2}\s*[:시]))")


def _mk(y, m, d, year: int) -> Optional[date]:
    try:
        return date(int(y or year), int(m), int(d))
    except (TypeError, ValueError):
        return None


def seoul_window(body: str, posted: Optional[str], winners: Optional[str] = None) -> Optional[Dict[str, str]]:
    """요약 본문의 청약 접수기간 — ■·□ 항목과 ○ 줄 중 '접수·신청' 문맥의 날짜 범위만(서류·당첨·계약·사전청약 당첨자 줄은 뺀다).
    가장 이른 시작 ~ 가장 늦은 마감. 공고일 30일 전보다 이르거나 당첨자 발표보다 늦거나 180일 넘게 걸치면 버린다(None).
    2026-11-12 주택포털 SH 공고 86건 표본으로 맞췄다(tests/test_live_seoul.py)."""
    if not posted:
        return None
    pd = date.fromisoformat(posted)
    wd = date.fromisoformat(_d(winners)) if _d(winners) else None      # 발표일 '-'(미정)
    year = pd.year
    early = date.fromordinal(pd.toordinal() - 30)
    starts, ends = [], []
    in_apply = False
    for t in re.split(r"(?=[■□○◦▶●])", body):
        t = t.strip()
        if not t:
            continue
        head = re.split(r"\s-\s", t, maxsplit=1)[0]          # 머리말만(같은 줄의 '- 사전청약 당첨자: …' 하위 줄은 아래에서 따로)
        lab = re.split(r"[:：]", head, maxsplit=1)[0][:30] if re.search(r"[:：]", head[:32]) else head[:24]
        lab_ok = bool(_APPLY.search(lab)) and not _NOT_APPLY.search(
            re.sub(r"(및\s*)?신청\s*방법", "", lab).replace("신청접수", "접수"))
        if t[0] in "■□":
            in_apply = lab_ok
        elif _NOT_APPLY.search(lab) and not lab_ok:
            continue
        if not (lab_ok or in_apply):
            continue
        for line in re.split(r"(?=\s-\s)", t):          # '- 사전청약 당첨자: …' 같은 하위 줄
            if re.search(r"사전청약|서류|당첨자\s*발표|포기", line[:30]):
                continue
            for m in _RANGE.finditer(line):
                y1, m1, d1, y2, m2, d2, _hh = m.groups()
                a = _mk(y1, m1, d1, year)
                if a and not y1 and a < early:                       # 12월 공고 → 1월 접수(해를 넘김)
                    a = _mk(year + 1, m1, d1, year)
                b = _mk(y2 or (a.year if a else year), m2, d2, year) if m2 else a
                if a and b and b < a and not y2:
                    b = _mk(a.year + 1, m2, d2, year)
                if a and b and 0 <= (b - a).days <= 120:
                    starts.append(a)
                    ends.append(b)
    if not starts:
        return None
    s, e = min(starts), max(ends)
    if s < early or (wd and e > wd) or (e - s).days > 180:
        return None
    return {"window_start": s.isoformat(), "window_end": e.isoformat()}


def seoul_house_no(body: str) -> Optional[str]:
    """요약 본문의 주택관리번호(청약홈과 같은 번호 — 분양 공고는 청약홈 행과 정확히 묶는다)."""
    m = re.search(r"주택관리번호\s*[:：]?\s*(\d{4})\s*-?\s*(\d{6})", body)
    return m.group(1) + m.group(2) if m else None


def seoul_announced(body: str) -> Optional[str]:
    m = re.search(r"모집\s*공고일\s*[:：]?\s*(20\d{2})\s*[.\-]\s*(\d{1,2})\s*[.\-]\s*(\d{1,2})", body)
    d = _mk(*m.groups(), 0) if m else None
    return d.isoformat() if d else None


def seoul_external_id(row: Dict) -> str:
    """주택포털 상세 주소의 seq는 목록 순서라 바뀐다 — 공고명·게시일로 고정 ID를 만든다."""
    import hashlib
    return hashlib.sha1(f"{row['title']}|{row['posted']}".encode("utf-8")).hexdigest()[:16]


def seoul_notice(row: Dict) -> Optional[LiveNotice]:
    """목록 행 → LiveNotice(접수기간은 상세를 읽은 뒤 with_seoul_detail). 모집공고 아닌 글은 None."""
    if SEOUL_NOT_NOTICE.search(row["title"]):
        return None
    return LiveNotice(source=SEOUL_SOURCE, external_id=seoul_external_id(row), title=row["title"], issuer="SH",
                      kind=row["type"], region="서울특별시", announced=row["posted"], window_start=None, window_end=None,
                      status=row["status"], url=SEOUL_BASE + row["view"],
                      detail_key={"view": row["view"], "winners": row.get("winners") or ""})


def with_seoul_detail(n: LiveNotice, view_html: str) -> LiveNotice:
    """상세 요약 → 모집공고일·접수기간·주택관리번호. 접수기간을 못 읽으면 비워 둔다(화면은 '접수 일정은 공고문 확인')."""
    body = seoul_text(view_html)
    ann = seoul_announced(body) or n.announced
    w = seoul_window(body, ann, n.detail_key.get("winners") or None) or {}
    key = dict(n.detail_key)
    hn = seoul_house_no(body)
    if hn:
        key["house_no"] = hn
    return replace(n, announced=ann, detail_key=key, **w)


# ------------------------------------------------------------------ 마이홈 보조 정보(묶음 C, 2026-11-14)
# 국토교통부 마이홈포털 공공주택 모집공고 조회(15108420, apis.data.go.kr/1613000/HWSPR02) — LH·지방공사 공고(SH 없음, 2026-11-13 확인).
# 공식 링크(url)의 panId가 LH 공고 ID(PAN_ID)와 같아 정확히 잇는다. 카드 보조 정보(단지 주소·임대보증금·월임대료·공급 세대수)와
# LH 접수기간 보충·교차 확인에 쓴다. 판정에는 쓰지 않는다.
MYHOME_RENT = "https://apis.data.go.kr/1613000/HWSPR02/rsdtRcritNtcList"
MYHOME_SALE = "https://apis.data.go.kr/1613000/HWSPR02/ltRsdtRcritNtcList"


def parse_myhome(resp) -> List[Dict]:
    body = ((resp or {}).get("response") or {}).get("body") or {}
    items = body.get("item") or []
    return items if isinstance(items, list) else [items]


def myhome_total(resp) -> int:
    try:
        return int((((resp or {}).get("response") or {}).get("body") or {}).get("totalCount") or 0)
    except ValueError:
        return 0


def _pan_id(item: Dict) -> Optional[str]:
    m = re.search(r"panId=(\d+)", item.get("url") or "")
    return m.group(1) if m else None


def _address(a: Optional[str]) -> str:
    a = re.sub(r"\s+", " ", a or "").strip()
    half = len(a) // 2
    if a and len(a) % 2 == 1 and a[:half] == a[half + 1:]:      # 같은 주소가 두 번 이어 붙은 응답
        return a[:half]
    return a


def _money_range(values) -> Optional[List[int]]:
    v = sorted({int(x) for x in values if isinstance(x, (int, float)) and x > 0})
    return [v[0], v[-1]] if v else None


def myhome_info(items: List[Dict]) -> Dict[str, Dict]:
    """마이홈 공고 항목(단지별 여러 줄) → LH 공고 ID별 보조 정보."""
    by: Dict[str, List[Dict]] = {}
    for it in items:
        pid = _pan_id(it)
        if pid:
            by.setdefault(pid, []).append(it)
    out = {}
    for pid, rows in by.items():
        addrs = list(dict.fromkeys(_address(r.get("fullAdres")) for r in rows if r.get("fullAdres")))
        complexes = list(dict.fromkeys((r.get("hsmpNm") or "").strip() for r in rows if r.get("hsmpNm")))
        supply = sum(int(r.get("sumSuplyCo") or 0) for r in rows if str(r.get("sumSuplyCo") or "").isdigit()
                     or isinstance(r.get("sumSuplyCo"), int))
        begins = sorted(d for d in (_d(r.get("beginDe")) for r in rows) if d)
        ends = sorted(d for d in (_d(r.get("endDe")) for r in rows) if d)
        out[pid] = {"address": addrs[0] if addrs else None, "addresses": len(addrs), "complexes": complexes[:5],
                    "deposit": _money_range(r.get("rentGtn") for r in rows),
                    "rent": _money_range(r.get("mtRntchrg") for r in rows), "supply": supply or None,
                    "window": [begins[0], ends[-1]] if begins and ends else None,
                    "type": rows[0].get("suplyTyNm"), "myhome_url": rows[0].get("pcUrl")}
    return out


def with_myhome(n: LiveNotice, info: Optional[Dict]) -> LiveNotice:
    """LH 접수기간을 못 얻은 공고(상세 조회 실패 등)는 마이홈 접수기간으로 채운다."""
    if not info or not info.get("window") or n.window_start:
        return n
    return replace(n, window_start=info["window"][0], window_end=n.window_end or info["window"][1])
