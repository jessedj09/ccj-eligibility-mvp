# -*- coding: utf-8 -*-
"""독립 검증 워크시트 대조(피드백 B5) — 사람이 공고 PDF만 보고 채운 판단(docs/independent-validation-cases.json의
user_verdict)을 엔진 결과와 맞대어 본다. 사용: python tools/worksheet_check.py [--show-engine]

B2 비교(tools/draft_compare.py)는 '자동 분석 = 사람 등록'을 잰다 — 둘이 같은 원문을 똑같이 잘못 읽으면 잡지 못한다. 이 도구는
원문만 본 사람의 판단과 엔진을 대조해 그 빈틈을 메운다. 불일치는 ① 엔진(규칙) 오류 ② 작성자 오독 ③ 원문 해석 갈림
(docs/lh-inquiry-questions.md) 셋 중 하나로 분류해 기록한다.
- user_verdict가 빈 사례는 건너뛴다(채운 만큼만 대조). '확인필요'는 엔진의 보류(NEEDS_INFO·MANUAL_REVIEW)와 같다고 본다.
- --show-engine은 작성자가 다 채운 뒤에만 쓴다(먼저 보면 독립 검증이 아니다).
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from profile_io import household_from_dict  # noqa: E402
from rule_data import load_notice  # noqa: E402
from rule_engine import evaluate  # noqa: E402

CASES = ROOT / "docs" / "independent-validation-cases.json"
HOLD = {"NEEDS_INFO", "MANUAL_REVIEW", "확인필요"}


def engine_verdict(case: dict) -> str:
    profile = household_from_dict(dict(case["profile"], profile_id=f"W{case['id']}"))
    return evaluate(profile, load_notice(case["notice"]), case["layer"]).verdict


def same(user: str, engine: str) -> bool:
    return user == engine or (user in HOLD and engine in HOLD)


def check(cases: list) -> dict:
    out = {"filled": 0, "agree": 0, "mismatch": []}
    for c in cases:
        user = (c.get("user_verdict") or "").strip()
        if not user:
            continue
        out["filled"] += 1
        eng = engine_verdict(c)
        if same(user, eng):
            out["agree"] += 1
        else:
            out["mismatch"].append({"id": c["id"], "notice": c["notice"], "layer": c["layer"], "user": user, "engine": eng,
                                    "user_page": c.get("user_page", ""), "memo": c.get("memo", "")})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--show-engine", action="store_true", help="모든 사례의 엔진 결과(작성자가 다 채운 뒤에만)")
    a = ap.parse_args(argv)
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    res = check(cases)
    print(f"사례 {len(cases)}건 중 채운 {res['filled']}건 — 일치 {res['agree']} · 불일치 {len(res['mismatch'])}")
    for m in res["mismatch"]:
        print(f"  #{m['id']} {m['notice']}/{m['layer']}: 작성자 {m['user']}(p.{m['user_page'] or '?'}) ≠ 엔진 {m['engine']} — {m['memo']}")
    if a.show_engine:
        for c in cases:
            print(f"  #{c['id']} {c['notice']}/{c['layer']}: 엔진 {engine_verdict(c)}")
    return 1 if res["mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
