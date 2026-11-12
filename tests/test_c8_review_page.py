# -*- coding: utf-8 -*-
"""test_c8_review_page.py — 운영자 검토 화면(ops/review.py — 운영자 화면 첫 화면, C8): 잠금·대기열·사업별 상태·이용 집계.

운영 DB를 쓰지 않는다 — 가짜 저장소로 화면만 그려 본다(실제 질의는 tests/test_d4_store.py가 CI의 PostgreSQL로).
"""
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import store as S

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

PAGE = str(Path(__file__).resolve().parent.parent / "ops" / "review.py")
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

    def live_notices(self, open_only=True, limit=500):
        row = dict(source="lh", external_id="2015122300021011", title="원주시지역 영구임대주택 예비입주자 모집", issuer="LH",
                   kind="영구임대", region="강원특별자치도", announced=date(2026, 11, 9), window_start=date(2026, 11, 25),
                   window_end=date(2026, 11, 27), status="공고중", url="https://apply.lh.or.kr/", program="영구임대주택",
                   template="lh.permanent_rental", registered_id=None, route="template", first_seen=NOW, last_seen=NOW)
        return [row, dict(row, external_id="Y", title="일반 매입임대", template=None, route="unsupported")]


def test_locked_without_operator_mode():
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert any("운영자 전용" in m.value for m in at.info) and not at.subheader


def test_operator_sees_queue_health_and_usage(monkeypatch):
    fake = Fake()
    monkeypatch.setattr(S, "get_store", lambda: fake)
    at = AppTest.from_file(PAGE, default_timeout=30)
    at.session_state["operator_on"] = True
    at.run()
    assert [h.value for h in at.subheader] == ["사업별 자동 판정", "작업 대기열", "지금 모집 중인 공고", "이용 집계(최근 14일)"]
    assert any("마감 안 된 공고 2건 중 1건" in c.value for c in at.caption)      # 기본은 판정 틀 있음·등록 공고만
    assert any("행복주택" in e.label for e in at.expander)
    assert any("미분류 문장 p.16" in c.value for c in at.caption)
    at.button(key="resume_sh.jeonse").click().run()
    assert "sh.jeonse" not in fake.demoted
    at.text_input(key="note_7").input("분양 — 다음 단계").run()
    at.button(key="fail_7").click().run()
    assert fake.closed == [(7, "failed", "분양 — 다음 단계")]


def test_locked_screen_shows_password_box_without_query():
    """운영자 전용 화면이라 주소에 ?operator가 없어도 비밀번호 칸을 바로 보인다(2026-11-12 정리)."""
    at = AppTest.from_file(PAGE, default_timeout=30)
    at.run()
    assert any("운영자 전용" in m.value for m in at.info)


def test_signed_in_operator_email_unlocks_without_password(monkeypatch):
    """Streamlit Cloud 비공개 앱: 로그인 이메일이 operator_emails에 있으면 비밀번호 없이 운영자 모드(2026-11-12)."""
    import operator_mode as O
    fake = Fake()
    monkeypatch.setattr(S, "get_store", lambda: fake)
    monkeypatch.setenv(O.EMAILS_ENV, "Ops@Example.org, other@example.org")
    monkeypatch.setattr(O, "signed_in_email", lambda: "ops@example.org")
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert at.subheader and at.subheader[0].value == "사업별 자동 판정"
    monkeypatch.setattr(O, "signed_in_email", lambda: "stranger@example.org")
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert any("운영자 전용" in m.value for m in at.info) and not at.subheader


def test_email_rules():
    import operator_mode as O
    assert O.email_allowed("A@x.org", frozenset({"a@x.org"})) and not O.email_allowed(None, frozenset({"a@x.org"}))
    assert not O.email_allowed("b@x.org", frozenset())


def test_app_entry_opens_review_first():
    """app.py(Streamlit Cloud 시작 파일)는 메뉴만 — 첫 화면은 운영자 검토, 옛 '내 조건으로 공고 찾기'는 없다."""
    root = Path(__file__).resolve().parent.parent
    at = AppTest.from_file(str(root / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert any("운영자 전용" in m.value for m in at.info)          # 잠긴 운영자 검토
    assert not (root / "pages").exists() or not any((root / "pages").glob("*.py"))
