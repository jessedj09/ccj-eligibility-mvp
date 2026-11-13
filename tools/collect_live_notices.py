# -*- coding: utf-8 -*-
"""collect_live_notices.py — 지금 모집 중인 LH·SH 공고를 공공데이터포털에서 모아 저장한다(실시간 공고 연결 1단계, docs/12).

    python tools/collect_live_notices.py              # 모아서 공유 저장소(live_notices)에 넣고 요약 출력
    python tools/collect_live_notices.py --dry-run    # 저장하지 않고 요약만(갈래별 건수·판정 틀 있는 공고)
    python tools/collect_live_notices.py --json out.json

- 인증키: 환경변수 `DATA_GO_KR_KEY`(사용자가 직접 넣음 — 출력·저장하지 않는다). 없으면 종료코드 2.
- 출처: LH 분양임대공고문 조회(주택 유형 05·06·13·39, 최근 2개월) + 상세 정보(단지별 청약 접수기간 — 새 공고·하루 지난 것만)
  + 청약홈 분양정보 조회(LH·SH 공고만, 최근 60일)
  + 서울시 주택포털 SH 공공임대·공공분양 목록(최근 2개월)과 모집 중인 공고의 상세 요약(접수기간·주택관리번호 — 2026-11-12 ②-5).
  공고문 PDF는 내려받지 않는다.
- 저장소가 없으면(DATABASE_URL 없음·CCJ_STORE=off) 상세 조회는 공고마다 하고 저장은 건너뛴다.
- API가 실패하면 종료코드 1(예약 작업이 실패로 알린다). 한 출처만 실패해도 다른 출처는 저장한다.
"""
import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, timedelta
from typing import Optional
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools")]
import live_notices as L  # noqa: E402

log = logging.getLogger("ccj.collect")
KEY_ENV = "DATA_GO_KR_KEY"
LH_LIST = "https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1"
LH_DETAIL = "https://apis.data.go.kr/B552555/lhLeaseNoticeDtlInfo1/getLeaseNoticeDtlInfo1"
APPLYHOME = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"
PAGE = 100
MAX_PAGES = 10                 # 유형마다 1,000건까지(실제 2개월 공고는 유형당 200건 안팎)
PAUSE = 0.2                    # 호출 사이 쉼 — 개발 계정 하루 호출 한도 안에서 천천히
TIMEOUT = 20                   # 호출 하나의 시간 한도(초)
RETRIES = 1                    # 접속 실패·시간 초과면 이만큼 더 시도(2026-11-10 첫 예약 실행: GitHub 서버에서 상세 8건이 TLS 연결 시간 초과)
RETRY_WAIT = 3                 # 다시 시도하기 전 쉼(초)
USER_AGENT = "ccj-collector/0.1"
SEOUL_PAUSE = 1.0              # 주택포털은 화면 — 공공데이터 API보다 천천히
AUTO_MAX = 8                   # 한 번 수집에 자동 분석할 LH 공고문 수(2026-11-14 A안 — 접수 시작 가까운 순)
AUTO_PAUSE = 2.0               # 공고문 내려받기 사이 쉼(초)
PDF_TIMEOUT = 60
PDF_MAX = 25 * 1024 * 1024
SEOUL_MAX_PAGES = 5


class SourceError(Exception):
    pass


def _get(url: str, key: str, params: dict):
    q = urllib.parse.urlencode({"serviceKey": key, **params})
    req = urllib.request.Request(f"{url}?{q}", headers={"User-Agent": USER_AGENT})
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                text = r.read().decode("utf-8", "replace")
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == RETRIES:
                raise SourceError(str(e).replace(key, "***")) from None
            time.sleep(RETRY_WAIT)
    time.sleep(PAUSE)
    try:
        return json.loads(text)
    except ValueError:
        # 인증 오류 등은 XML로 온다 — 키를 가린 앞부분만 남긴다
        raise SourceError("JSON이 아닌 응답: " + text.replace(key, "***")[:200]) from None


def _get_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                text = r.read().decode("utf-8", "replace")
            break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == RETRIES:
                raise SourceError(str(e)) from None
            time.sleep(RETRY_WAIT)
    time.sleep(SEOUL_PAUSE)
    return text


