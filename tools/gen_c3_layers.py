# -*- coding: utf-8 -*-
"""C3: 행복주택 새 계층(고령자·산업단지근로자·주거급여수급자·지역전략산업종사자)을 공고 JSON에 추가한다.

사용: python tools/gen_c3_layers.py      (여러 번 실행해도 같은 결과 — 해당 계층·표를 덮어쓴다)

- 결정표 행은 원문 표를 손으로 옮긴 것이다(쪽은 각 표의 source). 원문 표에 칸이 없는 조합은 입력 모순으로 본다.
- 인용문 쪽은 대상 PDF에서 자동 탐색(계층 대표 문구가 있는 쪽 근처 우선). 찾지 못하면 MISSING으로 보고한다.
- 생성 후 python tools/verify_sources.py 와 pytest(tests/test_c3_layers.py)로 확인한다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import source_verify as sv  # noqa: E402

B1, B2, B3 = [345000000, 45420000], [379000000, 49960000], [413000000, 54510000]
SEOUL_ADJ = ["서울특별시", "의정부시", "남양주시", "하남시", "구리시", "성남시", "과천시", "안양시", "광명시",
             "부천시", "인천광역시", "김포시", "고양시", "양주시"]
INCONSISTENT = {"code": "INPUT_INCONSISTENT", "detail": ""}
ASSET_QUOTES = ["345,000,000원", "379,000,000원", "413,000,000원", "45,420,000원", "49,960,000원", "54,510,000원"]


def no_row(detail):
    return {"result": "NO_ROW", "no_row": {"code": "INPUT_INCONSISTENT", "detail": detail}}


D_ALONE_CHILD = "가구원수가 1인인데 출생자녀 가산 대상 자녀가 있습니다(자녀도 가구원). 가구원수 또는 자녀 입력을 확인해 주세요."
D_ALONE_DUAL = "가구원수가 1인인데 맞벌이로 입력했습니다(원문 표의 1인 맞벌이 칸은 '-'). 가구원수 또는 맞벌이 입력을 확인해 주세요."
D_TWO_KIDS = "가구원수가 2인인데 출생자녀 가산 대상 자녀가 2명 이상입니다. 가구원수 또는 자녀 입력을 확인해 주세요."
D_DUAL2_CHILD = "맞벌이 부부 2인 가구인데 출생자녀 가산 대상 자녀가 있습니다(부부+자녀면 3인 이상). 입력을 확인해 주세요."
D_DUAL3_KIDS = "맞벌이 부부 3인 가구인데 출생자녀 가산 대상 자녀가 2명 이상입니다(부부+자녀 2명이면 4인 이상). 입력을 확인해 주세요."


def r(when, out=None, readings=None, **extra):
    row = {"when": when}
    if out is not None:
        row["out"] = out
    row.update(extra)
    if readings:
        row["readings"] = readings
    return row


# --- 고령자: 가구원수 × 출생자녀 (금천 p.13 / 가좌 p.7 / 오류 p.11 결합표) -------------------------------
ELDERLY_ROWS = [
    r({"size": 1, "child": 0}, [120] + B1),
    r({"size": 1, "child": "1+"}, **no_row(D_ALONE_CHILD)),
    r({"size": 2, "child": 0}, [110] + B1),
    r({"size": 2, "child": 1}, [120] + B2),
    r({"size": 2, "child": "2+"}, **no_row(D_TWO_KIDS)),
    r({"size": "3+", "child": 0}, [100] + B1),
    r({"size": "3+", "child": 1}, [110] + B2),
    r({"size": "3+", "child": "2+"}, [120] + B3),
]

# --- 산업단지근로자: 맞벌이 × 가구원수 × 출생자녀 (금천 p.6 결합표) -----------------------------------------
INDUSTRIAL_ROWS = [
    # 맞벌이 X
    r({"size": 1, "child": 0, "dual": False}, [120] + B1),
    r({"size": 1, "child": "1+", "dual": False}, **no_row(D_ALONE_CHILD)),
    r({"size": 2, "child": 0, "dual": False}, [110] + B1),
    r({"size": 2, "child": 1, "dual": False}, [120] + B2),
    r({"size": 2, "child": "2+", "dual": False}, **no_row(D_TWO_KIDS)),
    r({"size": "3+", "child": 0, "dual": False}, [100] + B1),
    r({"size": "3+", "child": 1, "dual": False}, [110] + B2),
    r({"size": "3+", "child": "2+", "dual": False}, [120] + B3),
    # 맞벌이 ○
    r({"size": 1, "child": "any", "dual": True}, **no_row(D_ALONE_DUAL)),
    r({"size": 2, "child": 0, "dual": True}, [130] + B1),
    r({"size": 2, "child": "1+", "dual": True}, **no_row(D_DUAL2_CHILD)),
    r({"size": 3, "child": 0, "dual": True}, [120] + B1),
    r({"size": 3, "child": 1, "dual": True}, [130] + B2),
    r({"size": 3, "child": "2+", "dual": True}, **no_row(D_DUAL3_KIDS)),
    r({"size": "4+", "child": 0, "dual": True}, [120] + B1),
    r({"size": "4+", "child": 1, "dual": True}, [130] + B2),
    r({"size": "4+", "child": "2+", "dual": True}, [140] + B3),
]

# --- 지역전략산업종사자(부천 p.7): 원문은 가구원수 × 맞벌이 표만 있고 출생자녀 가산 언급이 없다 -------------
R_TABLE = "원문 그대로(이 계층은 출생자녀 가산 언급 없음)"
R_BONUS = "다른 계층과 같은 출생자녀 가산 적용(같은 공고 다른 계층·산업단지형 공고의 가산표)"
REGIONAL_ROWS = [
    r({"size": 1, "child": "any", "dual": True}, **no_row(D_ALONE_DUAL)),
    # 원문 그대로: 자녀와 무관, 자산 3억4,500만·자동차 4,542만 고정
    r({"size": 1, "child": "any", "dual": False}, [120] + B1, [R_TABLE]),
    r({"size": 2, "child": "any", "dual": False}, [110] + B1, [R_TABLE]),
    r({"size": 2, "child": "any", "dual": True}, [130] + B1, [R_TABLE]),
    r({"size": "3+", "child": "any", "dual": False}, [100] + B1, [R_TABLE]),
    r({"size": "3+", "child": "any", "dual": True}, [120] + B1, [R_TABLE]),
] + [dict(row, readings=[R_BONUS]) if "out" in row else row for row in INDUSTRIAL_ROWS if row["when"] != {
    "size": 1, "child": "any", "dual": True}]


def table(label, columns, rows, page, readings=None, quotes=None, derivation=None):
    inputs = {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"}, "dual": {"var": "dual_income"}}
    t = {"label": label, "columns": columns, "inputs": {c: inputs[c] for c in columns},
         "outputs": ["ratio", "asset_limit", "car_limit"], "rows": rows,
         "source": {"page": page, "quote": list(quotes or ASSET_QUOTES)}}
    if derivation:
        t["source"]["derivation"] = derivation
    if readings:
        t["readings"] = readings
    return t


INCOME = {"lte": [{"var": "monthly_income"},
                  {"lookup": ["income_standard", {"var": "household_size"}, {"term": "ratio"}]}]}
ASSETS = {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}
CAR = {"lte": [{"var": "car_value", "unknown_values": ["확인불가"]}, {"term": "car_limit"}]}
HOME = {"eq": [{"var": "home_ownership"}, "무주택"]}


def cond(cid, field, quotes, note, check, **extra):
    d = {"id": cid, "field": field, "required": True, "source": {"quote": quotes}, "note": note, "check": check}
    d.update(extra)
    return d


def elderly(nid, home_quote):
    p = f"{nid}-E"
    return [
        cond(f"{p}-home", "home_ownership", [home_quote], "무주택세대구성원인지(세대 전원 무주택)", HOME),
        cond(f"{p}-age", "age", [home_quote], "공고일 현재 65세 이상인지", {"gte": [{"var": "age"}, 65]}),
        cond(f"{p}-income", "monthly_income", ["해당 세대의 월평균소득이 전년도 도시근로자 가구원수별 가구당 월평균소득의 100퍼센트 이하"],
             "해당 세대 월평균소득이 출생자녀 가산을 반영한 기준(1인 120%·2인 110%·3인 이상 100%) 이내인지", INCOME,
             table="elderly_terms"),
        cond(f"{p}-assets", "total_assets", ["해당 세대가 보유하고 있는 총 자산가액이 34,500만원 이하"],
             "해당 세대 총자산이 출생자녀 가산을 반영한 자산기준 이내인지", ASSETS, table="elderly_terms"),
        cond(f"{p}-car", "car_value", ["총 자산 중 자동차가액이 4,542만원 이하"],
             "자동차가액이 출생자녀 가산을 반영한 기준 이내인지", CAR, table="elderly_terms"),
    ]


def industrial(nid):
    p = f"{nid}-I"
    return [
        cond(f"{p}-home", "home_ownership", ["무주택세대구성원(혼인 중이 아닌 경우 무주택자)"],
             "무주택인지(혼인 중이면 세대 전원, 혼인 중이 아니면 본인 기준)", HOME),
        cond(f"{p}-workplace", "industrial_workplace",
             ["소재한 산업단지의 입주기업 및 교육·연구기관(입주 예정인 기업 및 교육·연구기관을 포함한다) 또는 경제자유구역에 "
              "입주한 중소기업(입주예정* 중소기업을 포함한다)에 근무 중일 것"],
             "산업단지 입주기업·교육·연구기관 또는 경제자유구역 입주 중소기업(입주예정 포함)에 근무 중인지",
             {"in": [{"var": "industrial_workplace"},
                     ["산업단지 입주기업", "산업단지 교육·연구기관", "경제자유구역 입주 중소기업"]]}),
        cond(f"{p}-workarea", "workplace_area",
             ["해당 주택건설지역(서울시) 또는 연접지역(의정부시, 남양주시, 구리시, 하남시, 성남시, 과천시, 안양시, 광명시, "
              "부천시, 인천광역시, 김포시, 고양시, 양주시)에 소재한 산업단지"],
             "그 근무처(산업단지·경제자유구역)가 서울특별시 또는 연접 13개 시에 있는지",
             {"in": [{"var": "workplace_area"}, SEOUL_ADJ]}),
        cond(f"{p}-affiliation", "industrial_affiliation",
             ["해당 기업에 소속되지 않고 근무 중인 경우에는 1년 이상 근무 중이거나 1년 미만 근무 중이더라도 1년 이상 근무 예정인 사람만 해당"],
             "그 기업 소속이거나, 소속이 아니면 1년 이상 근무 중(또는 1년 이상 근무 예정)인지",
             {"in": [{"var": "industrial_affiliation"}, ["소속", "비소속 1년 이상 근무(예정)"]]}),
        cond(f"{p}-income", "monthly_income",
             ["해당 세대의 월평균소득이 전년도 도시근로자 가구원수별 가구당 월평균소득의 100퍼센트 이하(맞벌이 부부 120퍼센트 이하)일 것"],
             "해당 세대 월평균소득이 맞벌이·출생자녀 가산을 반영한 기준 이내인지", INCOME, table="industrial_worker_terms"),
        cond(f"{p}-assets", "total_assets", ["해당 세대가 보유하고 있는 총 자산가액 합산기준 34,500만원 이하"],
             "해당 세대 총자산이 출생자녀 가산을 반영한 자산기준 이내인지", ASSETS, table="industrial_worker_terms"),
        cond(f"{p}-car", "car_value", ["총 자산 중 자동차가액이 4,542만원 이하"],
             "자동차가액이 출생자녀 가산을 반영한 기준 이내인지", CAR, table="industrial_worker_terms"),
        cond(f"{p}-sub", "has_subscription_account",
             ["본인 또는 배우자중 1인이 입주 전까지 주택청약종합저축(청약저축 포함) 가입사실을 증명할 수 있을 것"],
             "본인 또는 배우자가 입주 전까지 청약통장 가입을 증명할 수 있는지(현재 자격과 무관)", True,
             timing="BEFORE_MOVE_IN"),
    ]


def housing_benefit(nid, home_quote):
    p = f"{nid}-H"
    return [
        cond(f"{p}-home", "home_ownership", [home_quote], "무주택세대구성원인지(세대 전원 무주택)", HOME),
        cond(f"{p}-benefit", "housing_benefit_status",
             ["'주거급여수급자'란 「주거급여법」 제2조 제2호 및 제3호에 따른 수급권자 또는 수급자를 말함"],
             "「주거급여법」에 따른 주거급여 수급권자 또는 수급자인지(공고에 별도 소득·자산 기준 조항 없음)",
             {"in": [{"var": "housing_benefit_status"}, ["수급자", "수급권자"]]}),
    ]


def regional(nid):
    p = f"{nid}-R"
    return [
        cond(f"{p}-home", "home_ownership", ["무주택세대구성원(미혼일 경우 무주택자)"],
             "무주택인지(혼인 중이면 세대 전원, 미혼이면 본인 기준)", HOME),
        cond(f"{p}-age", "age", ["19세 ～39세 이하인 청년"], "19세 이상 39세 이하인지", {"between": [{"var": "age"}, 19, 39]}),
        cond(f"{p}-type", "regional_industry_type",
             ["문화산업종사자, 등록예술인 및 부천시가 추천하는 자 중 하나에 해당하는",
              "문화산업종사자 중 콘텐츠산업 종사자는 LH에 청약신청을 하고 그 신청자를 대상으로 부천시가 확인하는 방식"],
             "문화산업종사자(콘텐츠산업·전문예술법인·단체)·등록 예술인·부천시 추천자 중 하나인지",
             {"any": [
                 {"in": [{"var": "regional_industry_type"}, ["전문예술법인·단체 종사자", "등록 예술인"]]},
                 {"in": [{"var": "regional_industry_type"}, ["콘텐츠산업 종사자", "부천시 추천자"]],
                  "review_if_true": {"code": "SELF_REPORT_UNVERIFIED",
                                     "detail": "콘텐츠산업 종사자·부천시 추천자 자격은 신청 후 부천시가 확인·추천한다(p.6~7) — "
                                               "신청 시점에는 확정할 수 없음"}},
             ]}),
        cond(f"{p}-income", "monthly_income",
             ["해당 세대의 월평균소득이 전년도 도시근로자 가구원수별 가구당 월평균소득의 100% 이하, 맞벌이 부부는 120% 이하일 것"],
             "해당 세대 월평균소득이 기준(1인 120%·2인 110%·3인 이상 100%, 맞벌이 2인 130%·3인 이상 120%) 이내인지",
             INCOME, table="regional_worker_terms", reading_detail="지역전략산업종사자 출생자녀 가산 적용 여부 불일치"),
        cond(f"{p}-assets", "total_assets", ["총 자산가액이 34,500만원 이하이고 총 자산 중 자동차가액이 4,542만원 이하일 것"],
             "해당 세대 총자산이 자산기준 이내인지", ASSETS, table="regional_worker_terms",
             reading_detail="지역전략산업종사자 출생자녀 가산 적용 여부 불일치"),
        cond(f"{p}-car", "car_value", ["총 자산가액이 34,500만원 이하이고 총 자산 중 자동차가액이 4,542만원 이하일 것"],
             "자동차가액이 기준 이내인지", CAR, table="regional_worker_terms",
             reading_detail="지역전략산업종사자 출생자녀 가산 적용 여부 불일치"),
        cond(f"{p}-sub", "has_subscription_account",
             ["본인 또는 배우자 중 1인이 입주 전까지 주택청약종합저축(청약저축 포함) 가입사실을 증명할 수 있을 것"],
             "본인 또는 배우자가 입주 전까지 청약통장 가입을 증명할 수 있는지(현재 자격과 무관)", True,
             timing="BEFORE_MOVE_IN"),
    ]


ELDER_HOME = "무주택세대구성원으로서 아래의 요건을 모두 갖춘 65세 이상인 자"
PLAN = {
    "N5": {"지역전략산업종사자": (regional, "지역전략산업종사자", 6)},
    "N6": {"고령자": (lambda n: elderly(n, ELDER_HOME), "고령자", 13),
           "산업단지근로자": (industrial, "산업단지 근로자", 5)},
    "N9": {"고령자": (lambda n: elderly(n, ELDER_HOME), "고령자", 7)},
    "N10": {"고령자": (lambda n: elderly(n, ELDER_HOME), "고령자", 11),
            "주거급여수급자": (lambda n: housing_benefit(n, "현재 무주택세대구성원인 주거급여수급자"), "주거급여수급자", 12)},
}
# 주거약자용 주택: C1·C2에서 미지원 목록에 빠뜨린 공고(주택형 축 — C5)
HOUSING_WEAK = {"N6": 8, "N10": 12}
TABLE_SPECS = {
    "elderly_terms": dict(label="고령자 계층 출생자녀 가산 소득·자산 기준: 가구원수×출생자녀수 (결합표)",
                          columns=["size", "child"], rows=ELDERLY_ROWS),
    "industrial_worker_terms": dict(label="산업단지근로자 출생자녀 가산 소득·자산 기준: 맞벌이×가구원수×출생자녀수 (결합표)",
                                    columns=["size", "child", "dual"], rows=INDUSTRIAL_ROWS),
    "regional_worker_terms": dict(
        label="지역전략산업종사자 소득·자산 기준: 가구원수×맞벌이 (원문 표에 출생자녀 가산 없음)",
        columns=["size", "child", "dual"], rows=REGIONAL_ROWS, readings=[R_TABLE, R_BONUS],
        quotes=["34,500만원 이하", "4,542만원 이하", "7,626,151원 이하", "9,802,115원 이하"],
        derivation="'다른 계층과 같은 출생자녀 가산 적용' 해석의 가산 행(379,000,000원/413,000,000원, 맞벌이 130%·140% 등)은 "
                   "이 공고에 없고, 같은 LH 행복주택 산업단지형 공고(N6 서울금천 p.6)의 산업단지근로자 가산표를 빌려 온 값이다. "
                   "두 해석의 결과가 갈릴 때만 MANUAL_REVIEW가 된다."),
}
TABLE_OF = {"고령자": "elderly_terms", "산업단지근로자": "industrial_worker_terms",
            "지역전략산업종사자": "regional_worker_terms"}


def locate(pages, text, anchor):
    found = [i + 1 for i, p in enumerate(pages) if sv.normalize(text) in p]
    return min(found, key=lambda p: (abs(p - anchor), p < anchor)) if found else None


def place_quotes(source, pages, anchor, where, missing):
    quotes, first = [], None
    for q in source["quote"]:
        p = locate(pages, q, anchor)
        if p is None:
            missing.append(f"{where}: '{q}'")
            continue
        if first is None:
            first = p
        quotes.append(q if p == first else {"page": p, "text": q})
    source["page"] = first or anchor
    source["quote"] = quotes


def main():
    for nid, layers in PLAN.items():
        path = ROOT / "rules" / "notices" / f"{nid}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        pages = sv.pdf_pages(nid)
        missing = []
        for layer, (build, anchor_text, hint) in layers.items():
            anchor = locate(pages, anchor_text, hint) or hint
            conds = build(nid)
            for c in conds:
                place_quotes(c["source"], pages, anchor, f"{layer}/{c['id']}", missing)
            doc["layers"][layer] = {"conditions": conds}
            name = TABLE_OF.get(layer)
            if name:
                spec = TABLE_SPECS[name]
                t = table(spec["label"], spec["columns"], spec["rows"], anchor, spec.get("readings"),
                          spec.get("quotes"), spec.get("derivation"))
                place_quotes(t["source"], pages, anchor, f"table:{name}", missing)
                doc["tables"][name] = t
            doc["unsupported_layers"] = [u for u in doc.get("unsupported_layers", []) if u["name"] != layer]
        # 금천·오류의 주거약자용 주택은 고령자 배정 주택형이라 고령자 판정과 같다(C5에서 확인) — 미지원 목록에 넣지 않는다
        doc["unsupported_layers"] = [u for u in doc["unsupported_layers"] if u["name"] != "주거약자용 주택"]
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(nid, "계층", list(doc["layers"]), "미지원", [u["name"] for u in doc["unsupported_layers"]],
              "MISSING", len(missing))
        for m in missing:
            print("   -", m)


if __name__ == "__main__":
    main()
