# -*- coding: utf-8 -*-
"""find.py — 청약 흥신소 주 흐름: 기본 조건 → 지금 모집 중인 LH·SH 공고 목록(docs/12 '2단계 재설계' ②-2).

    out = find_open(master, live_rows, today, analyzed=None, filters=None)

공고마다 판정 근거를 정한다:
    confirmed  그 공고문 기준 — 등록 공고(registered_id) 또는 올려서 분석된 공고(analyzed 콜백이 Draft를 돌려줌)
    preview    같은 사업 최근 등록 공고(대표 공고) 기준 예비 판정(src/live_judge.py) — 판정 틀은 있으나 공고문 분석 전
    none       판정하지 않는 사업 — 이름·기간·공식 링크만

결과(카드 묶음 — 화면 순서):
    eligible    지원 가능(이 공고문 기준)
    likely      지원 가능 (단, 공고문 내 지원자격 상세 확인 필요) — 예비. 2026-11-10 사용자 결정 표시
    needs_info  지원가능 판단을 위한 추가정보 요청 — 정보 부족(추가 질문과 연결)
    verify      실제 공고문 확인필요(접힘) — 수동 확인, 대표 공고 기준 지원 불가지만 공고마다 다를 수 있는 조건
    unlikely    지원 어려움(접힘) — 확정 지원 불가와 예비 '어려움'
    unjudged    판정하지 않는 사업(접힘)
    ('확인 필요'를 둘로 나눔 — 2026-11-11 사용자 결정: 목록 위쪽에는 실제로 넣어 볼 만한 공고만)

판정 로직은 엔진·매처·예비 판정을 그대로 부른다. 입력한 조건은 저장하지 않는다.
"""
import dataclasses
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Callable, Dict, List, Optional, Tuple

import live_judge as J
import live_notices as LN
from matcher import FIELD_LABELS, Match, MasterProfile, evaluate_layer, missing_fields, scoped_profile
from notices_data import ALL_NOTICES
from rule_data import region_groups

ELIGIBLE, LIKELY, NEEDS_INFO, VERIFY, UNLIKELY, UNJUDGED = (
    "eligible", "likely", "needs_info", "verify", "unlikely", "unjudged")
GROUPS = (ELIGIBLE, LIKELY, NEEDS_INFO, VERIFY, UNLIKELY, UNJUDGED)
COLLAPSED = (VERIFY, UNLIKELY, UNJUDGED)
CONFIRMED, PREVIEW, NONE = "confirmed", "preview", "none"
LABELS = {
    ELIGIBLE: "지원 가능",
    LIKELY: "지원 가능 (단, 공고문 내 지원자격 상세 확인 필요)",
    NEEDS_INFO: "지원가능 판단을 위한 추가정보 요청",
    VERIFY: "실제 공고문 확인필요",
    UNLIKELY: "지원 어려움",
    UNJUDGED: "판정하지 않는 사업",
}
BASIS_NOTE = {
    CONFIRMED: "이 공고문 기준 판정입니다.",
    PREVIEW: "같은 사업 최근 공고({title}, {date} 공고) 기준입니다. 이 공고문의 지원자격을 꼭 확인하세요 — 공고문을 올리면 바로 확정 판정합니다.",
    NONE: "이 사업은 아직 판정하지 않습니다. 공식 공고에서 자격을 확인하세요.",
}
SALE_TEMPLATES = frozenset({"lh.newlywed_town_sale", "lh.public_sale", "sh.land_sale", "lh.share_sale"})
RENT, SALE = "임대", "분양"
STALE_HOURS = 24
MAX_QUESTIONS = 2
VERDICT_GROUP = {"ELIGIBLE": ELIGIBLE, "NEEDS_INFO": NEEDS_INFO, "MANUAL_REVIEW": VERIFY, "INELIGIBLE": UNLIKELY}


def preview_group(lp) -> str:
    """예비 판정 → 묶음. 확인 필요는 정보 부족이면 추가정보 요청, 그 밖(수동 확인·공고마다 다른 조건으로 지원 불가)은 공고문 확인."""
    if lp.outcome == J.LIKELY:
        return LIKELY
    if lp.outcome == J.UNLIKELY:
        return UNLIKELY
    return NEEDS_INFO if lp.verdict == "NEEDS_INFO" else VERIFY


# ------------------------------------------------------------------ 대표 공고 후보(등록 공고)
_REGS: Optional[List[J.Registered]] = None
_INDEX: Optional[J.CommonIndex] = None


