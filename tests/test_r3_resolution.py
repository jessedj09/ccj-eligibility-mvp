# -*- coding: utf-8 -*-
"""test_r3_resolution.py — R-③ 공고 단위 해소(src/clause_resolution.py, 2026-11-15 사용자 승인: 최종안 + 보완 A·B·C).

피드백 세션 완료 기준 5가지를 시험으로 맞춘다:
1. 그 공고를 보는 모든 사용자에게 적용(판정은 사용자와 무관하게 초안 단위로 반영)
2. 되돌릴 수 있음(기록 취소·판정자 단위 취소 → 다시 보류)
3. 사업 멈춤과 함께 동작(멈춘 사업은 해소와 관계없이 판정하지 않음 — api _paused가 먼저)
4. 출처를 남김(source·judge·reason·status)
5. 개인정보 없음(공고 문장과 판정자 이름만)
"""
import dataclasses
import os
import uuid

import clause_resolution as CR
import draft
import grading
import pytest
import source_verify as sv
import store as S
from display_status import ONLY_SENTENCES_TODO, display_result
from rule_engine import HouseholdProfile

SHA, OTHER = "a" * 64, "b" * 64
IN_AREA = (3, "신청자 본인은 해당 지역에 6개월 이상 거주하여야 합니다")       # 자격 영역(p.3) 안 — 필수
OUTSIDE = (12, "계약 체결 시 관리비 예치금을 납부하여 주시기 바랍니다 안내드립니다")   # 영역 밖·제한 표현 없음 — 참고


@pytest.fixture(scope="module")
def base():
    return draft.make_draft(sv.pdf_path("N12").read_bytes(), pages=sv.pdf_pages("N12"), exclude="N12")


@pytest.fixture
def d(base):
    return dataclasses.replace(base, unclassified=[IN_AREA, OUTSIDE])


def youth():
    return HouseholdProfile(profile_id="T", age=25, marital_status="미혼", household_size=1, monthly_income=1, total_assets=1,
                            car_value=0, home_ownership="무주택", house_head_status="세대주", has_subscription_account=True)


class MemStore(S.NullStore):
    """해소 기록만 메모리에 두는 저장소(Store와 같은 의미: 취소된 것은 돌려주지 않음, 같은 사업 기록도 함께)."""

    def __init__(self):
        self.rows = []

    def save_resolution(self, r):
        r = dataclasses.replace(r, id=len(self.rows) + 1)
        self.rows.append(r)
        return r.id

    def resolutions_for(self, sha, template=""):
        return [r for r in self.rows if r.status != CR.REVOKED and (r.sha256 == sha or (template and r.template == template))]

    def set_resolution_status(self, rid, status):
        self.rows = [dataclasses.replace(r, status=status) if r.id == rid else r for r in self.rows]
        return True

    def revoke_judge(self, judge):
        n = sum(1 for r in self.rows if r.judge == judge and r.status != CR.REVOKED)
        self.rows = [dataclasses.replace(r, status=CR.REVOKED) if r.judge == judge else r for r in self.rows]
        return n


def test_sentence_id_matches_parsing_session_definition():
    import sentence_check as SC
    for page, text in (IN_AREA, OUTSIDE, (1, "공백  과\x00제어문자")):
        assert CR.sentence_id(SHA, page, text) == SC.sentence_id(SHA, page, text)


def test_tier_and_initial_status(d):
    assert CR.tier(d.doc, *IN_AREA) == CR.REQUIRED                   # 자격 영역 안
    assert CR.tier(d.doc, *OUTSIDE) == CR.REFERENCE
    assert CR.tier(d.doc, 12, "무주택세대구성원에 한하여 신청할 수 있습니다") == CR.REQUIRED   # 영역 밖이어도 제한 표현
    assert CR.initial_status("operator", CR.NOT_CONDITION, CR.REFERENCE) == CR.ACTIVE
    assert CR.initial_status("operator", CR.NOT_CONDITION, CR.REQUIRED) == CR.PROVISIONAL
    assert CR.initial_status("operator", CR.NEW_CONDITION, CR.REQUIRED) == CR.ACTIVE
    # 묶음 C 시험 전 출처는 초안으로만
    assert CR.initial_status("sentence_check", CR.NOT_CONDITION, CR.REFERENCE) == CR.PROPOSED
    assert CR.initial_status("auto_position", CR.NOT_CONDITION, CR.REFERENCE) == CR.PROPOSED
    with pytest.raises(ValueError):
        CR.initial_status("누군가", CR.NOT_CONDITION, CR.REFERENCE)


