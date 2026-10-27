# -*- coding: utf-8 -*-
"""test_b2_compare.py — B2: 등록 전에 얼린 초안 스냅샷과 등록 후 판정 비교(tools/draft_compare.py).

- 스냅샷은 운영자 미리보기와 같은 판정을 재현한다(보류 조건·새 제한 문구로 낮춤까지).
- 등록 공고를 그대로 초안으로 만들면 위험 0·같음 100%(도구 점검), 초안에서 조건을 빼면 '틀린 지원 가능'을 잡고,
  새 제한 문구가 있으면 '초안이 더 조심'으로 센다. 판정할 수 없는 초안은 '초안 판정 없음'.
- 저장: 이미 있는 스냅샷은 덮어쓰지 않는다.
"""
import copy
import json
import sys
from pathlib import Path

import draft
import golden_cases as gc
import pytest
import source_verify as sv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import draft_compare as dc  # noqa: E402
import notice_intake as ni  # noqa: E402

LIMIT = 400


@pytest.fixture(scope="module")
def n12_snapshot():
    path = sv.pdf_path("N12")
    d = draft.make_draft(path.read_bytes(), only=None, pages=sv.pdf_pages("N12"))
    return draft.to_snapshot(d, sv.notice_doc("N12")["source"]["sha256"], source=path.name, created="2026-10-28")


def test_snapshot_round_trip_reproduces_operator_verdicts(n12_snapshot):
    snap = json.loads(json.dumps(n12_snapshot, ensure_ascii=False))     # 파일로 썼다 읽은 것과 같게
    d = draft.make_draft(sv.pdf_path("N12").read_bytes(), pages=sv.pdf_pages("N12"))
    back = draft.from_snapshot(snap)
    for _, layer, p in list(gc.cases(only=[("N12", "청년")]))[:200]:
        assert draft.judge(back, p, layer)[0] == draft.judge(d, p, layer)[0]
    with pytest.raises(ValueError):
        draft.from_snapshot(dict(snap, format="other"))


def test_registered_notice_as_draft_has_no_danger(n12_snapshot):
    res = dc.compare(n12_snapshot, limit=LIMIT)
    assert res["nid"] == "N12" and set(res["counts"]) == {layer for n, layer in gc.GROUPS if n == "N12"}
    assert dc.danger_count(res) == 0
    assert all(c[dc.SAME] == LIMIT and c["exact"] == LIMIT for c in res["counts"].values())
    assert "✅ 위험 0건" in dc.to_markdown(res)


def test_missing_condition_in_draft_is_caught_as_wrong_eligible(n12_snapshot):
    snap = copy.deepcopy(n12_snapshot)
    conds = snap["doc"]["layers"]["청년"]["conditions"]
    dropped = next(c for c in conds if c["id"].endswith("-age"))
    conds.remove(dropped)                                            # 초안이 나이 조건을 놓친 경우
    res = dc.compare(snap, limit=LIMIT)
    assert res["counts"]["청년"][dc.WRONG_ELIGIBLE] > 0 and dc.danger_count(res) > 0
    ex = res["examples"]["청년"][0]
    assert ex["draft"] == "ELIGIBLE" and dropped["id"].split("-", 1)[1] in ex["registered_failed"]
    md = dc.to_markdown(res)
    assert "❌ 위험" in md and "위험 사례" in md


def test_new_restriction_counts_as_cautious_not_danger(n12_snapshot):
    snap = dict(n12_snapshot, restrictions=[[3, "이번공고에서는모집하지않음"]])
    res = dc.compare(snap, limit=LIMIT)
    c = res["counts"]["청년"]
    assert c[dc.CAUTIOUS] > 0 and dc.danger_count(res) == 0
    assert "새 제한 문구 p.3" in dc.to_markdown(res)


def test_blocked_draft_is_not_judged():
    path = sv.pdf_path("N10")
    d = draft.make_draft(path.read_bytes(), only=None, pages=sv.pdf_pages("N10"))
    snap = draft.to_snapshot(d, sv.notice_doc("N10")["source"]["sha256"])
    res = dc.compare(snap, limit=50)
    assert d.status == draft.BLOCKED and dc.danger_count(res) == 0
    assert all(c[dc.NOT_JUDGED] == 50 for c in res["counts"].values())


def test_classify_uses_screen_groups():
    assert dc.classify("NEEDS_INFO", "MANUAL_REVIEW") == dc.SAME            # 둘 다 '보류'
    assert dc.classify("MANUAL_REVIEW", "ELIGIBLE") == dc.CAUTIOUS
    assert dc.classify("ELIGIBLE", "MANUAL_REVIEW") == dc.WRONG_ELIGIBLE
    assert dc.classify("INELIGIBLE", "ELIGIBLE") == dc.WRONG_OTHER
    assert dc.classify("NOT_OFFERED", "INELIGIBLE") == dc.WRONG_OTHER
    assert dc.classify(None, "ELIGIBLE") == dc.NOT_JUDGED


def test_unregistered_snapshot_is_refused(n12_snapshot):
    with pytest.raises(SystemExit):
        dc.compare(dict(n12_snapshot, sha256="0" * 64))


def test_save_snapshot_never_overwrites(tmp_path):
    r = ni.report(sv.pdf_path("N17"), pages=sv.pdf_pages("N17"), with_draft=True)
    out = tmp_path / "x.draft.json"
    assert ni.save_snapshot(r, str(out)) == out
    first = out.read_text(encoding="utf-8")
    assert json.loads(first)["format"] == draft.SNAPSHOT_FORMAT
    assert ni.save_snapshot(r, str(out)) is None and out.read_text(encoding="utf-8") == first