def registered() -> Tuple[List[J.Registered], J.CommonIndex]:
    """등록 공고 → 판정 틀(대표 공고 후보)과 공통 조건 색인. 배포 안에서 바뀌지 않으므로 한 번만 만든다."""
    global _REGS, _INDEX
    if _REGS is None:
        import sys
        from pathlib import Path
        tools = str(Path(__file__).resolve().parent.parent / "tools")
        if tools not in sys.path:
            sys.path.insert(0, tools)
        import templates as T
        base = {"N1": "lh.happy_housing", "N2": "lh.happy_housing", "N3": "lh.happy_housing"}
        regs = []
        for nid, n in ALL_NOTICES.items():
            tname = base.get(nid) or T.gold_sheet(nid)["template"]
            regs.append(J.Registered(nid, tname, n.meta.get("issuer"), n.meta.get("program"), n.announcement_date))
        _REGS, _INDEX = regs, J.CommonIndex(regs)
    return _REGS, _INDEX


# ------------------------------------------------------------------ 공고 한 건
def _d(s) -> Optional[date]:
    if s is None or isinstance(s, date):
        return s
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def kind_of(row: Dict) -> str:
    """임대 / 분양 — 판정 틀이 있으면 틀로, 없으면 출처 유형·제목으로(분양전환 임대는 임대)."""
    if row.get("template"):
        return SALE if row["template"] in SALE_TEMPLATES else RENT
    text = f"{row.get('kind') or ''} {row.get('program') or ''} {row.get('title') or ''}"
    return SALE if "분양" in text and "분양전환" not in text and "임대" not in (row.get("kind") or "") else RENT


def sido_of(area: Optional[str]) -> Optional[str]:
    """거주지(시·군 표준 이름) → 시·도 — 공고 지역(LH: '서울특별시'·'경기도' …)과 맞추려고."""
    if not area:
        return None
    for group, names in region_groups().items():
        if area in names:
            return "경기도" if group == "경기도" else area
    return area


def _region_ok(row: Dict, regions: Optional[List[str]]) -> bool:
    if not regions:
        return True
    r = row.get("region") or ""
    return not r or "전국" in r or any(x[:2] in r for x in regions)


def schedule_of(row: Dict, today: date) -> Dict:
    """접수 상태 — open(접수 중) / upcoming(접수 예정) / unknown, 마감·시작까지 남은 날."""
    s, e = _d(row.get("window_start")), _d(row.get("window_end"))
    if s and today < s:
        return {"code": "upcoming", "text": "접수 예정", "days": (s - today).days, "start": s.isoformat(),
                "end": e.isoformat() if e else None}
    if e and today <= e:
        return {"code": "open", "text": "접수 중", "days": (e - today).days, "start": s.isoformat() if s else None,
                "end": e.isoformat()}
    # 접수기간을 못 읽음 — '접수 중'이라고 단정하지 않는다(2026-11-12, 주택포털 SH 요약에 날짜가 없는 공고 등)
    text = (f"{row['status']} · 접수 일정은 공고문 확인" if row.get("status") in ("모집중", "공고중", "접수중")
            else "접수 일정은 공고문 확인")
    return {"code": "unknown", "text": text, "days": None,
            "start": s.isoformat() if s else None, "end": e.isoformat() if e else None}


def _confirmed_layers(m: MasterProfile, notice, judge: Optional[Callable] = None) -> Tuple[List[Dict], List[Match]]:
    """그 공고문 기준 계층별 판정 — judge가 있으면(올린 공고 초안) grading.judge, 없으면 등록 공고 판정(evaluate_layer)."""
    layers, matches = [], []
    for layer in notice.layers:
        if judge is None:
            r = evaluate_layer(m, notice, layer)
        else:
            r = judge(scoped_profile(m, notice, layer), layer)
        if r.verdict == "NOT_OFFERED":
            continue
        layers.append({"layer": layer, "result": VERDICT_GROUP.get(r.verdict, VERIFY), "verdict": r.verdict})
        matches.append(Match(notice, layer, r))
    return layers, matches


def _preview_layers(m: MasterProfile, rep: J.Registered, announced: Optional[date]) -> Tuple[List[Dict], List[Match]]:
    regs, index = registered()
    notice = ALL_NOTICES[rep.notice_id]
    dated = dataclasses.replace(notice, announcement_date=announced) if announced else notice
    layers, matches = [], []
    for layer in notice.layers:
        p = scoped_profile(m, dated, layer)          # 나이는 수집 공고의 공고일 기준
        lp = J.preview_layer(p, layer, notice, rep.template, index, announced)
        if lp.outcome == J.NONE:
            continue
        layers.append({"layer": layer, "result": preview_group(lp), "verdict": lp.verdict,
                       "reasons": lp.reasons[:3]})
        if lp.result is not None:
            matches.append(Match(dated, layer, lp.result))
    return layers, matches


