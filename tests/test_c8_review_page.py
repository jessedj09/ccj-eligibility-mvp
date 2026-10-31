# -*- coding: utf-8 -*-
"""test_c8_review_page.py — 운영자 검토 화면(pages/9_운영자_검토.py, C8): 잠금·대기열·사업별 상태·이용 집계.

운영 DB를 쓰지 않는다 — 가짜 저장소로 화면만 그려 본다(실제 질의는 tests/test_d4_store.py가 CI의 PostgreSQL로).
"""
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import store as S

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

PAGE = str(Path(__file__).resolve().parent.parent / "pages" / "9_운영자_검토.py")
NOW = datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc)


class Fake(S.NullStore):
    available = True

    def __init__(self):
        self.closed, self.demoted = [], {"sh.jeonse"}

    def program_health(self):
        return [{"program": "lh.youth_rental", "compared": 400, "same": 390, "cautious": 10, "danger": 0, "demoted_at": None},
                {"program": "sh.jeonse", "compared": 50, "same": 40, "cautious": 9, "danger": 1, "demoted_at": NOW}]

    def set_demoted(self, program, demoted):
        (self.demoted.add if demoted else self.demoted.discard)(program)
        return True

    def list_jobs(self, kind=None, status=None, limit=100):
        return [dict(id=7, sha256="ab" * 32, kind="review", status="pending", priority=3, attempts=0, error=None,
                     updated_at=NOW, issuer="LH", program="행복주택", title=None, announcement_date=date(2026, 10, 28),
                     first_seen=NOW, has_pdf=True)]

    def latest_snapshot(self, sha):
        return {"status": "unsupported", "template": None, "reason": "이 사업(행복주택)은 아직 자동 판정을 지원하지 않습니다.",
                "held_conditions": {}, "held_fields": [], "unclassified": [[16, "•지역요건행복주택이위치하는과천시에거주하는자"]]}

    def close_job(self, job_id, status, note=""):
        self.closed.append((job_id, status, note))
        return True

    def usage(self, days=14):
        return [{"day": date(2026, 11, 1), "uploads": 3, "judged": 2, "unjudged": 3}]


def test_locked_without_operator_mode():
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert any("운영자 전용" in m.value for m in at.info) and not at.subheader


def test_operator_sees_queue_health_and_usage(monkeypatch):
    fake = Fake()
    monkeypatch.setattr(S, "get_store", lambda: fake)
    at = AppTest.from_file(PAGE, default_timeout=30)
    at.session_state["operator_on"] = True
    at.run()
    assert [h.value for h in at.subheader] == ["사업별 자동 판정", "작업 대기열", "이용 집계(최근 14일)"]
    assert any("행복주택" in e.label for e in at.expander)
    assert any("미분류 문장 p.16" in c.value for c in at.caption)
    at.button(key="resume_sh.jeonse").click().run()
    assert "sh.jeonse" not in fake.demoted
    at.text_input(key="note_7").input("분양 — 다음 단계").run()
    at.button(key="fail_7").click().run()
    assert fake.closed == [(7, "failed", "분양 — 다음 단계")]