def test_resolution_releases_hold_for_every_user_and_is_shown(d):
    """기준 1·4: 판정 한 번이 그 공고의 모든 사용자에게 — 해소된 문장은 확인할 곳에서 빠지고 화면에 출처 표시가 남는다."""
    r, checks = grading.judge(d, youth(), "청년")
    assert r.verdict == "MANUAL_REVIEW" and [c.kind for c in checks] == ["unclassified", "unclassified"]
    rows = [CR.make(d, SHA, *IN_AREA, CR.NOT_CONDITION, "operator", "운영자1", "거주 안내가 아니라 이미 규칙의 조건"),
            CR.make(d, SHA, *OUTSIDE, CR.NOT_CONDITION, "operator", "운영자1", "계약 안내")]
    assert [x.status for x in rows] == [CR.PROVISIONAL, CR.ACTIVE]
    d2 = CR.apply(d, SHA, rows)
    assert d2.unclassified == [] and d.unclassified                  # 원래 초안은 그대로(복사본)
    other = dataclasses.replace(youth(), profile_id="U", age=31)
    for p in (youth(), other):
        r2, c2 = grading.judge(d2, p, "청년")
        assert (r2.verdict, c2) == ("ELIGIBLE", [])
    shown = grading.resolved_for(d2, "청년")
    assert {(x["page"], x["status"]) for x in shown} == {(3, CR.PROVISIONAL), (12, CR.ACTIVE)}
    assert any("교차 확인 중" in x["label"] for x in shown)
    # 개인정보 없음(기준 5): 기록 필드는 공고 문장·판정자·사유뿐
    assert set(dataclasses.asdict(rows[0])) == {"sha256", "sentence_id", "page", "sentence", "verdict", "tier", "source", "judge",
                                                "reason", "status", "template", "normalize_version", "id", "created_at"}


def test_new_condition_and_proposed_keep_the_hold(d):
    """애매하면 보류 유지 — '새 조건' 판정이 하나라도 있으면 빼지 않는다. 시험 전 출처(초안)는 판정에 쓰지 않는다."""
    ok = CR.make(d, SHA, *OUTSIDE, CR.NOT_CONDITION, "operator", "운영자1")
    new = CR.make(d, SHA, *OUTSIDE, CR.NEW_CONDITION, "operator", "운영자2")
    assert CR.apply(d, SHA, [ok, new]).unclassified == d.unclassified
    proposed = CR.make(d, SHA, *OUTSIDE, CR.NOT_CONDITION, "sentence_check", "gemma4:e2b")
    assert proposed.status == CR.PROPOSED and CR.apply(d, SHA, [proposed]) is d
    revoked = dataclasses.replace(ok, status=CR.REVOKED)
    assert CR.apply(d, SHA, [revoked]) is d


def test_sentence_dictionary_applies_within_the_same_program_only(d):
    """같은 사업(판정 틀)의 다른 공고에서 해소된 같은 문장은 새 공고에도 바로 — 다른 사업이면 적용하지 않는다."""
    there = CR.make(d, OTHER, 7, OUTSIDE[1] + " ", CR.NOT_CONDITION, "operator", "운영자1")   # 쪽·공백이 달라도 같은 문장
    d2 = CR.apply(d, SHA, [there])
    assert d2.unclassified == [IN_AREA] and d2.resolved[0].via == "dictionary" and "다른 공고" in d2.resolved[0].label
    elsewhere = dataclasses.replace(there, template="sh.newlywed")
    assert CR.apply(d, SHA, [elsewhere]) is d
    blocked = dataclasses.replace(there, verdict=CR.NEW_CONDITION)    # 같은 사업 어디서든 '새 조건'이면 빼지 않음
    assert CR.apply(d, SHA, [there, blocked]).unclassified == d.unclassified