def _best(layers: List[Dict]) -> str:
    got = {x["result"] for x in layers}
    return next((g for g in GROUPS if g in got), UNJUDGED)


def judge_row(m: MasterProfile, row: Dict, today: date, analyzed: Optional[Callable] = None) -> Tuple[Dict, List[Match]]:
    """수집 공고(같은 공고 묶은 행) 하나 → 공고 카드와 판정(추가 질문 집계용)."""
    announced = _d(row.get("announced"))
    basis, rep, layers, matches = NONE, None, [], []
    rid = row.get("registered_id")
    if rid and rid in ALL_NOTICES:
        basis = CONFIRMED
        layers, matches = _confirmed_layers(m, ALL_NOTICES[rid])
    elif row.get("template"):
        d = analyzed(row) if analyzed else None
        if d is not None and d.notice is not None:
            import grading
            basis = CONFIRMED
            layers, matches = _confirmed_layers(m, d.notice, lambda p, layer: grading.judge(d, p, layer)[0])
        else:
            regs, _ = registered()
            rep = J.pick_representative(row["template"], row.get("issuer"), row.get("program"), announced, regs)
            if rep is not None:
                basis = PREVIEW
                layers, matches = _preview_layers(m, rep, announced)
    result = _best(layers) if basis != NONE else UNJUDGED
    if basis != NONE and not layers:
        result = UNJUDGED if basis == PREVIEW else VERIFY
    note = BASIS_NOTE[basis]
    if basis == PREVIEW:
        note = note.format(title=ALL_NOTICES[rep.notice_id].title, date=rep.announcement_date.isoformat())
    card = {
        "key": f"{row['source']}:{row['external_id']}", "source": row["source"], "external_id": row["external_id"],
        "title": LN.clean_title(row["title"]), "issuer": row.get("issuer"), "program": row.get("program"),
        "kind": kind_of(row), "region": row.get("region"), "announced": announced.isoformat() if announced else None,
        "schedule": schedule_of(row, today), "url": row.get("url"), "basis": basis, "basis_note": note,
        "preview_from": None if rep is None else {"notice_id": rep.notice_id, "title": ALL_NOTICES[rep.notice_id].title,
                                                   "announced": rep.announcement_date.isoformat()},
        "registered_id": rid if basis == CONFIRMED and rid else None,
        "result": result, "label": LABELS[result], "layers": layers,
        "related": [{"title": r["title"], "url": r.get("url")} for r in row.get("related", [])],
    }
    return card, matches


# ------------------------------------------------------------------ 목록
_LIVE_FIELDS = {f.name for f in dataclasses.fields(LN.LiveNotice)}


def relink(rows: List[Dict]) -> List[Dict]:
    """저장된 수집 행을 지금 코드로 다시 잇는다(사업 분류·판정 틀·등록 공고) — 수집 뒤 등록한 공고·분류 보완이 바로 반영되게."""
    out = []
    for r in rows:
        kw = {k: (r.get(k).isoformat() if isinstance(r.get(k), date) else r.get(k)) for k in _LIVE_FIELDS}
        for k in ("kind", "region", "status", "url", "title"):
            kw[k] = kw[k] or ""
        kw["detail_key"] = kw["detail_key"] or {}
        n = LN.link(LN.LiveNotice(**kw))
        out.append({**r, **n.as_dict()})
    return out


def _is_open(row: Dict, today: date) -> bool:
    e = _d(row.get("window_end"))
    return row.get("status") not in LN.CLOSED_STATUS and (e is None or e >= today)


def registered_open_rows(at: datetime, linked: set) -> List[Dict]:
    """접수 중·예정인 등록 공고 중 수집 목록에 없는 것(SH 공고 — 수집 전, 저장소 장애 때 대체 목록)."""
    from schedule import load_schedules, statuses
    stat, sched = statuses(list(ALL_NOTICES), at), load_schedules()
    out = []
    for nid, s in stat.items():
        if not s.applicable or nid in linked:
            continue
        n, sc = ALL_NOTICES[nid], sched.get(nid)
        ws = [w for w in sc.windows] if sc else []
        out.append({"source": "registered", "external_id": nid, "title": n.title, "issuer": n.meta.get("issuer"),
                    "kind": n.meta.get("program") or "", "region": "", "announced": n.announcement_date.isoformat(),
                    "window_start": min(w.start for w in ws).date().isoformat() if ws else None,
                    "window_end": max(w.end for w in ws).date().isoformat() if ws else None,
                    "status": s.text, "url": n.meta.get("source", {}).get("url") or "", "program": n.meta.get("program"),
                    "template": None, "registered_id": nid, "route": LN.REGISTERED, "related": []})
    return out


