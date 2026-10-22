# -*- coding: utf-8 -*-
"""test_d2_schedule.py — 공고별 청약 접수기간과 접수 상태(D2). 원문 대조는 test_source_verify(verify_all)에 포함된다."""

import json
from datetime import datetime, timedelta

import pytest
import schedule
from rule_data import load_notice, notice_ids
from schedule import CLOSED, KST, OPEN, UNKNOWN, UPCOMING, ScheduleError, load_schedules, status


def kst(*a):
    return datetime(*a, tzinfo=KST)


def test_every_notice_has_a_schedule_after_its_announcement():
    s = load_schedules()
    assert set(s) == set(notice_ids())
    for nid, sched in s.items():
        ann = load_notice(nid).announcement_date
        assert sched.windows[0].start.date() > ann, nid           # 접수는 공고일 다음부터
        assert sched.windows[-1].end.date() - ann < timedelta(days=60), nid


@pytest.mark.parametrize("at,code", [
    (kst(2026, 10, 12, 9, 59), UPCOMING),
    (kst(2026, 10, 12, 10, 0), OPEN),       # 시작 시각 포함
    (kst(2026, 10, 14, 16, 0), OPEN),       # 마감 시각 포함
    (kst(2026, 10, 14, 16, 1), CLOSED),
])
def test_status_boundaries_n4(at, code):
    assert status("N4", at).code == code


def test_multi_window_notice_reports_next_rank():
    # 49차 장기전세: 1순위·우선공급 01.08~09, 2순위 01.12, 3·4순위 01.19
    s = status("N25", kst(2026, 1, 10, 12))
    assert s.code == UPCOMING and s.window.label == "2순위" and s.applicable
    s = status("N25", kst(2026, 1, 12, 12))
    assert s.code == OPEN and s.window.label == "2순위"
    s = status("N25", kst(2026, 1, 20))
    assert s.code == CLOSED and s.window.label == "3·4순위" and not s.applicable
    assert "1순위" in status("N25", kst(2026, 1, 1)).text


def test_all_sample_notices_closed_on_2026_10_22():
    st = schedule.statuses(notice_ids(), kst(2026, 10, 22, 12))
    assert {s.code for s in st.values()} == {CLOSED}


def test_open_on_2026_10_14_noon():
    st = schedule.statuses(notice_ids(), kst(2026, 10, 14, 12))
    assert {n for n, s in st.items() if s.code == OPEN} == {"N4", "N8", "N17", "N18", "N19"}


def test_naive_datetime_is_taken_as_kst_and_unknown_notice():
    assert status("N4", datetime(2026, 10, 12, 10, 0)).code == OPEN
    assert status("N999").code == UNKNOWN and not status("N999").applicable


def test_invalid_schedule_rejected(tmp_path, monkeypatch):
    bad = {"notices": {"N1": {"windows": [
        {"label": "a", "start": "2026-08-12T17:00", "end": "2026-08-10T10:00", "source": {"page": 1, "quote": ["x"]}}]}}}
    p = tmp_path / "s.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(schedule, "SCHEDULES_PATH", p)
    schedule.load_schedules.cache_clear()
    try:
        with pytest.raises(ScheduleError):
            schedule.load_schedules()
    finally:
        schedule.load_schedules.cache_clear()


def test_quote_date_mismatch_is_caught():
    """데이터의 날짜를 하루 틀리게 바꾸면 원문 대조가 잡는다(변이)."""
    import source_verify
    real = json.loads((source_verify.RULES / "schedules.json").read_text(encoding="utf-8"))
    real["notices"]["N4"]["windows"][0]["end"] = "2026-10-15T16:00"
    rep = source_verify.verify_schedules(real)
    assert any("N4" in p and "end" in p for p in rep.problems), rep.problems