def test_cross_check_promotes_or_revokes_and_judge_can_be_rolled_back(d):
    """기준 2: 잠정(필수) 판정은 다른 판정자가 뒤에서 교차 확인 — 같으면 확정, '새 조건'이면 취소. 판정자 단위로 되돌린다."""
    s = MemStore()
    first = CR.record(s, d, SHA, *IN_AREA, CR.NOT_CONDITION, "operator", "세션A")
    assert first.status == CR.PROVISIONAL
    assert CR.apply(d, SHA, s.resolutions_for(SHA, d.template)).unclassified == [OUTSIDE]
    same_judge = CR.record(s, d, SHA, *IN_AREA, CR.NOT_CONDITION, "operator", "세션A")      # 같은 판정자는 교차 확인 아님
    assert same_judge.status == CR.PROVISIONAL
    agree = CR.record(s, d, SHA, *IN_AREA, CR.NOT_CONDITION, "operator", "세션B")
    assert agree.status == CR.ACTIVE and s.rows[0].status == CR.ACTIVE is not None
    # 다른 문장: 교차 확인이 '새 조건' → 잠정 취소, 보류 유지
    t = CR.record(s, d, SHA, 3, "만 19세 이상 39세 이하인 사람이어야 합니다 추가로", CR.NOT_CONDITION, "operator", "세션A")
    CR.record(s, d, SHA, 3, "만 19세 이상 39세 이하인 사람이어야 합니다 추가로", CR.NEW_CONDITION, "operator", "세션B")
    assert next(r for r in s.rows if r.id == t.id).status == CR.REVOKED
    # 판정자 단위 되돌리기 — 세션B를 되돌리면 세션B가 확정시킨 것은 남지만(세션A 기록이 확정됨) 세션B 기록은 취소
    assert s.revoke_judge("세션A") >= 1
    left = s.resolutions_for(SHA, d.template)
    assert all(r.judge == "세션B" for r in left)
    s.revoke_judge("세션B")
    assert CR.apply(d, SHA, s.resolutions_for(SHA, d.template)) is d        # 모두 되돌림 → 다시 보류


def test_waiting_sentence_shows_everything_else_is_met(d):
    """보완 B: 확인할 곳이 규칙에 없는 문장뿐이면 '이 문장 말고는 모두 충족' — 보류 조건이 섞이면 기존 문구."""
    r, checks = grading.judge(d, youth(), "청년")
    shown = display_result(r.verdict, r.review_reasons, len(checks), {c.kind for c in checks})
    assert shown.todo == ONLY_SENTENCES_TODO and shown.title.endswith("원문 확인 2건")
    mixed = display_result("MANUAL_REVIEW", None, 2, {"held", "unclassified"})
    assert mixed.todo != ONLY_SENTENCES_TODO


def test_queue_orders_by_impact_open_status_and_tier(d, base):
    items = CR.queue([(OTHER, "마감 공고", d, False), (SHA, "접수 중 공고", d, True)])
    assert [q.priority for q in items] == sorted((q.priority for q in items), reverse=True)
    assert [(q.title, q.tier) for q in items] == [("접수 중 공고", CR.REQUIRED), ("접수 중 공고", CR.REFERENCE),
                                                  ("마감 공고", CR.REQUIRED), ("마감 공고", CR.REFERENCE)]
    assert all(len(q.layers) == 3 for q in items)                    # 영역 밖 문장은 모든 계층, p.3은 세 계층 범위 안
    narrow = dataclasses.replace(d, doc={**d.doc, "layers": {k: v for k, v in d.doc["layers"].items() if k == "청년"}})
    one = CR.queue([(SHA, "좁은 공고", narrow, True)])
    assert one and all(q.layers == ("청년",) or len(q.layers) <= 3 for q in one)
    resolved = CR.apply(d, OTHER, [CR.make(d, OTHER, *IN_AREA, CR.NOT_CONDITION, "operator", "x")])
    assert IN_AREA[1] not in [q.sentence for q in CR.queue([(OTHER, "t", resolved, True)])]


