# -*- coding: utf-8 -*-
"""C5a: 주거약자용 주택형을 계층으로 추가한다. 사용: python tools/gen_c5_housing_weak.py   (재실행 안전)

원문 구조(직접 확인):
- N4 하남감일·위례 p.7 / N7 서울대방 p.7·p.8 / N8 의왕청계2 p.8: "신혼부부·한부모가족 계층(일반 공급대상자)의 요건을 모두
  갖추고 아래 주거약자의 요건을 갖춘 자". 주거약자 = ① 65세 이상 고령자 ②~⑦ 장애인·국가유공자 상이 등.
  → "신혼부부(주거약자용)", "한부모(주거약자용)" = 기본 계층 조건 그대로 + 주거약자 조건.
- N5 부천영상 p.11: "지역전략산업종사자, 청년, 대학생 중 하나의 자격요건을 충족하면서 주거약자(장애인 등)에 해당".
  주거약자 정의에 고령자가 없다(① 장애인부터). → "주거약자(26A1/B1형)" = 트랙(세 계층 중 하나) + 주거약자 조건.
- N1 서울공릉 p.7·p.8: N7과 같은 문구('59주거약자' 주택형) → "신혼부부(주거약자용)", "한부모(주거약자용)".
- N2 서울관악봉천 p.1·p.7: "「주거약자용주택」은 '대학생인 주거약자'에게 우선공급" → "대학생(주거약자용)" = 대학생 조건 + 주거약자 조건.
  남은 주택은 다른 주택형을 신청한 대학생 예비자가 희망하면 공급한다(원문) — 주거약자가 아니어도 대학생 계층으로 그 경로가 있다.
- N6 서울금천·N10 서울오류: 주거약자용 주택은 고령자에게 배정된 주택형(65세 이상 고령자가 신청 대상) → 고령자 계층과 같다.
  계층을 만들지 않고 공고 유의사항으로 안내한다(tools/gen_c1_notices.py가 담당).

이 스크립트는 위 변형 계층만 소유한다. 기본 계층이 바뀌면(gen_c1·gen_c3) 이 스크립트를 다시 돌려 복사본을 맞춘다 —
tests/test_c5_housing_weak.py가 "변형 계층 = 기본 계층 + 주거약자 조건"을 확인한다.
"""
import copy
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import source_verify as sv  # noqa: E402

_spec = importlib.util.spec_from_file_location("gen_c3_layers", ROOT / "tools" / "gen_c3_layers.py")
C3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C3)
cond, locate, place_quotes = C3.cond, C3.locate, C3.place_quotes

WEAK_TYPES = ["장애인", "국가유공자(상이 1~7급)", "보훈보상대상자(상이 1~7급)", "5·18민주화운동부상자(장해 1~14급)",
              "고엽제후유의증환자(경도 이상)", "국가유공자에 준하는 군경(상이 1~7급)"]
DISABLED_QUOTE = "「장애인복지법」 제2조제2항에 해당하는 장애인"


def weak_condition(nid, with_elderly, quotes):
    legs = [{"in": [{"var": "housing_weak_type"}, WEAK_TYPES]}]
    if with_elderly:
        legs.insert(0, {"gte": [{"var": "age"}, 65]})
    note = ("신청자 본인이 주거약자인지 — " + ("65세 이상 고령자이거나 " if with_elderly else "")
            + "장애인, 상이등급 1~7급 국가유공자·보훈보상대상자·준군경, 5·18 부상자(장해 1~14급), 고엽제후유의증환자(경도 이상)")
    return cond(f"{nid}-W-weak", "housing_weak_type" + ("/age" if with_elderly else ""), quotes, note, {"any": legs})


PLAN = {
    "N1": dict(bases=["신혼부부", "한부모"], elderly=True, page=7,
               quotes=["신혼부부·한부모가족의 일반 공급대상자의 요건을 모두 갖추고 아래 주거약자의 요건을 갖춘 사람",
                       "65세 이상인 사람(고령자)", DISABLED_QUOTE]),
    "N2": dict(bases=["대학생"], elderly=True, page=7,
               quotes=["「주거약자용주택」은 '대학생인 주거약자'에게 우선공급", "고령자(만65세 이상인 자)", DISABLED_QUOTE]),
    "N4": dict(bases=["신혼부부", "한부모"], elderly=True, page=7,
               quotes=["신혼부부·한부모가족 계층 공급대상자의 요건을 모두 갖추고 아래 주거약자의 요건을 갖춘 자", DISABLED_QUOTE]),
    "N7": dict(bases=["신혼부부", "한부모"], elderly=True, page=7,
               quotes=["신혼부부·한부모가족의 일반 공급대상자의 요건을 모두 갖추고 아래 주거 약자의 요건을 갖춘 사람",
                       "65세 이상인 사람(고령자)"]),
    "N8": dict(bases=["신혼부부", "한부모"], elderly=True, page=8,
               quotes=["신혼부부·한부모가족의 일반 공급대상자의 요건을 모두 갖추고 아래 주거약자의 요건을 갖춘 사람", DISABLED_QUOTE]),
    "N5": dict(tracks=["지역전략산업종사자", "청년", "대학생"], elderly=False, page=11,
               quotes=["지역전략산업종사자, 청년, 대학생 중 하나의 자격요건을 충족 하면서 주거약자(장애인 등)에 해당", DISABLED_QUOTE]),
}


def apply_weak(doc, nid, plan, pages):
    """공고 문서(메모리)에 주거약자용 변형 계층을 넣는다(이전 변형 계층은 지우고 다시 — 재실행 안전). plan = PLAN[nid] 모양."""
    missing = []
    anchor = plan["page"]
    doc["layers"] = {k: v for k, v in doc["layers"].items() if "(" not in k}
    if "bases" in plan:
        for base in plan["bases"]:
            conds = copy.deepcopy(doc["layers"][base]["conditions"])
            weak = weak_condition(nid, plan["elderly"], list(plan["quotes"]))
            place_quotes(weak["source"], pages, anchor, f"{base}(주거약자용)/{weak['id']}", missing)
            doc["layers"][f"{base}(주거약자용)"] = {"conditions": conds + [weak]}
    else:
        group = {"id": f"{nid}-W-base", "field": "계층", "required": True,
                 "source": {"quote": [plan["quotes"][0]]},
                 "note": "지역전략산업종사자·청년·대학생 중 하나의 자격요건을 충족하는지",
                 "tracks": [{"id": t, "label": f"{t} 계층 자격요건",
                             "conditions": copy.deepcopy(doc["layers"][t]["conditions"])} for t in plan["tracks"]]}
        place_quotes(group["source"], pages, anchor, "주거약자/base", missing)
        weak = weak_condition(nid, plan["elderly"], list(plan["quotes"][1:]))
        place_quotes(weak["source"], pages, anchor, "주거약자/weak", missing)
        doc["layers"]["주거약자(26A1/B1형)"] = {"conditions": [group, weak]}
    doc["unsupported_layers"] = [u for u in doc.get("unsupported_layers", []) if "주거약자" not in u["name"]]
    return missing


def main():
    for nid, plan in PLAN.items():
        path = ROOT / "rules" / "notices" / f"{nid}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        missing = apply_weak(doc, nid, plan, sv.pdf_pages(nid))
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(nid, "계층", list(doc["layers"]), "미지원", [u["name"] for u in doc["unsupported_layers"]],
              "MISSING", len(missing))
        for m in missing:
            print("   -", m)


if __name__ == "__main__":
    main()
