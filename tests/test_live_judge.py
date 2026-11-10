# -*- coding: utf-8 -*-
"""예비 판정(src/live_judge.py) — 흥신소 주 흐름 ②-1, docs/12 '2단계 재설계'."""
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tools"), str(ROOT / "tests")]

import eval_preview as EP  # noqa: E402
import golden_cases as gc  # noqa: E402
import live_judge as J  # noqa: E402
from rule_data import load_notice  # noqa: E402
from rule_engine import EvaluationResult, evaluate  # noqa: E402


def _reg(nid, t="lh.x", issuer="LH", program="P", d=date(2026, 1, 1)):
    return J.Registered(nid, t, issuer, program, d)


def test_pick_representative_prefers_same_program_and_nearest_earlier():
    c = [_reg("A", d=date(2026, 3, 1)), _reg("B", d=date(2026, 6, 1)), _reg("C", d=date(2026, 9, 1)),
         _reg("D", program="Q", d=date(2026, 8, 1)), _reg("E", issuer="SH", d=date(2026, 8, 1)), _reg("F", t="lh.y", d=date(2026, 8, 1))]
    assert J.pick_representative("lh.x", "LH", "P", date(2026, 8, 15), c).notice_id == "B"
    assert J.pick_representative("lh.x", "LH", "Q", date(2026, 8, 15), c).notice_id == "D"
    # 앞선 공고가 없으면 가장 최근 공고, 사업 이름이 없으면 같은 틀 전체에서
    assert J.pick_representative("lh.x", "LH", "P", date(2026, 1, 1), c).notice_id == "C"
    assert J.pick_representative("lh.x", "LH", "모름", date(2026, 8, 15), c).notice_id == "D"
    assert J.pick_representative("lh.z", "LH", "P", None, c) is None


def _result(*failed):
    return EvaluationResult("p", "N", "L", "INELIGIBLE", None, [], list(failed), [], [])


def test_unlikely_only_for_common_same_conditions():
    conds = {"a": ("home_ownership", "c1", False), "b": ("residence_area", "c2", False), "g": ("유형", "c3", True),
             "m": ("total_assets", "c4", False), "k": ("children_birth_dates", "c5", False)}
    common = {"home_ownership": {"c1"}, "residence_area": {"c2"}, "total_assets": {"c4", "c9"}, "children_birth_dates": {"c5", "c6"}}
    assert J._judge_failed(_result("a"), conds, common)[1:] == (True, False)
    assert J._judge_failed(_result("a", "g"), conds, common)[1] is True        # 묶음 머리는 보지 않음
    assert J._judge_failed(_result("b"), conds, common)[1] is False            # 거주 지역 — 공고마다 다름
    assert J._judge_failed(_result("a"), conds, {})[1] is False                 # 같은 사업 모든 공고에 있는 조건이 아님
    assert J._judge_failed(_result("k"), conds, common)[1] is False             # 공고마다 식이 다름(3명 → 2명)
    assert J._judge_failed(_result("m"), conds, common)[1:] == (True, True)    # 금액 — 여유 폭 검사로 넘김
    assert J._judge_failed(_result("zz"), conds, common)[1] is False            # 모르는 조건


def _youth_profile():
    for _n, _l, p in gc.cases(only=[("N12", "청년")]):
        if evaluate(p, load_notice("N12"), "청년").verdict == "ELIGIBLE":
            return p
    raise AssertionError("지원 가능 골든 입력 없음")


def _youth_index():
    return J.CommonIndex([_reg("N11", "lh.youth_rental"), _reg("N12", "lh.youth_rental")])


def test_preview_likely_unlikely_and_stale():
    rep, index, p = load_notice("N11"), _youth_index(), _youth_profile()
    ok = J.preview_layer(p, "청년", rep, "lh.youth_rental", index, date(2026, 10, 1))
    assert ok.outcome in (J.LIKELY, J.CHECK)
    owner = replace(p, home_ownership="주택보유")
    out = J.preview_layer(owner, "청년", rep, "lh.youth_rental", index, date(2026, 10, 1))
    assert out.outcome == J.UNLIKELY and "home_ownership" in out.fields and out.reasons
    # 대표 공고가 1년 넘게 앞서면 '어려움'을 쓰지 않는다
    late = J.preview_layer(owner, "청년", rep, "lh.youth_rental", index, date(2028, 1, 1))
    assert late.outcome == J.CHECK
    # 대표 공고에 없는 계층은 판정하지 않는다
    assert J.preview_layer(p, "고령자", rep, "lh.youth_rental", index, None).outcome == J.NONE
    assert J.summary([late, out, ok]) == ok.outcome


def test_money_margin_needs_clear_excess():
    rep, index, p = load_notice("N11"), _youth_index(), _youth_profile()
    rich = replace(p, total_assets=10 ** 11)                 # 한도의 수백 배 — 금액을 줄여도 걸림
    assert J.preview_layer(rich, "청년", rep, "lh.youth_rental", index, None).outcome == J.UNLIKELY


def test_backtest_no_misses_on_known_risky_templates():
    """2026-11-10 되짚어 보기에서 놓침이 났던 틀(공고 유형마다 조건 유무가 다름·기준 변경·같은 해 다른 한도)."""
    rc = EP.main(["--limit", "60", "--template", "lh.newlywed_town_sale", "lh.public_rental", "lh.select_rental",
                  "sh.happy_housing"])
    assert rc == 0