def test_import_proposals_are_proposed_and_check_ids(d):
    item = {"sha256": SHA, "sentence_id": CR.sentence_id(SHA, *OUTSIDE), "page": OUTSIDE[0], "sentence": OUTSIDE[1],
            "tier": "참고", "draft_verdict": "조건 아님", "reason": "계약 안내", "template": d.template}
    rows = CR.import_proposals([item], judge="파싱 세션")
    assert rows[0].status == CR.PROPOSED and rows[0].tier == CR.REFERENCE and rows[0].verdict == CR.NOT_CONDITION
    assert CR.apply(d, SHA, rows) is d
    assert CR.import_proposals([dict(item, draft_verdict=None, context="…")], judge="x") == []   # 판정 없는 후보는 건너뜀
    with pytest.raises(ValueError):
        CR.import_proposals([dict(item, sentence_id=SHA[:16] + ":99:000000000000")], judge="x")


def test_api_applies_resolutions_and_paused_program_still_wins(d, monkeypatch):
    """기준 3: 해소가 있어도 멈춘 사업은 판정하지 않는다(_paused가 먼저). DB가 없으면 해소 없이 그대로."""
    pytest.importorskip("fastapi")
    import sys
    from pathlib import Path
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    import api.main as api
    s = MemStore()
    s.save_resolution(CR.make(d, SHA, *OUTSIDE, CR.NOT_CONDITION, "operator", "운영자1"))
    monkeypatch.setattr(api, "get_store", lambda: s)
    api._resolutions.clear()
    assert api._with_resolutions(d, SHA).unclassified == [IN_AREA]
    monkeypatch.setattr(s, "demoted_programs", lambda: frozenset({d.template}))
    assert api._paused(api._with_resolutions(d, SHA), s)
    api._resolutions.clear()
    monkeypatch.setattr(api, "get_store", lambda: S.NullStore())
    assert api._with_resolutions(d, SHA) is d
    api._resolutions.clear()


TEST_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


@pytest.mark.skipif(not TEST_URL, reason="TEST_DATABASE_URL 없음 — 실제 DB 시험은 CI(postgres 서비스)에서")
def test_db_resolutions_round_trip(d):
    schema = "t_" + uuid.uuid4().hex[:10]
    s = S.Store(TEST_URL, schema=schema)
    try:
        assert s.migrate()
        a = CR.record(s, d, SHA, *IN_AREA, CR.NOT_CONDITION, "operator", "세션A")
        CR.record(s, d, OTHER, *OUTSIDE, CR.NOT_CONDITION, "operator", "세션A")
        got = s.resolutions_for(SHA, d.template)
        assert {(r.sha256, r.status) for r in got} == {(SHA, CR.PROVISIONAL), (OTHER, CR.ACTIVE)}
        assert CR.apply(d, SHA, got).unclassified == []
        CR.record(s, d, SHA, *IN_AREA, CR.NOT_CONDITION, "operator", "세션B")
        assert next(r for r in s.resolutions_for(SHA) if r.id == a.id).status == CR.ACTIVE
        assert s.revoke_judge("세션A") == 2 and len(s.list_resolutions(status=CR.REVOKED)) == 2
        assert s.migrate()
    finally:
        s._run(lambda c: c.execute(f'DROP SCHEMA "{schema}" CASCADE'))
        s.close()


