# -*- coding: utf-8 -*-
"""test_regression.py — 워크북 match_matrix(수기 정답지) 36건과 Rule Engine 결과가
항상 일치하는지 자동 확인. 앞으로 규칙을 고칠 때마다 `pytest -q`만 실행하면 됨."""

import pytest
from rule_engine import evaluate
from notices_data import ALL_NOTICES
from profiles_data import PROFILES, EXPECTED

CASES = [
    (profile, layer, notice_id)
    for profile, layer in PROFILES
    for notice_id in ALL_NOTICES
]


@pytest.mark.parametrize(
    "profile,layer,notice_id",
    CASES,
    ids=[f"{p.profile_id}-{layer}-{nid}" for p, layer, nid in CASES],
)
def test_matches_manual_match_matrix(profile, layer, notice_id):
    notice = ALL_NOTICES[notice_id]
    result = evaluate(profile, notice, layer)
    expected = EXPECTED[profile.profile_id][notice_id]
    assert result.verdict == expected, (
        f"{profile.profile_id} on {notice_id}: got {result.verdict}, expected {expected} "
        f"(failed={result.failed}, unknown={result.unknown})"
    )