def _sort_key(card: Dict):
    s = card["schedule"]
    return (GROUPS.index(card["result"]), {"open": 0, "upcoming": 1}.get(s["code"], 2),
            s["end"] or "9999", card["title"])


def _given(m: MasterProfile) -> set:
    """이미 입력한 항목(엔진 필드 이름) — 여러 항목을 읽는 조건이 정보 부족이어도 이미 준 것은 다시 묻지 않는다."""
    given = {k for k, v in m.common.items() if v is not None}
    if m.birth_date is not None:
        given.add("age")
    if m.home_self is not None or m.home_household is not None:
        given.add("home_ownership")
    if m.common.get("household_size") == 1:          # 1인 가구면 본인 = 세대
        for f, own, house in (("monthly_income", m.income_self, m.income_household),
                              ("total_assets", m.assets_self, m.assets_household),
                              ("car_value", m.car_self, m.car_household)):
            if own is not None or house is not None:
                given.add(f)
    return given


def questions(matches: List[Match], m: Optional[MasterProfile] = None) -> List[Dict]:
    """정보 부족이 가장 많이 걸린 항목 MAX_QUESTIONS개 — '이것만 알려 주시면 N건이 더 판정됩니다'."""
    given = _given(m) if m is not None else set()
    counts = [(f, n) for f, n in missing_fields(matches).items() if f not in given]
    return [{"field": f, "label": FIELD_LABELS.get(f, f), "notices": n} for f, n in counts[:MAX_QUESTIONS]]


def find_open(m: MasterProfile, live_rows: List[Dict], at: datetime, analyzed: Optional[Callable] = None,
              regions: Optional[List[str]] = None, kind: Optional[str] = None, live_ok: bool = True) -> Dict:
    """기본 조건 → 지금 모집 중인 공고 카드 목록. live_rows: 저장소의 수집 공고(같은 공고 묶기 전).
    live_ok=False(저장소에 닿지 않음)면 등록 공고만으로 만들고 알린다."""
    today = at.date()
    rows = [r for r in LN.merge_duplicates([r for r in live_rows if _is_open(r, today)])] if live_ok else []
    linked = {r.get("registered_id") for r in rows if r.get("registered_id")}
    rows += registered_open_rows(at, linked)
    cards, matches = [], []
    for row in rows:
        if not _region_ok(row, regions) or (kind in (RENT, SALE) and kind_of(row) != kind):
            continue
        card, ms = judge_row(m, row, today, analyzed)
        cards.append(card)
        matches += ms
    cards.sort(key=_sort_key)
    seen = [r.get("last_seen") for r in live_rows if r.get("last_seen")]
    collected = max(seen) if seen else None
    stale = bool(collected and isinstance(collected, datetime)
                 and (at - (collected if collected.tzinfo else collected.replace(tzinfo=at.tzinfo))).total_seconds()
                 > STALE_HOURS * 3600)
    notice = None
    if not live_ok:
        notice = "실시간 공고 목록을 잠시 불러오지 못했습니다. 지금은 등록된 공고만 보여 드립니다."
    elif stale:
        notice = f"공고 목록이 {collected:%m월 %d일 %H시} 이후 갱신되지 않았습니다. 공식 공고에서 최신 상태를 확인하세요."
    return {"at": at.isoformat(), "collected_at": collected.isoformat() if isinstance(collected, datetime) else None,
            "stale": stale, "notice": notice, "labels": LABELS, "groups": list(GROUPS), "collapsed": list(COLLAPSED),
            "counts": {g: sum(1 for c in cards if c["result"] == g) for g in GROUPS},
            "questions": questions(matches, m), "items": cards}


# ------------------------------------------------------------------ 올려서 분석된 공고 잇기(F35)
def match_analyzed(row: Dict, candidates: List[Dict]) -> Optional[str]:
    """수집 공고와 같은 공고로 보이는 분석 공고의 sha256 — 기관·공고일·사업 키가 같고 제목이 비슷(0.7 이상)할 때만."""
    title = LN._norm(row.get("title") or "")
    want = LN._program_key(row.get("program"))
    best, best_r = None, 0.0
    for c in candidates:
        if c.get("issuer") != row.get("issuer") or str(c.get("announcement_date")) != str(row.get("announced")):
            continue
        prog = LN._program_key(c.get("program"))
        if want and prog and want != prog:
            continue
        r = SequenceMatcher(None, title, LN._norm(c.get("title") or "")).ratio()
        if r > best_r:
            best, best_r = c["sha256"], r
    return best if best_r >= 0.7 else None