# ------------------------------------------------------------------ 피드백 세션 권고(2026-11-15): 세션 판정 시험 전 제한·잠정 유효 기간·문장 사전 범위
def test_session_judgment_before_bundle_e_needs_a_second_judge_for_required(d):
    """Claude 세션 판정은 묶음 E 통과 전: 참고 문장은 바로 확정, 필수 문장은 초안 — 다른 판정자가 같은 판단이면 둘 다 확정."""
    assert not CR.SESSION_TESTED
    assert CR.initial_status("session", CR.NOT_CONDITION, CR.REFERENCE) == CR.ACTIVE
    assert CR.initial_status("session", CR.NOT_CONDITION, CR.REQUIRED) == CR.PROPOSED
    s = MemStore()
    a = CR.record(s, d, SHA, *IN_AREA, CR.NOT_CONDITION, "session", "세션A")
    assert a.status == CR.PROPOSED and CR.apply(d, SHA, s.resolutions_for(SHA, d.template)) is d
    b = CR.record(s, d, SHA, *IN_AREA, CR.NOT_CONDITION, "session", "세션B")
    assert b.status == CR.ACTIVE and next(r for r in s.rows if r.id == a.id).status == CR.ACTIVE
    assert CR.apply(d, SHA, s.resolutions_for(SHA, d.template)).unclassified == [OUTSIDE]
    # 두 번째 판정자가 '새 조건'이면 초안을 취소하고 보류 유지
    s2 = MemStore()
    a2 = CR.record(s2, d, SHA, *IN_AREA, CR.NOT_CONDITION, "session", "세션A")
    CR.record(s2, d, SHA, *IN_AREA, CR.NEW_CONDITION, "session", "세션B")
    assert next(r for r in s2.rows if r.id == a2.id).status == CR.REVOKED
    assert CR.apply(d, SHA, s2.resolutions_for(SHA, d.template)) is d
    # 시험 전 LLM 출처의 판정은 세션 초안을 확정시키지 못한다
    s3 = MemStore()
    a3 = CR.record(s3, d, SHA, *IN_AREA, CR.NOT_CONDITION, "session", "세션A")
    CR.record(s3, d, SHA, *IN_AREA, CR.NOT_CONDITION, "sentence_check", "gemma4:e2b")
    assert next(r for r in s3.rows if r.id == a3.id).status == CR.PROPOSED


def test_provisional_without_cross_check_goes_first_then_expires(d):
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    r = CR.make(d, SHA, *IN_AREA, CR.NOT_CONDITION, "operator", "운영자1")
    fresh = dataclasses.replace(r, id=1, created_at=(now - timedelta(days=2)).isoformat())
    late = dataclasses.replace(r, id=2, created_at=(now - timedelta(days=CR.PROVISIONAL_DUE_DAYS + 1)).isoformat())
    old = dataclasses.replace(r, id=3, created_at=(now - timedelta(days=CR.PROVISIONAL_TTL_DAYS + 1)).isoformat())
    assert [x.id for x in CR.due([fresh, late, old], now)] == [3, 2]          # 오래된 것부터 대기열 맨 앞
    assert CR.apply(d, SHA, [late], now).unclassified == [OUTSIDE]            # 7~14일: 아직 반영
    assert CR.apply(d, SHA, [old], now) is d                                  # 14일 넘김: 다시 보류
    active_old = dataclasses.replace(old, status=CR.ACTIVE)
    assert not CR.expired(active_old, now)                                    # 확정 기록은 만료 없음


def test_dictionary_moves_only_active_and_skips_deictic_sentences(d):
    there = CR.make(d, OTHER, 7, OUTSIDE[1], CR.NOT_CONDITION, "operator", "운영자1")
    assert CR.apply(d, SHA, [dataclasses.replace(there, status=CR.PROVISIONAL)]) is d   # 잠정은 다른 공고로 옮기지 않음
    pointing = "위 요건에 해당하는 분은 신청할 수 없습니다"
    dd = dataclasses.replace(d, unclassified=[(12, pointing)])
    there2 = dataclasses.replace(there, sentence=pointing, sentence_id=CR.sentence_id(OTHER, 7, pointing))
    assert CR.apply(dd, SHA, [there2]) is dd                                  # 지시어 문장은 사전으로 옮기지 않음
    direct = CR.make(dd, SHA, 12, pointing, CR.NOT_CONDITION, "operator", "운영자1")
    assert CR.apply(dd, SHA, [direct]).unclassified == []                     # 그 공고의 직접 판정은 그대로 반영
    for t in ("본 공고문에 따라", "아래 표의 기준", "다음 각 호"):
        assert CR.DEICTIC.search(t)
    for t in ("위반 시 계약 해지", "단위 면적", "위치는 단지 안내도", "해당없음"):
        assert not CR.DEICTIC.search(t)
