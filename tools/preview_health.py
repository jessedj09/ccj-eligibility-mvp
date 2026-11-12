# -*- coding: utf-8 -*-
"""예비 판정 감시 현황·재개(흥신소 묶음 A, 2026-11-13).

    python tools/preview_health.py                    # 판정 틀별: 비교한 공고·입력 수·놓침·가능성 있음 맞음/헛걸음, 멈춘 틀
    python tools/preview_health.py --resume lh.national_rental   # 놓침 원인을 확인·고친 뒤 그 틀의 예비 '어려움'을 다시 켠다

수집 예약 작업(tools/collect_live_notices.py)이 공고문이 분석된 수집 공고마다 예비 ↔ 확정을 비교해 기록한다(src/coverage.py).
놓침(예비 '어려움' → 확정 '지원 가능')이 1건이라도 있으면 그 틀은 흥신소에서 '어려움' 대신 '실제 공고문 확인필요'로 보인다.
공유 저장소(DATABASE_URL)가 필요하다 — 개인정보 없음.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from store import NullStore, get_store  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--resume", help="이 판정 틀의 예비 '어려움'을 다시 켠다")
    a = ap.parse_args(argv)
    store = get_store()
    if type(store) is NullStore or not getattr(store, "available", False):
        print("공유 저장소(DATABASE_URL)에 접속할 수 없습니다.")
        return 2
    if a.resume:
        ok = store.resume_preview(a.resume)
        print(f"{a.resume}: 예비 '어려움' 다시 켬" if ok else f"{a.resume}: 실패")
        return 0 if ok else 1
    rows = store.preview_health()
    stopped = store.preview_stopped()
    if not rows:
        print("아직 비교한 공고가 없습니다(공고문이 분석된 수집 공고가 생기면 수집 작업이 비교한다).")
    for r in rows:
        mark = "  ← 멈춤" if r["template"] in stopped else ""
        print(f"{r['template']}: 공고 {r['notices']} · 입력 {r['compared']} · 놓침 {r['missed']} · 가능성 있음 맞음 {r['likely_ok']}"
              f"/헛걸음 {r['likely_wrong']} · 마지막 {r['last_checked']:%Y-%m-%d %H:%M}{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
