# -*- coding: utf-8 -*-
"""사업별 자동 판정 상태(A3) — 공유 저장소의 program_health를 보고, 운영자가 사업의 자동 판정을 멈추거나 다시 켠다.

    python tools/program_health.py                    # 사업별 비교 건수·같음·주의·위험·멈춤 여부
    python tools/program_health.py --pause sh.jeonse  # 그 사업의 자동 판정을 멈춤(업로드하면 '정확도 점검 중' 안내)
    python tools/program_health.py --resume sh.jeonse # 다시 켬 — 위험의 원인을 고치고 다시 비교한 뒤에만

사업 키는 초안 템플릿 ID(src/draft.py PASSING). 비교 결과는 tools/draft_compare.py --record가 더하고, 위험이 1건이라도
나오면 그 사업을 저절로 멈춘다. 전체 공개 스위치(CCJ_AUTO_JUDGE_PUBLIC)와 별개로 사업 단위로 막는다.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import draft  # noqa: E402
from store import NullStore, get_store  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--pause", metavar="사업", help="자동 판정을 멈출 사업(템플릿 ID)")
    g.add_argument("--resume", metavar="사업", help="자동 판정을 다시 켤 사업(템플릿 ID)")
    a = ap.parse_args(argv)
    store = get_store()
    if type(store) is NullStore:
        print("공유 저장소(DATABASE_URL)에 접속할 수 없습니다.")
        return 2
    target = a.pause or a.resume
    if target:
        if target not in draft.PASSING:
            print(f"알 수 없는 사업: {target} (가능: {', '.join(draft.PASSING)})")
            return 2
        store.set_demoted(target, bool(a.pause))
        print(f"{target}: {'멈춤' if a.pause else '다시 켬'}")
    rows = {r["program"]: r for r in store.program_health()}
    print(f"{'사업':<20} {'비교':>6} {'같음':>6} {'주의':>6} {'위험':>6}  상태")
    for t in draft.PASSING:
        r = rows.get(t, {})
        state = f"멈춤({r['demoted_at']:%Y-%m-%d %H:%M})" if r.get("demoted_at") else "판정 중"
        print(f"{t:<20} {r.get('compared', 0):>6} {r.get('same', 0):>6} {r.get('cautious', 0):>6} {r.get('danger', 0):>6}  {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