def _get_bytes(url: str) -> bytes:
    """공고문 PDF(LH 상세 API가 준 첨부 주소). 크기 상한 PDF_MAX."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=PDF_TIMEOUT) as r:
                size = int(r.headers.get("Content-Length") or 0)
                if size > PDF_MAX:
                    raise SourceError(f"공고문이 너무 큽니다({size // 1024 // 1024}MB)")
                data = r.read(PDF_MAX + 1)
            if len(data) > PDF_MAX:
                raise SourceError("공고문이 너무 큽니다")
            return data
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == RETRIES:
                raise SourceError(str(e)) from None
            time.sleep(RETRY_WAIT)


def auto_analyze(store, grouped, analyzed, today: date, limit: int = AUTO_MAX) -> list:
    """분석 대기 LH 공고의 공고문을 공식 API 주소로 내려받아 재판소와 같은 자동 분석으로 저장한다(2026-11-14 사용자 결정 A안 —
    robots가 /lhapply/lhFile.do를 막지만 공식 API가 주는 주소, 비영리·공익 목적). 같은 공고문(주소)은 한 번만 시도하고
    결과를 수집 공고의 detail_key.auto에 남긴다. PDF는 분석 뒤 보관하지 않는다(후속 작업이 있을 때만 저장소 정책대로 잠시).
    → [(행, 기록)]"""
    import hashlib
    import analysis
    import coverage as V
    import notice_identify as ni
    todo = []
    for r in V.pending(grouped, analyzed):
        dk = r.get("detail_key") or {}
        pdf = dk.get("pdf")
        if r.get("source") != L.LH_SOURCE or not pdf or (dk.get("auto") or {}).get("pdf") == pdf:
            continue
        todo.append((r, pdf))
    out = []
    for r, pdf in todo[:limit]:
        t0 = time.time()
        rec = {"pdf": pdf, "at": today.isoformat()}
        try:
            data = _get_bytes(pdf)
            rec["kb"] = len(data) // 1024
            ident = ni.identify_pdf(data)
            if ident.status in (ni.NOT_NOTICE, ni.UNREADABLE, ni.REGISTERED):
                rec["result"] = ident.status.lower()
            else:
                d = analysis.analyze(data, ident, store, title=r["title"], origin="collect", source_url=r.get("url"))
                rec.update(result=d.status, grade=analysis.overall_grade(d), sha=hashlib.sha256(data).hexdigest())
        except SourceError as e:
            rec.update(result="download_error", error=str(e)[:200])
        except Exception as e:      # noqa: BLE001 — 분석 실패가 수집을 막지 않는다
            rec.update(result="analysis_error", error=f"{type(e).__name__}: {e}"[:200])
        rec["seconds"] = round(time.time() - t0, 1)
        store.merge_live_detail(r["source"], r["external_id"], {"auto": rec})
        out.append((r, rec))
        print(f"  [자동 분석] {L.clean_title(r['title'])[:40]} | {rec['result']}{' · ' + rec['grade'] if rec.get('grade') else ''}"
              f" | {rec.get('kb', '?')}KB · {rec['seconds']}초")
        time.sleep(AUTO_PAUSE)
    return out


def collect_seoul(key: str, today: date):
    """서울시 주택포털 SH 목록(임대·분양, 최근 2개월) — LiveNotice 목록(접수기간은 add_details가 상세에서). 화면 구조가 바뀌면 SourceError."""
    out, since = [], (today - timedelta(days=62)).isoformat()
    for kind, path in L.SEOUL_LISTS:
        for cp in range(1, SEOUL_MAX_PAGES + 1):
            try:
                rows = L.parse_seoul_list(_get_html(L.SEOUL_BASE + path.format(cp)), kind)
            except L.SeoulFormatError as e:
                raise SourceError(f"주택포털 {kind} 목록: {e}") from None
            out += [n for n in (L.seoul_notice(r) for r in rows if (r["posted"] or "") >= since) if n is not None]
            if len(rows) < 10 or not rows or (rows[-1]["posted"] or "") < since:
                break
    return out


def _seoul_wants_detail(n, today: date) -> bool:
    """상세는 모집 중인 공고만(분양은 최근 공고) — 이미 마감한 공고까지 열지 않는다."""
    if n.status == "모집중":
        return True
    return n.status == "" and (n.announced or "") >= (today - timedelta(days=45)).isoformat()


def collect_myhome(key: str) -> dict:
    """마이홈 공공주택 모집공고(임대·분양) → LH 공고 ID별 보조 정보(묶음 C). 보조 출처라 실패해도 수집을 실패로 만들지 않는다."""
    items = []
    for url in (L.MYHOME_RENT, L.MYHOME_SALE):
        for page in range(1, MAX_PAGES + 1):
            resp = _get(url, key, {"numOfRows": PAGE, "pageNo": page})
            got = L.parse_myhome(resp)
            items += got
            if len(got) < PAGE or page * PAGE >= L.myhome_total(resp):
                break
    return L.myhome_info(items)


def collect_lh(key: str, today: date):
    """LH 주택 공고(최근 2개월, 유형별 쪽 넘김) — LiveNotice 목록."""
    out = []
    start = (today - timedelta(days=62)).strftime("%Y%m%d")
    for upp in L.LH_TYPES:
        for page in range(1, MAX_PAGES + 1):
            resp = _get(LH_LIST, key, {"PG_SZ": PAGE, "PAGE": page, "UPP_AIS_TP_CD": upp,
                                       "PAN_ST_DT": start, "PAN_ED_DT": today.strftime("%Y%m%d")})
            rows = L.parse_lh_list(resp)
            out += rows
            if len(rows) < PAGE or page * PAGE >= L.lh_total(resp):
                break
    return out


def collect_applyhome(key: str, today: date):
    resp = _get(APPLYHOME, key, {"page": 1, "perPage": 500,
                                 "cond[RCRIT_PBLANC_DE::GTE]": (today - timedelta(days=60)).isoformat()})
    return L.parse_applyhome(resp, today)


def add_details(key: str, rows, needed, today: Optional[date] = None):
    """상세 조회가 필요한 LH 공고·모집 중인 주택포털 SH 공고만 접수기간을 채운다. → (새 목록, 조회한 키 집합)."""
    today = today or date.today()
    out, fetched = [], set()
    for n in rows:
        k = (n.source, n.external_id)
        if n.source == L.SEOUL_SOURCE and k in needed and _seoul_wants_detail(n, today):
            try:
                n = L.with_seoul_detail(n, _get_html(L.SEOUL_BASE + n.detail_key["view"]))
                fetched.add(k)
            except SourceError as e:
                log.warning("주택포털 상세 조회 실패 %s: %s", n.title[:30], e)
        elif n.source == L.LH_SOURCE and k in needed and n.detail_key.get("PAN_ID"):
            try:
                n = L.with_detail(n, _get(LH_DETAIL, key, n.detail_key))
                fetched.add(k)
            except SourceError as e:
                log.warning("상세 조회 실패 %s: %s", n.external_id, e)
        out.append(n)
    return out, fetched


def report_coverage(store, grouped, today: date, autos=()) -> None:
    """확정 판정 범위·분석 대기 공고·예비 판정 감시(묶음 A, 2026-11-13). 새로 분석된 공고는 예비 ↔ 확정을 비교해 기록한다.
    GitHub 작업에서는 요약($GITHUB_STEP_SUMMARY)에도 쓴다."""
    import coverage as V
    analyzed = store.analyzed_notices() if store else []
    cov, waiting = V.coverage(grouped, analyzed), V.pending(grouped, analyzed)
    print(f"확정 판정 범위 {cov['pct']}% — 등록 {cov.get('registered', 0)} + 분석 {cov.get('analyzed', 0)} / 판정 대상 {cov['target']}"
          f" · 분석 대기 {len(waiting)}건")
    for r in waiting:
        print(f"  [분석 대기] {r.get('window_start') or '?'}~{r.get('window_end') or '?'} | {r.get('issuer')} {r.get('program')} | "
              f"{L.clean_title(r['title'])[:50]} | 요청 {r.get('request_count') or 0}")
    checks = []
    if store:
        import find
        pairs = [(r, find.match_analyzed(r, analyzed, grouped)) for r in grouped if r.get("route") == L.TEMPLATE]
        pairs = [(r, sha) for r, sha in pairs if sha]
        done = store.preview_checked([sha for _, sha in pairs])
        for r, sha in pairs:
            if sha in done:
                continue
            try:
                import analysis
                import draft
                snap = store.latest_analysis(sha, analysis.analysis_version())
                got = V.check_preview(r, draft.from_snapshot(snap)) if snap else None
            except Exception as e:      # noqa: BLE001 — 감시가 수집을 막지 않는다
                log.warning("예비 판정 비교 실패 %s: %s", r["title"][:30], e)
                continue
            if got:
                tname, c = got
                store.record_preview_check(sha, tname, c["compared"], c["missed"], c["likely_ok"], c["likely_wrong"])
                checks.append((r["title"], tname, c))
                print(f"  [예비 판정 비교] {L.clean_title(r['title'])[:40]} | {tname} | 비교 {c['compared']} · 놓침 {c['missed']}")
    stopped = store.preview_stopped() if store else frozenset()
    if stopped:
        print("예비 '어려움'을 멈춘 판정 틀:", ", ".join(sorted(stopped)))
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(V.summary_markdown(cov, waiting, checks, stopped, today, autos) + "\n")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="저장하지 않고 요약만")
    ap.add_argument("--json", help="모은 공고를 이 파일에 JSON으로(검토용)")
    a = ap.parse_args(argv)
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        print(f"{KEY_ENV} 환경변수가 없습니다.")
        return 2
    today = date.today()
    from store import get_store
    store = None if a.dry_run else get_store()
    if store is not None and not store.available:
        store = None

    rows, failed = [], []
    for name, fn in (("LH", collect_lh), ("청약홈", collect_applyhome), ("서울시 주택포털(SH)", collect_seoul)):
        try:
            got = fn(key, today)
            rows += got
            print(f"{name}: {len(got)}건")
        except SourceError as e:
            failed.append(name)
            print(f"{name}: 실패 — {e}")

    keys = [(n.source, n.external_id) for n in rows if n.source in (L.LH_SOURCE, L.SEOUL_SOURCE)]
    needed = (store.live_detail_needed(keys) if store and type(store).__name__ != "NullStore" else None)
    needed = set(keys) if needed is None else needed
    rows, fetched = add_details(key, rows, needed, today)
    rows = [L.link(n) for n in rows]
    try:
        info = collect_myhome(key)
    except SourceError as e:
        info = {}
        print(f"마이홈(보조 정보): 실패 — {e} (지난 값 유지)")
    filled = differ = 0
    if info:
        out = []
        for n in rows:
            mi = info.get(n.external_id) if n.source == L.LH_SOURCE else None
            if mi and mi.get("window"):
                if not n.window_start:
                    filled += 1
                elif (n.window_start, n.window_end) != tuple(mi["window"]):
                    differ += 1
            out.append(L.with_myhome(n, mi) if mi else n)
        rows = out
        print(f"마이홈(보조 정보): LH 공고 {sum(1 for n in rows if n.source == L.LH_SOURCE and n.external_id in info)}건 연결 · "
              f"접수기간 보충 {filled}건 · LH 상세와 다름 {differ}건")

    saved = 0
    if store and type(store).__name__ != "NullStore":
        saved = store.upsert_live([dict(n.as_dict(), extra=info.get(n.external_id) if n.source == L.LH_SOURCE else None)
                                   for n in rows], fetched)
    open_rows = [n for n in rows if L.is_open(n, today)]
    live = store and type(store).__name__ != "NullStore"
    import find
    # 저장소가 있으면 저장된 행(분석 요청 건수·주택관리번호 포함)으로, 없으면 이번에 모은 행으로 요약한다
    base = find.relink(store.live_notices(open_only=True, limit=1000)) if live else [n.as_dict() for n in open_rows]
    grouped = L.merge_duplicates([r for r in base if find._is_open(r, today)])   # 정정공고·LH와 청약홈의 같은 공고는 하나로
    routes = Counter(r["route"] for r in grouped)
    print(f"상세 조회 {len(fetched)}건 · 저장 {saved}건" + ("" if store and saved else " (저장소 없음 — 저장 안 함)"))
    print(f"마감 안 된 공고 {len(grouped)}건(같은 공고 묶기 전 {len(open_rows)}건): 등록 공고 {routes[L.REGISTERED]} · 판정 틀 있음 {routes[L.TEMPLATE]} · "
          f"판정 안 하는 사업 {routes[L.UNSUPPORTED]}")
    autos = []
    if live:
        autos = auto_analyze(store, grouped, store.analyzed_notices(), today)
        if autos:
            print(f"자동 분석 {len(autos)}건: " + ", ".join(f"{k} {v}" for k, v in Counter(x['result'] for _, x in autos).items()))
    report_coverage(store if live else None, grouped, today, autos)
    if a.json:
        Path(a.json).write_text(json.dumps([n.as_dict() for n in rows], ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
