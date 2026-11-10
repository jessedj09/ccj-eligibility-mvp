# -*- coding: utf-8 -*-
"""collect_live_notices.py — 지금 모집 중인 LH·SH 공고를 공공데이터포털에서 모아 저장한다(실시간 공고 연결 1단계, docs/12).

    python tools/collect_live_notices.py              # 모아서 공유 저장소(live_notices)에 넣고 요약 출력
    python tools/collect_live_notices.py --dry-run    # 저장하지 않고 요약만(갈래별 건수·판정 틀 있는 공고)
    python tools/collect_live_notices.py --json out.json

- 인증키: 환경변수 `DATA_GO_KR_KEY`(사용자가 직접 넣음 — 출력·저장하지 않는다). 없으면 종료코드 2.
- 출처: LH 분양임대공고문 조회(주택 유형 05·06·13·39, 최근 2개월) + 상세 정보(단지별 청약 접수기간 — 새 공고·하루 지난 것만)
  + 청약홈 분양정보 조회(LH·SH 공고만, 최근 60일). 공고문 PDF는 내려받지 않는다.
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


def add_details(key: str, rows, needed):
    """상세 조회가 필요한 LH 공고만 접수기간을 채운다. → (새 목록, 조회한 키 집합)."""
    out, fetched = [], set()
    for n in rows:
        k = (n.source, n.external_id)
        if n.source == L.LH_SOURCE and k in needed and n.detail_key.get("PAN_ID"):
            try:
                n = L.with_detail(n, _get(LH_DETAIL, key, n.detail_key))
                fetched.add(k)
            except SourceError as e:
                log.warning("상세 조회 실패 %s: %s", n.external_id, e)
        out.append(n)
    return out, fetched


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
    for name, fn in (("LH", collect_lh), ("청약홈", collect_applyhome)):
        try:
            got = fn(key, today)
            rows += got
            print(f"{name}: {len(got)}건")
        except SourceError as e:
            failed.append(name)
            print(f"{name}: 실패 — {e}")

    keys = [(n.source, n.external_id) for n in rows if n.source == L.LH_SOURCE]
    needed = (store.live_detail_needed(keys) if store and type(store).__name__ != "NullStore" else None)
    needed = set(keys) if needed is None else needed
    rows, fetched = add_details(key, rows, needed)
    rows = [L.link(n) for n in rows]

    saved = 0
    if store and type(store).__name__ != "NullStore":
        saved = store.upsert_live([n.as_dict() for n in rows], fetched)
    open_rows = [n for n in rows if L.is_open(n, today)]
    routes = Counter(n.route for n in open_rows)
    print(f"상세 조회 {len(fetched)}건 · 저장 {saved}건" + ("" if store and saved else " (저장소 없음 — 저장 안 함)"))
    print(f"마감 안 된 공고 {len(open_rows)}건: 등록 공고 {routes[L.REGISTERED]} · 판정 틀 있음 {routes[L.TEMPLATE]} · "
          f"판정 안 하는 사업 {routes[L.UNSUPPORTED]}")
    for n in sorted(open_rows, key=lambda x: (x.route != L.REGISTERED, x.route != L.TEMPLATE, x.window_end or "")):
        if n.route != L.UNSUPPORTED:
            print(f"  [{n.route}] {n.issuer} {n.program} | {n.title[:50]} | {n.window_start or '?'}~{n.window_end or '?'}"
                  + (f" | {n.registered_id}" if n.registered_id else ""))
    if a.json:
        Path(a.json).write_text(json.dumps([n.as_dict() for n in rows], ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
