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


# ---------------------------------------------------------------- 묶음 B(2026-11-14) — 예비 판정 품질
def _regs_for(template, *nids):
    from find import registered
    regs, _ = registered()
    return [r for r in regs if r.template == template and (not nids or r.notice_id in nids)]


def test_one_common_mandatory_failure_is_enough_for_unlikely():
    """필수 조건(묶음 밖) 하나가 모든 공고에 같은 식인 조건이면, 공고마다 다른 조건에 함께 걸려도 '어려움'."""
    conds = {"a": ("home_ownership", "c1", False), "b": ("residence_area", "c2", False)}
    common = {"home_ownership": {"c1"}, "residence_area": {"c2"}}
    r = _result("a", "b")
    assert J._judge_failed(r, conds, common)[1] is False                          # 전부-같음 규칙으로는 못 감
    assert J._top_level_solid(r, None, None, "L", conds, common) is True           # 하나로 충분
    assert J._top_level_solid(_result("b"), None, None, "L", conds, common) is False


def test_group_all_tracks_failed_on_common_conditions():
    """영구임대 1순위 신분 묶음: 구성이 같은 틀 모든 공고에서 같고 모든 순위가 '어려움' 근거 조건으로 떨어지면 '어려움'."""
    index = J.CommonIndex(_regs_for("lh.permanent_rental"))
    rep = load_notice("N34")
    layer = next(iter(rep.layers))
    rid = next(c.rule_id for c in rep.layers[layer].conditions if c.tracks)
    assert index.group_sig("N34", layer, rid) in index.common_groups("lh.permanent_rental", layer)


def test_sibling_extra_condition_turns_likely_into_check():
    """대표 공고에 없는 조건(같은 사업 다른 공고에만 있음)에 걸리면 '지원 가능(단서)' 대신 확인 필요 — 신혼희망타운 하위 유형."""
    regs = _regs_for("lh.newlywed_town_sale")
    index = J.CommonIndex(regs)
    rep = load_notice("N45")                       # 추가 입주자 — 소득 조건 없음
    layer = "신혼부부"
    rich = None
    for _n, _l, p in gc.cases(only=[("N46", layer)]):
        if evaluate(p, load_notice("N46"), layer).verdict == "INELIGIBLE" and evaluate(p, rep, layer).verdict == "ELIGIBLE":
            rich = p
            break
    assert rich is not None
    out = J.preview_layer(rich, layer, rep, "lh.newlywed_town_sale", index, date(2026, 10, 1))
    assert out.outcome == J.CHECK and out.verdict == "INELIGIBLE" and out.fields and "다른 공고" in out.reasons[0]
