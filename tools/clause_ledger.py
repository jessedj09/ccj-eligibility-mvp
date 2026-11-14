# -*- coding: utf-8 -*-
"""조항 장부(자동 판정 v3 ②, docs/10 §2-4) — 공고문의 '조건처럼 보이는 문장'을 하나도 빠짐없이 분류해, 규칙이 모르는 새 조건을 찾는다.

    python tools/clause_ledger.py N12                     # 등록 공고 1건(형제 = 같은 사업의 다른 등록 공고)
    python tools/clause_ledger.py --all                   # 등록 공고 전부 요약
    python tools/clause_ledger.py --all --out docs/clause-ledger-review.md   # 미분류 문장 검토 목록

분류(위에서부터 먼저 맞는 것):
  근거            규칙 조건의 인용문이거나 조건 식의 값(유형 이름 등)을 담은 문장
  근거(하위 항목)  근거 문장 바로 아래의 목록 항목(①·1)·가.·- …)
  형제 공고에도   같은 사업의 다른 등록 공고에도 있는 문장 — 그 공고를 등록한 사람이 조건이 아니라고 본 것
  무관:<범주>     공통 제한(외국인·중복 신청 등, 판정 범위 밖 — 안내)·정의·서류·절차·계약·임대·선정·순위·안내
  **미분류**      위 어디에도 없음 → 규칙이 모르는 새 조건일 수 있다
'신청할 수 없'·'~에 한하여 신청'·'거주자만'·'이상인 자' 같은 강한 제한 표현이 있으면 서류·절차 등 무관 범주로 넘기지 않는다
(공통 제한·근거·형제 공고 확인은 그대로).
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]

import llm_slot as L  # noqa: E402
import source_verify as sv  # noqa: E402

CACHE = ROOT / ".cache" / "ledger_units_v4"     # v2(2026-11-03): 쪽 번호 줄 건너뜀, v4(2026-11-09): 추출기 pypdfium2·줄 안 목록 기호

MARK = re.compile(r"^\s*([•■①-⑳*※○□▶◆◇·ㆍ\-–]|\d+[.)]|[가-하][.)]|\(\d+\)|\d+순위)")
# '~인 자·~한 자'는 띄어쓰기를 지운 원문에서 '출생한자녀'·'있는자녀'와 겹친다 — 뒤에 '녀'가 오면 조건 표현이 아니다(G1 2026-11-01)
CONDLIKE = re.compile(r"((?:인|한|된|는)자(?!녀)|인사람|한사람|는사람|일것|이어야|여야|신청불가|신청할수없|신청이불가|신청제한|제외|"
                      r"에한하여|에한함|만신청|만해당|거주하는자|거주자에|소유하지않|무주택세대구성원|무주택자)")
STRONG = re.compile(r"(만신청|에한하여신청|신청할수없|신청불가|신청이불가|신청제한|거주하는자|거주자만|이상거주|이내인자|이하인자|"
                    r"이상인자|미만인자|소유하지않은자|해당하지않는자)")
COMMON = re.compile(r"(외국인|재외국민|중복신청|중복당첨|중복으로|말소|거주불명|행방불명|가출|무효처리|부정당첨|불법전대|"
                    r"1세대1주택|1주택만|1주택형만|1주택단지만|1개주택단지만|타[가-힣]{0,8}공고|다른공고|동일유형|동일한유형|"
                    # 사전청약 당첨자(그 세대)의 신청 제한·부적격 — 공통 결격사유처럼 안내만 한다(PRD 4.2, 2026-11-09 N56·N57)
                    r"사전청약당첨자|당첨되더라도부적격|"
                    # 분양 공고의 공통 청약 제한(2026-11-10 보류 줄이기 3차 — N49~N64): 사전청약 통장으로 다른 주택 당첨, 1인 1건,
                    # 기관추천 특별공급과 일반공급 중복, 특별공급 간 중복, 부적격 당첨 제한 기간, 종전 통장 전환 시점
                    r"사전청약시사용한입주자저축|1인1건만신청|기관추천특별공급대상자|특별공급간중복청약|"
                    r"부적격당첨후입주자로선정될수없는기간|종전통장)")
DEFINITION = re.compile(r"(이란|란,|말함|말한다|의미|산정|산출|가액은|공시지가|평가하|기준으로하며|기준으로합니다|포함됩니다|포함한다|포함함|"
                        r"재산|정자료|감가상각|경과년수|소득자료|"
                        # 세대구성원 범위(검증 대상에 포함·생계와 주거를 달리하는 사람 제외)·차량가액 산정(청년안심주택, 2026-11-14)
                        r"생계및주거를달리한다고|자격검증대상\(세대구성원\)|차량기준가액|높은차량가액을기준)")
# 주택을 소유하지 않은 것으로 보는 경우(주택공급에 관한 규칙 제53조 — 선착순 분양권, 비도시지역 주택, 경매·공매로 산 임차주택 등).
# 무주택으로 인정해 주는 예외라 신청을 막지 않는다 — 정의로 본다(2026-11-09 N22·N51·N56·N57)
OWNERSHIP_EXCEPTION = re.compile(r"(소유하지아니한것으로인정|소유하지않은것으로인정|선착순의방법으로공급받아|"
                                 r"도시지역이아닌지역또는면의행정구역|경매또는공매로매수|"
                                 # 소형 주택·60세 이상 직계존속 소유·생애최초 취득 임차주택(분양 공고, 2026-11-10)
                                 r"20m2이하의주택|20㎡이하의주택|60세이상의직계존속|생애최초로취득한경우로한정|"
                                 r"임차인으로서거주하던임차주택)")
# 공급 주택 목록 표(부록) — 머리글에 '…이내인 자'가 붙어도 주택 목록일 뿐(N20 p.58) — 강한 표현이 있어도 안내
HOUSE_LIST = re.compile(r"주택목록|공급주택현황|연번자치구주택형|주택명주소")
RANK = re.compile(r"\d순위")
# 모든 공고에 붙는 일반 안내(자격 요건 전반·개인정보) — 강한 제한 표현이 들어 있어도 새 조건이 아니다
BOILERPLATE = re.compile(r"(관계법령등에서정한|입주자격을유지|민감정보|본인정보제공|개인정보수집|"
                         # 공고 첫머리의 공급 계층 소개("…은 공고일 현재 다음 중 하나에 해당하는 사람에게 공급") — 계층마다 조건이 따로 있다
                         r"다음중하나(?:의계층)?에해당하는(?:사람|자)에게공급|"
                         # 신청 절차의 '신청 불가'(서류 미비·시스템 장애·변경 마감·특례 선택·옵션·본청약 포기) — 자격이 아니다(2026-11-10)
                         r"신청서류중1건이라도미비|구비서류중1건이라도미비|서비스다운등으로인해신청이불가|신청내용을변경|"
                         r"특례사용여부|마이너스옵션선택시|본청약신청포기|"
                         # 청년안심주택(2026-11-14): 공유형 2인 1팀 신청 방식, 접수 기간 중 주말 접수 불가, 소득 구간별 임대조건·거주기간 표
                         r"2인1팀형태로(?:만)?신청|\(토\)[\d:.~()가-힣]{0,30}청약신청이불가|거주가능임대조건시중시세)")
# 지역별 물량 배분(분양 — 해당 지역·도·기타 지역 몇 %, 미달 물량 넘기기)과 장기복무군인 지역 예외는 같은 순위 안의 **선정 순서**다.
# 신청 자격은 규칙의 거주 조건(수도권 등)이 따로 판정한다. 같은 문장에 '만 신청·신청할 수 없·신청 불가'가 있으면 자격 제한일 수 있어
# 이 분류를 쓰지 않는다(2026-11-09 보류 원인 분석 — 분양 공고 보류의 대부분이 이 문장들이었다).
ALLOCATION = re.compile(r"(미달된물량|남은물량은|물량을배정|%배정|우선공급비율|지역우선공급기준|우선공급에서낙첨|낙첨될경우|"
                        r"\d{2}%\.(?:사전청약|입주자모집)?공고일현재|장기복무군인|"
                        # 해당 지역 거주자 우선(분양 — '○○시 1년 이상 거주하는 신청자가 … 보다 우선')·지역우선공급 대상 인정 여부(2026-11-10)
                        r"거주하는신청자가.{0,80}?보다우선|입주자선정대상에서제외될수있|지역우선공급대상자로(?:는)?(?:불인정|인정))")
ALLOCATION_GUARD = re.compile(r"(만신청|신청할수없|신청불가|신청이불가)")
# 주택형마다 배정 물량이 있는 유형에만 신청(접수 화면 안내) — '만 신청'이 들어 있지만 자격이 아니다
TYPE_QUOTA = re.compile(r"배정물량이있는(?:유형|주택형)|"
                        r"^※?[A-Z](?:,[A-Z])*는신혼부부(?:I|II|Ⅰ|Ⅱ)유형에한함")     # 주택형마다 신청할 수 있는 유형(청년안심주택 p.14)
# '■우선공급대상자' 절 — 일반공급 요건을 갖춘 사람 중 지역·배점으로 먼저 뽑는 몫. 판정은 일반공급 자격 기준이라 그 절의 지역요건 등은
# 새 자격 조건이 아니다(B단계 2026-11-01: 새 공고의 '과천시에 거주하는 자'가 미분류로 남아 지원 가능을 모두 보류로 낮췄다).
PRIORITY_HEAD = re.compile(r"^■[^■]{0,6}우선공급|^■당첨자선정방법\[우선공급")   # 분양 '■당첨자선정방법[우선공급대상자]'(N57)
# 이미 규칙에 있는 소득·자산 기준표를 가리키는 문장('"<표3>총자산보유기준"이하인 자', N49·N56) — 그 공고 규칙에 소득·자산 조건이 있으면 근거로 본다
TABLE_REF = re.compile(r'<표\d+>[^"<]{0,40}?(소득|자산)[^"<]{0,20}?기준"?(?:을|의)?(?:\d+%)?(?:충족|이하)')
# '1인 가구는 생애최초 특별공급 신청 불가' — 생애최초 규칙의 가족 요건(혼인 중이거나 미혼 자녀)이 이미 막는다(N49 p.22·N63 p.26)
SINGLE_FIRST = re.compile(r"1인가구(?:의경우|는)?생애최초특별공급청약?신청이?불가")
# 접수 방법의 '현장 방문 신청 불가'는 강한 표현이지만 자격이 아니라 절차(N28 p.13) — 이 표현만 빼고 강한 제한을 본다
VISIT_ONLY = re.compile(r"(?:현장방문|방문|현장)(?:신청|접수)(?:불가|할수없)|(?:전환|변경)?신청후1년이내재신청불가")
ENUM = re.compile(r"^([①-⑳]|\d+\)|\d(?=[「가-힣])|[가-하][.)]|\(\d+\)|-)")
UNRELATED = {
    "서류": r"(서류|제출|발급|신분증|구비하여야|증명서|등본|초본|확인서|사본|증빙|동의서|원본|개인정보|마이데이터|주민등록번호|등록번호|서명|날인)",
    "절차": r"(인터넷|방문접수|신청서|접수|청약센터|로그인|공동인증|홈페이지|모바일|앱|신청방법|신청기간|삭제|입력하여야|"
            r"주택형\(타입\)별로)",
    "계약·임대": r"(계약|잔금|입주지정|임대기간|재계약|임대료|보증금|월임대|전환|관리비|퇴거|명도|갱신|임대조건|입주청소|키불출)",
    "선정·순위": r"(감점|가점|배점|순번|추첨|선정방법|동점|예비입주자|예비자|당첨|순위별|배정|선정순서)",
    "안내": r"(주택관리번호|www|문의|콜센터|유의|참조|참고|바랍니다|안내|열람|게시|점심시간|공개시간|사전공개|시설물|승강기|"
            r"사다리차|일조권|조망권|철거|하자|혜택|관계법령|에어컨|실외기|소음|주택목록|공급주택|시세의|우선협상대상자|민간참여사업)",
    # 단지 시설·설계 안내(B단계 2026-11-01 — 건설형 공고 뒤쪽의 주차장·마감재·조명 문장이 '제외'·'불가'로 조건처럼 보였다)
    "시설·단지": r"(주차장|주차대수|마감재|마감은|석재|도장|조명|스피커|발코니|천장|벽부형|미술작품|어린이집|관리사무소|"
                 r"편의시설|부대복리시설|주민공동시설|커뮤니티|성능등급|교통편|지하철|경전철|GTX|단지내|단지계획|주동|세대내|"
                 r"설치되며|설치됩니다|설치하여|인테리어|시설의위치|시설면적|자재|팸플릿|홍보물|"
                 # 분양 공고 뒤쪽의 가전·마감·학교 배정·등기 안내(2026-11-03 — '후드는자동'의 '는자'가 조건 표현으로 잡혔다).
                 # '학교'·'등기'처럼 짧은 말은 자격 문장(대학교 재학·등기부)과 겹쳐 쓰지 않고 원문 표현 그대로만
                 r"레인지후드|IoT|스마트홈|통학구역|교육지원청|개교예정|다용도실|건식벽체|물튀김|방화대로|비상차량|"
                 r"전기자동차주차|충전용전원|근린생활시설\(상가\)의대지|소유권보존등기|대지권등기|마이너스옵션|자동소화장치|"
                 r"완강기|바닥난방|자원회수시설|소각시설|음식물자원화)",
    # 당첨·입주 뒤의 의무(분양 — 거주의무·우선매입·융자 대환). 신청 자격이 아니다(2026-11-03, N45 p.2·3·7)
    "입주 후 의무": r"(거주의무자|거주의무개시|거주의무가부여|거주의무미준수|거주의무대상자|수익공유형모기지|대환)",
}
UNRELATED = {k: re.compile(v) for k, v in UNRELATED.items()}
UNCLASSIFIED = "미분류"


# 쪽 번호 줄. 쪽 경계에서 앞 문장과 잇지는 않는다 — 머리글(www…|25 제50차…)이 조건 문장에 붙어 '안내'로 가릴 수 있다(N26 p.24)
PAGE_NO = re.compile(r"^\s*[-–]\s*\d{1,3}\s*[-–]\s*$")
# 한 줄 안의 목록 기호 — 문장 끝('…다.'·'…함'·닫는 괄호) 바로 뒤에 오는 •·※·■ 등에서도 새 단위를 연다. pypdf는 이 자리를 줄로
# 나눴는데 pypdfium2(2026-11-09)는 한 줄로 읽는 곳이 있다(N37 p.4 "…평지붕입니다.※청약신청은…") — 새 공고와 형제 공고가 같은
# 함수로 나누므로 더 잘게 나누면 문장이 서로 맞는다.
# 문장 끝 뒤의 '·'도 목록 기호(N42 p.9 "…신청할수없습니다.·청약제한사항확인방법"). '■'(절 머리)는 줄 어디서든 새 단위(N39 p.5 "…거주자에게공급■일반공급대상자간경쟁시…"), 닫는 괄호 뒤의 •·※도(N36 p.7 "…참고)•신청").
INLINE_MARK = re.compile(r"(?<=[다함음됨임]\.)\s*(?=[•■※○□▪◆◇▶·ㆍ])|(?<=[다함음됨])\s+(?=[•■※○□▪◆◇▶])|(?<=\S)\s*(?=■)"
                         r"|(?<=\))\s*(?=[•※])")


def _units_from_raw(raw: Sequence[str]) -> List[Tuple[int, str]]:
    """쪽 텍스트(띄어쓰기·줄바꿈 유지) → 문장 단위(목록 기호로 시작하는 줄에서 새 단위, 나머지 줄은 이어 붙임) → (쪽, 정규화 문장)."""
    out = []
    for page, text in enumerate(raw, 1):
        cur = None
        for line in (seg for ln in text.splitlines() for seg in INLINE_MARK.split(ln)):
            if not line.strip() or PAGE_NO.match(line):      # 쪽 번호('- 7 -')는 목록 기호 '-'로 보여 새 단위를 열었다
                continue
            if cur is None or MARK.match(line):
                if cur:
                    out.append(cur)
                cur = [page, line]
            else:
                cur[1] += " " + line
        if cur:
            out.append(cur)
    return [(p, sv.normalize(x)) for p, x in out if len(sv.normalize(x)) >= 10]


def units_of_pdf(pdf: Path) -> List[Tuple[int, str]]:
    """원문 PDF의 문장 단위(원문 지문으로 캐시 — 형제 공고는 여러 번 쓰인다)."""
    pdf = Path(pdf)
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    cache = CACHE / f"{sha}.json"
    if cache.exists():
        return [tuple(u) for u in json.loads(cache.read_text(encoding="utf-8"))]
    units = _units_from_raw(L.raw_pages(pdf))
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(units, ensure_ascii=False), encoding="utf-8")
    return units


@lru_cache(maxsize=None)
def registered_units(nid: str) -> Tuple[Tuple[int, str], ...]:
    return tuple(units_of_pdf(sv.pdf_path(nid)))


def evidence_of(doc: Dict) -> Tuple[List[str], List[str]]:
    """규칙 문서 → (인용문들, 조건 식의 문자열 값들) — 정규화. 값에서 지명은 뺀다 — '서울특별시 거주'(규칙에 있음)와
    '서울특별시에 2년 이상 거주'(새 조건)를 지명만으로 같은 근거로 보지 않게."""
    from rule_data import region_names
    regions = {sv.normalize(r) for r in region_names()}
    quotes, values = set(), set()

    def take(q):
        t = sv.normalize(q["text"] if isinstance(q, dict) else q)
        if len(t) >= 6:
            quotes.add(t)

    def strings(x):
        if isinstance(x, dict):
            for v in x.values():
                strings(v)
        elif isinstance(x, list):
            for v in x:
                strings(v)
        elif isinstance(x, str):
            t = sv.normalize(x)
            if len(t) >= 3 and not t.isdigit() and t not in regions and not re.match(r"^(N\d+|DRAFT|NEW)-", t):
                values.add(t)

    def walk(conds):
        for c in conds:
            for t in c.get("tracks", []):
                walk(t["conditions"])
            for q in c.get("source", {}).get("quote", []):
                take(q)
            strings(c.get("check"))
    for ld in doc["layers"].values():
        walk(ld["conditions"])
    for td in doc.get("tables", {}).values():
        for q in td.get("source", {}).get("quote", []):
            take(q)
    return sorted(quotes), sorted(values)


def _mask(s: str) -> str:
    return re.sub(r"\d", "#", s)


class Known:
    """형제 공고들의 문장(숫자를 가린 것 그대로 + 형제 본문 어딘가에 그대로 있음 + 비슷한 문장 85% 이상).
    본문 포함은 문장 나누기(줄바꿈)에 기대지 않는다 — 추출기를 pypdfium2로 바꾼 뒤(2026-11-09) 표 칸이 다른 줄 순서로 나와
    형제에도 있는 문장이 단위 경계만 달라 '미분류'가 됐다(N20 '7.그밖에공급신청자와생계및주거를달리한다고…')."""
    MIN_SUBSTRING = 10                # 짧은 조각은 어디에나 있어 본문 포함으로 보지 않는다(목록 기호를 뺀 길이)
    LEAD = re.compile(r"^[•■①-⑳*※○□▶◆◇·ㆍ\-–▪]+")   # 목록 기호는 공고마다 다르다('•건설공사종사자' / '-건설공사종사자')

    COMMON_MIN = 2                    # 다른 사업 등록 공고 몇 건 이상에 있으면 공통 안내로 보나

    def __init__(self, sibling_units: Sequence[Tuple[int, str]], common_bodies: Sequence[str] = ()):
        """common_bodies: 다른 사업 등록 공고들의 본문(공고마다 하나) — 판정 틀에 공고가 1건뿐이라 형제가 없는 사업(N56·N57 등)도
        주택 소유 예외·자산 산정·소득 자료 같은 공통 안내를 알아보게(2026-11-09). 강한 제한 표현이 있는 문장은 쓰지 않는다 —
        다른 사업의 자격 조건이 이 공고의 새 조건일 수 있다."""
        self.masked = {_mask(u) for _, u in sibling_units}
        self.texts = [u for _, u in sibling_units]
        self.body = "\n".join(sorted(self.masked))
        self.common = list(common_bodies)

    def has(self, u: str) -> bool:
        m = _mask(u)
        core = self.LEAD.sub("", m)
        if m in self.masked or (len(core) >= self.MIN_SUBSTRING and core in self.body):
            return True
        if len(core) >= self.MIN_SUBSTRING and not STRONG.search(u) and \
                sum(core in b for b in self.common) >= self.COMMON_MIN:
            return True
        for s in self.texts:
            if abs(len(s) - len(u)) >= len(u) * 0.3:
                continue
            m = SequenceMatcher(None, u, s, autojunk=False)
            if m.quick_ratio() >= 0.85 and m.ratio() >= 0.85:
                return True
        return False


def _flat(conds):
    for c in conds:
        yield c
        for t in c.get("tracks", []):
            yield from _flat(t["conditions"])


def classify(units: Sequence[Tuple[int, str]], doc: Dict, known: Known) -> List[Tuple[int, str, str]]:
    """→ [(쪽, 문장, 분류)] — 조건처럼 보이지 않는 문장은 뺀다."""
    quotes, values = evidence_of(doc)
    fields = " ".join(c.get("field", "") for ld in doc["layers"].values() for c in _flat(ld["conditions"]))
    has_ref = {"소득": "income" in fields, "자산": any(k in fields for k in ("assets", "real_estate", "car_value"))}
    family_first = any(c["id"].endswith("-family") for c in _flat(doc["layers"].get("생애최초", {}).get("conditions", [])))
    out, parent, priority = [], None, False
    for page, u in units:
        if u.startswith("■"):                 # 절이 바뀐다 — 우선공급 절인지
            priority = bool(PRIORITY_HEAD.match(u))
        is_evidence = any(q in u or u in q for q in quotes) or any(v in u for v in values)
        if is_evidence:
            parent = page
        elif not ENUM.match(u):
            parent = None
        if not CONDLIKE.search(u):
            continue
        ref = TABLE_REF.search(u)
        if is_evidence:
            label = "근거"
        elif (ref and has_ref[ref.group(1)]) or (SINGLE_FIRST.search(u) and family_first):
            label = "근거(규칙의 기준표·요건)"
        elif parent == page and ENUM.match(u):
            label = "근거(하위 항목)"
        elif known.has(u):
            label = "형제 공고에도"
        elif COMMON.search(u):
            label = "무관:공통 제한"
        elif BOILERPLATE.search(u):
            label = "무관:일반 안내"
        elif HOUSE_LIST.search(u) or TYPE_QUOTA.search(u):
            label = "무관:안내"
        elif ALLOCATION.search(u) and not ALLOCATION_GUARD.search(u):
            label = "무관:선정·순위"
        elif RANK.search(u) and "모집하지않" not in u:     # 순위 정의(경쟁 순서 — 자격 아님). '그 순위만 모집'은 제한 문구 점검이 잡는다
            label = "무관:선정·순위"
        elif (DEFINITION.search(u) and not STRONG.search(u)) or OWNERSHIP_EXCEPTION.search(u):
            label = "무관:정의"
        else:
            cat = None if STRONG.search(VISIT_ONLY.sub("", u)) else next((k for k, rx in UNRELATED.items() if rx.search(u)), None)
            label = f"무관:{cat}" if cat else UNCLASSIFIED
            if label == UNCLASSIFIED and priority and "모집하지않" not in u:
                label = "무관:우선공급"
        out.append((page, u, label))
    return out


@lru_cache(maxsize=None)
def _templates() -> Dict[str, str]:
    import templates as T
    tpl = {n: T.gold_sheet(n)["template"] for n in T.sheet_ids()}
    tpl.update({n: "lh.happy_housing" for n in ("N1", "N2", "N3")})
    return tpl


def template_siblings(template: Optional[str], exclude: str = "") -> List[str]:
    """그 템플릿(사업)의 등록 공고들(행복주택은 템플릿 공고 N1~N3 포함) — exclude는 빼고(평가용)."""
    from rule_data import notice_ids
    return [n for n in notice_ids() if n != exclude and template and _templates().get(n) == template]


def siblings_of(nid: str) -> List[str]:
    """등록 공고의 형제 = 같은 템플릿의 다른 등록 공고."""
    return template_siblings(_templates().get(nid), exclude=nid)


@lru_cache(maxsize=None)
def _common_body(nid: str) -> str:
    """등록 공고 본문(숫자 가림) — 다른 사업 공고의 공통 안내 대조용."""
    return "\n".join(_mask(u) for _, u in registered_units(nid))


def common_bodies(exclude: Sequence[str]) -> List[str]:
    from rule_data import notice_ids
    return [_common_body(n) for n in notice_ids() if n not in set(exclude)]


def ledger_for_registered(nid: str) -> List[Tuple[int, str, str]]:
    sibs = siblings_of(nid)
    known = Known([u for s in sibs for u in registered_units(s)], common_bodies([nid, *sibs]))
    return classify(registered_units(nid), sv.notice_doc(nid), known)


def ledger_for_draft(pdf: Path, doc: Dict, sibling_nids: Sequence[str], exclude: str = "") -> List[Tuple[int, str, str]]:
    """새 공고(초안 규칙 doc) — 형제는 그 템플릿의 등록 공고, 공통 안내는 나머지 등록 공고(exclude는 평가에서 뺄 자기 공고)."""
    known = Known([u for s in sibling_nids for u in registered_units(s)], common_bodies([exclude, *sibling_nids]))
    return classify(units_of_pdf(pdf), doc, known)


def summary(rows) -> Counter:
    return Counter(label for _, _, label in rows)


def main(argv=None):
    from rule_data import notice_ids
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("nid", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", help="미분류 문장 검토 목록(.md)")
    a = ap.parse_args(argv)
    nids = notice_ids() if a.all else [a.nid]
    total, lines = Counter(), ["# 조항 장부 — 미분류 문장 검토 목록", "",
                               "등록 공고마다 '조건처럼 보이지만 규칙 근거·형제 공고·무관 범주 어디에도 없는 문장'(`tools/clause_ledger.py`).",
                               "각 문장을 원문과 대조해 ① 규칙에 빠진 조건이면 규칙을 고치고 ② 조건이 아니면 범주를 보강한다.", ""]
    for nid in nids:
        rows = ledger_for_registered(nid)
        c = summary(rows)
        total += c
        print(f"{nid}: 조건형 문장 {sum(c.values())} — 근거 {c['근거'] + c['근거(하위 항목)']} · 형제 공고에도 {c['형제 공고에도']} · "
              f"무관 {sum(v for k, v in c.items() if k.startswith('무관'))} · 미분류 {c[UNCLASSIFIED]}")
        if c[UNCLASSIFIED]:
            lines += [f"## {nid} ({c[UNCLASSIFIED]})", ""] + [f"- p.{p} {u[:160]}" for p, u, lab in rows
                                                              if lab == UNCLASSIFIED] + [""]
    print("합계:", dict(total))
    if a.out:
        Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("검토 목록:", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
