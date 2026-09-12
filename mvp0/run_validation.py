# -*- coding: utf-8 -*-
"""run_validation.py — Rule Engine 출력이 워크북 match_matrix(수기 정답지)와 일치하는지 검증."""

from rule_engine import evaluate
from notices_data import ALL_NOTICES
from profiles_data import PROFILES, EXPECTED

def main():
    total, ok = 0, 0
    print(f"{'profile':<6}{'layer':<8}{'notice':<6}{'engine':<14}{'expected':<14}{'match':<6}  근거")
    print("-" * 100)
    for profile, layer in PROFILES:
        for notice_id, notice in ALL_NOTICES.items():
            result = evaluate(profile, notice, layer)
            expected = EXPECTED[profile.profile_id][notice_id]
            is_match = (result.verdict == expected)
            total += 1
            ok += int(is_match)
            reason = ""
            if result.verdict == "INELIGIBLE":
                reason = f"failed={result.failed}"
            elif result.verdict == "NEEDS_INFO":
                reason = f"unknown={result.unknown}"
            elif result.verdict == "ELIGIBLE":
                reason = f"score={result.score}"
            mark = "OK" if is_match else "★MISMATCH"
            print(f"{profile.profile_id:<6}{layer:<8}{notice_id:<6}{result.verdict:<14}"
                  f"{expected:<14}{mark:<10}{reason}")
    print("-" * 100)
    print(f"총 {total}건 중 {ok}건 일치 ({ok/total*100:.1f}%)")

if __name__ == "__main__":
    main()
