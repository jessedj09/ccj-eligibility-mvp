# -*- coding: utf-8 -*-
"""C4a: LH 매입임대·든든전세 7건(N11~N17)을 만든다. 사용: python tools/gen_c4_lh.py   (재실행 안전 — 같은 결과)

| ID  | 원문 | 사업 | 공고일 |
| N11 | LH06 | 청년매입임대(2차) | 2026-06-25 |
| N12 | LH07 | 청년매입임대(3차) | 2026-09-17 |
| N13 | LH01 | 신혼·신생아 매입임대Ⅰ(2차) | 2026-06-25 |
| N14 | LH03 | 신혼·신생아 매입임대Ⅰ(3차) | 2026-09-17 |
| N15 | LH02 | 신혼·신생아 매입임대Ⅱ 전세형(2차) | 2026-06-25 |
| N16 | LH04 | 든든전세(비분양전환형, 1차) | 2026-05-22 |
| N17 | LH05 | 든든전세(비분양전환형, 2차) | 2026-10-01 |

- 순위·유형은 트랙 묶음(조건의 "tracks")으로 표현한다: 공통요건 AND (트랙 중 하나 이상).
- 원문 표의 수치(소득 금액·자산 한도)는 손으로 옮긴 리터럴이다. 날짜는 원문이 적은 리터럴(LH 관행).
- 인용문 쪽은 대상 PDF에서 자동 탐색한다. 생성 후 tools/verify_sources.py, pytest(tests/test_c4_lh.py)로 확인.
"""
import copy
import hashlib
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
cond, r, no_row, locate, place_quotes = C3.cond, C3.r, C3.no_row, C3.locate, C3.place_quotes
B1, B2, B3 = C3.B1, C3.B2, C3.B3

CAPITAL = ["서울특별시", "인천광역시", "수원시", "성남시", "고양시", "용인시", "부천시", "안산시", "안양시", "남양주시",
           "화성시", "평택시", "의정부시", "시흥시", "파주시", "김포시", "광명시", "광주시", "군포시", "하남시", "오산시",
           "이천시", "안성시", "의왕시", "양주시", "구리시", "포천시", "여주시", "동두천시", "과천시", "가평군", "양평군", "연천군"]
WELFARE_1ST = ["생계·의료·주거급여 수급자", "차상위계층"]          # 청년매입 1순위(p.3: 생계·의료·주거급여 / 차상위)
WELFARE_EXEMPT = ["생계·의료·주거급여 수급자", "교육급여만 수급", "차상위계층"]  # 신혼·신생아 소득·자산 검증 면제(수급자·차상위)
HOME = {"eq": [{"var": "home_ownership"}, "무주택"]}
D_7PLUS = "원문 소득표에 7인 이상 가구 금액이 없습니다(행복주택과 달리 7인 이상 가산 규칙도 적혀 있지 않음)."


# ------------------------------------------------------------------------------------------------
# 청년매입임대 (LH06 p.3 / LH07 p.3)
# ------------------------------------------------------------------------------------------------
def youth_rental(nid, birth_range, under30):
    p = nid

    def common(prefix):
        return [
            cond(f"{p}-{prefix}-home", "home_ownership",
                 ["무주택자인 미혼 청년으로서 소득 및 자산 기준을 충족하는", "부모가 주택을 소유한 경우에도 신청 가능"],
                 "무주택자인지(본인 기준 — 부모가 주택을 소유해도 신청 가능)", HOME),
            cond(f"{p}-{prefix}-marital", "marital_status", ["무주택자인 미혼 청년으로서"],
                 "미혼인지",
                 {"any": [{"eq": [{"var": "marital_status"}, "미혼"]},
                          {"eq": [{"var": "marital_status"}, "한부모"],
                           "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                              "detail": "공고는 '미혼 청년'만 대상이지만 1순위에 '지원대상 한부모가족(신청자 본인)'이 있어 "
                                                        "혼인 이력이 있는 한부모의 신청 가능 여부가 원문에서 불명확(LH 확인 필요)"}}]}),
        ]

    not_youth = cond(f"{p}-notyouth", "age", ["①에 해당되지 않는 사람만 ② 또는 ③으로 신청"],
                     "19~39세가 아닌지(19~39세는 반드시 청년 유형으로 신청)",
                     {"any": [{"lte": [{"var": "age"}, 18]}, {"gte": [{"var": "age"}, 40]}]})
    rank = {
        "id": f"{p}-rank", "field": "순위", "required": True,
        "source": {"quote": ["입주순위", "신청 후 순위 변경은 불가하므로 신청 시 유의하시기 바랍니다"]},
        "note": "1·2·3순위 중 하나 이상 충족하는지(소득·자산 기준은 순위마다 다름)",
        "tracks": [
            {"id": "1순위", "label": "수급자·차상위계층 가구 또는 지원대상 한부모가족(소득·자산 검증 없음)", "conditions": [
                cond(f"{p}-T1-welfare", "welfare_status/parent_welfare_status/is_supported_single_parent",
                     ["생계·의료·주거급여 중 어느 하나에 해당", f"30세 미만({under30}이후 출생)인 경우에 한하여"],
                     "본인이 생계·의료·주거급여 수급자·차상위계층이거나 지원대상 한부모가족인지, 또는 부모가 수급자·차상위계층이고 "
                     "부모와 같은 주민등록표에 등재(30세 미만은 분리 거주도 가능)돼 있는지",
                     {"any": [
                         {"in": [{"var": "welfare_status"}, WELFARE_1ST]},
                         {"eq": [{"var": "is_supported_single_parent"}, True]},
                         {"all": [{"in": [{"var": "parent_welfare_status"}, WELFARE_1ST]},
                                  {"any": [{"eq": [{"var": "registered_with_parents"}, True]},
                                           {"lte": [{"var": "age"}, 29]}]}]},
                     ]})]},
            {"id": "2순위", "label": "본인+부모 소득 100%(1인 120%·2인 110%) 이하, 본인+부모 자산 국민임대 기준", "conditions": [
                cond(f"{p}-T2-income", "monthly_income/parents_monthly_income/parents_count",
                     ["본인과 부모의 월평균소득이 전년도 도시근로자 가구원수별"],
                     "본인과 부모의 월평균소득 합계가 가구원수(본인+부모) 기준 이내인지(1인 4,576,036 / 2인 6,452,897 / 3인 8,168,429원)",
                     {"lte": [{"fn": "add", "args": [{"var": "monthly_income"}, {"var": "parents_monthly_income"}]},
                              {"lookup": ["income_standard", {"fn": "add", "args": [1, {"var": "parents_count"}]},
                                          {"term": "ratio"}]}]},
                     table="youth_rental_rank2"),
                cond(f"{p}-T2-assets", "total_assets/parents_total_assets", ["총자산 34,500만원 이하"],
                     "본인과 부모의 총자산 합계가 3억4,500만원 이하인지",
                     {"lte": [{"fn": "add", "args": [{"var": "total_assets"}, {"var": "parents_total_assets"}]}, 345000000]}),
                cond(f"{p}-T2-car", "car_value/parents_car_value", ["자동차 4,542만원 이하"],
                     "본인과 부모가 보유한 자동차 중 가장 높은 차량가액이 4,542만원 이하인지",
                     {"lte": [{"fn": "max", "args": [{"var": "car_value", "unknown_values": ["확인불가"]},
                                                     {"var": "parents_car_value"}]}, 45420000]}),
            ]},
            {"id": "3순위", "label": "본인 소득 1인 가구 기준 이하, 본인 자산 행복주택(청년) 기준", "conditions": [
                cond(f"{p}-T3-income", "monthly_income", ["본인의 월평균소득이 전년도 도시근로자 1인 가구"],
                     "본인 월평균소득이 4,576,036원(1인 가구 100%+20%p) 이하인지",
                     {"lte": [{"var": "monthly_income"}, {"lookup": ["income_standard", 1, 120]}]}),
                cond(f"{p}-T3-assets", "total_assets", ["총자산 25,100만원 이하"],
                     "본인 총자산이 2억5,100만원 이하인지(원문은 '행복주택(청년) 자산기준'이라고만 적어 본인 기준으로 판정)",
                     {"lte": [{"var": "total_assets"}, 251000000]}),
                cond(f"{p}-T3-car", "car_value", ["자동차 4,542만원 이하"], "본인 자동차가액이 4,542만원 이하인지",
                     {"lte": [{"var": "car_value", "unknown_values": ["확인불가"]}, 45420000]}),
            ]},
        ],
    }
    layers = {
        "청년": common("Y") + [cond(f"{p}-Y-age", "age", [f"({birth_range} 출생자)"],
                                     "공고일 현재 19세 이상 39세 이하인지", {"between": [{"var": "age"}, 19, 39]}),
                             dict(copy.deepcopy(rank), id=f"{p}-Y-rank")],
        "대학생": common("U") + [dict(copy.deepcopy(not_youth), id=f"{p}-U-notyouth"),
                              cond(f"{p}-U-student", "student_status", ["대학생(입학·복학 예정자 포함)"],
                                   "대학에 재학 중이거나 입학·복학 예정인지",
                                   {"in": [{"var": "student_status"}, ["재학중", "입학예정", "복학예정"]]}),
                              dict(copy.deepcopy(rank), id=f"{p}-U-rank")],
        "취업준비생": common("J") + [dict(copy.deepcopy(not_youth), id=f"{p}-J-notyouth"),
                                cond(f"{p}-J-grad", "grad_or_dropout_date", ["졸업·중퇴 후 2년 이내인 사람으로서 미취업자"],
                                     "고등학교·대학교 등을 졸업·중퇴한 지 2년 이내인지",
                                     {"gte": [{"var": "grad_or_dropout_date"},
                                              {"fn": "years_before", "args": [{"ctx": "announcement_date"}, 2]}]}),
                                cond(f"{p}-J-unemployed", "is_employed", ["졸업·중퇴 후 2년 이내인 사람으로서 미취업자"],
                                     "현재 취업하지 않았는지", {"eq": [{"var": "is_employed"}, False]}),
                                dict(copy.deepcopy(rank), id=f"{p}-J-rank")],
    }
    tables = {"youth_rental_rank2": {
        "label": "청년매입임대 2순위 소득 비율: 가구원수(본인+부모) → 비율(1인 +20%p, 2인 +10%p 가산)",
        "columns": ["size"], "inputs": {"size": {"fn": "add", "args": [1, {"var": "parents_count"}]}},
        "outputs": ["ratio"],
        "rows": [r({"size": 1}, [120]), r({"size": 2}, [110]), r({"size": "3+"}, [100])],
        "source": {"quote": ["4,576,036원", "6,452,897원", "8,168,429원"]},
    }}
    return {name: {"conditions": conds} for name, conds in layers.items()}, tables


# ------------------------------------------------------------------------------------------------
# 신혼·신생아 매입임대 Ⅰ(LH01·LH03) / Ⅱ 전세형(LH02)
# ------------------------------------------------------------------------------------------------
def newlywed_rental(nid, kind, marriage_quote, marriage, child6, newborn, child6_quote, newborn_quote):
    p = nid
    exempt = {"all": [{"ne": [{"var": "marital_status"}, "예비신혼"]},
                      {"any": [{"in": [{"var": "welfare_status"}, WELFARE_EXEMPT]},
                               {"eq": [{"var": "is_supported_single_parent"}, True]}]}]}
    youngest_after = lambda d: {"if": [{"is": [{"var": "has_children"}, False]}, False,
                                       {"gte": [{"var": "youngest_child_birth_date"}, {"date": d}]}]}
    types = [
        {"id": "①신혼부부", "label": "혼인 7년 이내 신혼부부", "conditions": [
            cond(f"{p}-T-newlywed", "marital_status/marriage_date", [marriage_quote],
                 f"혼인 중이고 혼인신고일이 {marriage} 이후인지(혼인 7년 이내)",
                 {"all": [{"eq": [{"var": "marital_status"}, "혼인중"]},
                          {"gte": [{"var": "marriage_date"}, {"date": marriage}]}]})]},
        {"id": "②예비신혼부부", "label": "입주일 전일까지 혼인신고할 예비신혼부부", "conditions": [
            cond(f"{p}-T-prospective", "marital_status", ["입주일 전일까지 혼인신고를 하는 사람"],
                 "혼인 예정(예비신혼)인지 — 입주일 전일까지 혼인신고해야 함",
                 {"eq": [{"var": "marital_status"}, "예비신혼"]})]},
        {"id": "③-1한부모가족", "label": "6세 이하 자녀(태아 포함)를 둔 한부모가족", "conditions": [
            cond(f"{p}-T-singleparent", "marital_status/youngest_child_birth_date", [child6_quote],
                 f"한부모이고 6세 이하 자녀({child6} 이후 출생, 태아 포함)가 있는지",
                 {"all": [{"eq": [{"var": "marital_status"}, "한부모"]}, youngest_after(child6)]})]},
        {"id": "③-2지원대상한부모", "label": "「한부모가족 지원법」 지원대상 한부모가족", "conditions": [
            cond(f"{p}-T-supported", "is_supported_single_parent",
                 ["지원대상 한부모가족 : 「한부모가족 지원법 시행규칙」 제3조에 따라 여성가족부장관이 정하여 고시"],
                 "지원대상 한부모가족(한부모가족 증명서 발급 대상)인지",
                 {"eq": [{"var": "is_supported_single_parent"}, True]})]},
        {"id": "④유자녀혼인가구", "label": "6세 이하 자녀가 있는 혼인가구", "conditions": [
            cond(f"{p}-T-married-child", "marital_status/youngest_child_birth_date",
                 ["유자녀 혼인가구 : 6세 이하 자녀가 있는 혼인가구"],
                 f"혼인 중이고 6세 이하 자녀({child6} 이후 출생, 태아 포함)가 있는지(혼인기간 제한 없음)",
                 {"all": [{"eq": [{"var": "marital_status"}, "혼인중"]}, youngest_after(child6)]})]},
        {"id": "⑤신생아가구", "label": "2년 이내 출산(입양·태아 포함) 자녀가 있는 가구", "conditions": [
            cond(f"{p}-T-newborn", "youngest_child_birth_date", [newborn_quote],
                 f"{newborn} 이후 출생(태아는 출산예정일) 자녀가 있는지 — 혼인 여부와 무관. "
                 "입양 자녀는 입양일 기준(원문)이나 이 화면은 생년월일만 받는다",
                 youngest_after(newborn))]},
    ]
    if kind == "II":
        types.append({"id": "⑥혼인가구", "label": "공고일 현재 혼인한 가구", "conditions": [
            cond(f"{p}-T-married", "marital_status", ["혼인가구 : 공고일 현재 혼인한 가구"], "공고일 현재 혼인 중인지",
                 {"eq": [{"var": "marital_status"}, "혼인중"]})]})

    if kind == "I":
        ratio_rows = [r({"size": 1, "dual": False}, [90]), r({"size": 1, "dual": True},
                      **no_row("가구원수 1인인데 맞벌이(본인·배우자 모두 소득)로 입력했습니다. 입력을 확인해 주세요.")),
                      r({"size": 2, "dual": False}, [80]), r({"size": 2, "dual": True}, [100]),
                      r({"size": "3-6", "dual": False}, [70]), r({"size": "3-6", "dual": True}, [90])]
        income_quote = ["전년도 도시근로자 가구원수별 월평균소득의 70% 이하", "(본인 및 배우자 모두 소득이 있는 경우 90% 이하)"]
        income_note = "가구 월평균소득이 70%(1인 90%·2인 80%), 맞벌이 90%(1인 110%·2인 100%) 이하인지 — 수급자 등은 검증 면제"
        table_quote = ["3,432,027원", "4,693,016원", "5,717,900원", "6,161,541원", "6,528,890원", "6,934,384원",
                       "4,194,699원", "5,866,270원", "7,351,586원", "7,921,982원", "8,394,287원", "8,915,637원"]
        assets = [345000000, 379000000, 413000000]
        cars = [45420000, 49960000, 54510000]
        asset_quote = ["345,000,000원 이하", "379,000,000원 이하", "413,000,000원 이하",
                       "45,420,000원 이하", "49,960,000원 이하", "54,510,000원 이하"]
    else:
        ratio_rows = [r({"size": 1, "dual": False}, [150]), r({"size": 1, "dual": True},
                      **no_row("가구원수 1인인데 맞벌이(본인·배우자 모두 소득)로 입력했습니다. 입력을 확인해 주세요.")),
                      r({"size": 2, "dual": False}, [140]), r({"size": 2, "dual": True}, [210]),
                      r({"size": "3-6", "dual": False}, [130]), r({"size": "3-6", "dual": True}, [200])]
        income_quote = ["전년도 도시근로자 가구원수별 월평균소득의 130% 이하", "(본인 및 배우자 모두 소득이 있는 경우 200% 이하)"]
        income_note = "가구 월평균소득이 130%(1인 150%·2인 140%), 맞벌이 200%(1인 220%·2인 210%) 이하인지 — 수급자 등은 검증 면제"
        table_quote = ["5,720,045원", "8,212,778원", "10,618,958원", "11,442,863원", "12,125,081원", "12,878,142원",
                       "8,389,399원", "12,319,167원", "16,336,858원", "17,604,404원", "18,653,970원", "19,812,526원"]
        assets = [362000000, 396000000, 431000000]
        cars = None
        asset_quote = ["362,000,000원 이하", "396,000,000원 이하", "431,000,000원 이하"]
    ratio_rows.append(r({"size": "7+", "dual": "any"}, result="NO_ROW",
                        no_row={"code": "AMBIGUOUS_SOURCE", "detail": D_7PLUS}))
    exempt_quote = "수급자, 지원대상 한부모가족, 차상위계층은 소득·자산 검증 불필요 (예비신혼부부 제외)"
    conds = [
        cond(f"{p}-home", "home_ownership", ["무주택세대구성원으로서 신혼·신생아 매입임대주택"],
             "무주택세대구성원인지(세대 전원 무주택)", HOME),
        {"id": f"{p}-type", "field": "유형", "required": True,
         "source": {"quote": ["입주자격", "순위를 잘못 입력하여 신청하는 경우 변경이 불가하므로"]},
         "note": "신혼부부·예비신혼부부·한부모가족·지원대상 한부모·유자녀 혼인가구·신생아 가구"
                 + ("·혼인가구" if kind == "II" else "") + " 중 하나에 해당하는지(순위는 유형으로 정해짐)",
         "tracks": types},
        cond(f"{p}-income", "monthly_income", income_quote + [exempt_quote], income_note,
             {"any": [exempt, {"lte": [{"var": "monthly_income"},
                                       {"lookup": ["income_standard_rental", {"var": "household_size"},
                                                   {"term": "ratio"}]}]}]},
             table="newlywed_rental_income"),
        cond(f"{p}-assets", "total_assets", asset_quote[:1] + [exempt_quote],
             "총자산이 출생자녀 가산(1명 +10%p, 2명 이상 +20%p)을 반영한 기준 이내인지 — 수급자 등은 검증 면제",
             {"any": [exempt, {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}]},
             table="newlywed_rental_assets"),
    ]
    asset_rows = [r({"child": 0}, [assets[0]] + ([cars[0]] if cars else [])),
                  r({"child": 1}, [assets[1]] + ([cars[1]] if cars else [])),
                  r({"child": "2+"}, [assets[2]] + ([cars[2]] if cars else []))]
    tables = {
        "newlywed_rental_income": {
            "label": "신혼·신생아 매입임대 소득 비율: 가구원수×맞벌이 (1인 +20%p·2인 +10%p 가산 반영)",
            "columns": ["size", "dual"], "inputs": {"size": {"var": "household_size"}, "dual": {"var": "dual_income"}},
            "outputs": ["ratio"], "rows": ratio_rows, "source": {"quote": table_quote}},
        "newlywed_rental_assets": {
            "label": "신혼·신생아 매입임대 자산 기준: 출생자녀 수(태아 포함, 최대 2자녀)",
            "columns": ["child"], "inputs": {"child": {"fn": "child_bonus_count"}},
            "outputs": ["asset_limit"] + (["car_limit"] if cars else []), "rows": asset_rows,
            "source": {"quote": asset_quote}},
    }
    if cars:
        conds.append(cond(f"{p}-car", "car_value", ["자동차 4,542만원 이하", exempt_quote],
                          "자동차가액이 출생자녀 가산을 반영한 기준 이내인지 — 수급자 등은 검증 면제",
                          {"any": [exempt, {"lte": [{"var": "car_value", "unknown_values": ["확인불가"]},
                                                    {"term": "car_limit"}]}]}, table="newlywed_rental_assets"))
    if kind == "II":
        tables["newlywed_rental_assets"]["source"]["derivation"] = (
            "원문(p.4)은 문장에서 '자녀 1인 15% 완화(최대 2자녀 25%p)'라고 쓰고 표에서는 +10%p/+20%p와 금액(3억6,200만/3억9,600만/"
            "4억3,100만원)을 적는다. 판정은 표의 금액 리터럴을 쓴다. 자동차가액 개별 기준은 원문에 없다.")
    return {"신혼·신생아": {"conditions": conds}}, tables


# ------------------------------------------------------------------------------------------------
# 든든전세(비분양전환형) (LH04 p.3·4 / LH05 p.3·4) — 소득·자산 요건 없음
# ------------------------------------------------------------------------------------------------
def jeonse(nid):
    p = nid
    return {"일반": {"conditions": [
        cond(f"{p}-home", "home_ownership", ["무주택세대구성원으로 주민등록표등본상 거주하고 있는"],
             "무주택세대구성원인지(세대 전원 무주택)", HOME),
        cond(f"{p}-region", "residence_area", ["서울·인천·경기 (수도권 거주자만 신청 가능)",
                                              "주민등록표등본상 거주하고 있는 모집권역에 한하여 신청 가능"],
             "주민등록상 거주지가 수도권(서울·인천·경기)인지 — 신청은 거주하는 모집권역(시·도)에만 가능",
             {"in": [{"var": "residence_area"}, CAPITAL]}),
        cond(f"{p}-adult", "age", ["「민법」상 미성년자(19세 미만)는 공급 신청할 수 없습니다"],
             "만 19세 이상인지(미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청 가능)",
             {"any": [{"gte": [{"var": "age"}, 19]},
                      {"lte": [{"var": "age"}, 18], "review_if_true": {
                          "code": "SELF_REPORT_UNVERIFIED",
                          "detail": "미성년자는 원문의 예외(자녀가 있는 미성년 세대주, 형제자매를 부양하는 미성년 세대주 등)에 "
                                    "해당할 때만 신청 가능 — 이 화면은 예외 여부를 확인하지 않음"}}]}),
    ]}}, {}


PLAN = [
    dict(nid="N11", key="LH06", title="서울지역본부 청년매입임대주택(2차)", ann="2026-06-25", program="청년매입임대",
         build=lambda: youth_rental("N11", "1986.06.26. ~ 2007.06.25.", "1996.06.26."),
         notes=["공고일(2026.6.25)이 같은 청년 매입임대 공고(타지역 포함)에는 중복 신청할 수 없다(p.1).",
                "성별 전용 주택(남성·여성 전용)은 공급주택목록에서 확인 — 이 판정은 주택별 조건을 보지 않는다(p.1)."]),
    dict(nid="N12", key="LH07", title="서울지역본부 청년매입임대주택(3차)", ann="2026-09-17", program="청년매입임대",
         build=lambda: youth_rental("N12", "1986.09.18. ~ 2007.09.17.", "1996.09.18."),
         notes=["주민등록이 거주불명·말소 상태이면 신청할 수 없다(p.6·p.10) — 이 판정은 주민등록 상태를 묻지 않는다.",
                "성별 전용 주택(남성·여성 전용)은 공급주택목록에서 확인 — 이 판정은 주택별 조건을 보지 않는다."]),
    dict(nid="N13", key="LH01", title="서울지역본부 신혼·신생아 매입임대주택Ⅰ(2차)", ann="2026-06-25",
         program="신혼·신생아 매입임대Ⅰ",
         build=lambda: newlywed_rental("N13", "I", "혼인신고일이 2019.6.25. ~ 2026.6.25", "2019-06-25", "2019-06-26",
                                       "2024-06-25", "’19.6.26 이후 출생한 자녀 및 태아", "’24.6.25이후 출생‧입양한 자녀 및 태아"),
         notes=["배우자가 국내에 거주하지 않는 재외국민이거나 외국인 등록을 하지 않은 외국인이면 신청할 수 없다(p.3).",
                "같은 지자체(시·군·구)의 기계약자는 신청할 수 없다(p.1)."]),
    dict(nid="N14", key="LH03", title="서울지역본부 신혼·신생아 매입임대주택Ⅰ(3차)", ann="2026-09-17",
         program="신혼·신생아 매입임대Ⅰ",
         build=lambda: newlywed_rental("N14", "I", "혼인신고일이 2019.9.17~ 2026.9.17", "2019-09-17", "2019-09-18",
                                       "2024-09-17", "‘19.9.18이후 출생", "‘24.9.17이후 출생"),
         notes=["주민등록이 거주불명·말소 상태이면 신청할 수 없다 — 이 판정은 주민등록 상태를 묻지 않는다.",
                "배우자가 국내에 거주하지 않는 재외국민이거나 외국인 등록을 하지 않은 외국인이면 신청할 수 없다."]),
    dict(nid="N15", key="LH02", title="서울지역본부 신혼·신생아 매입임대주택Ⅱ 전세형(2차)", ann="2026-06-25",
         program="신혼·신생아 매입임대Ⅱ(전세형)",
         build=lambda: newlywed_rental("N15", "II", "혼인신고일이 2019.6.25. ~ 2026.6.25", "2019-06-25", "2019-06-26",
                                       "2024-06-25", "’19.6.26이후 출생", "’24.6.25이후 출생"),
         notes=["같은 날 공고된 신혼·신생아 매입임대Ⅰ과 중복 신청 시 처리 기준은 공고문 확인(p.1).",
                "배우자가 국내에 거주하지 않는 재외국민이거나 외국인 등록을 하지 않은 외국인이면 신청할 수 없다(p.3)."]),
    dict(nid="N16", key="LH04", title="서울지역본부 든든전세주택(비분양전환형, 1차)", ann="2026-05-22",
         program="든든전세(비분양전환형)", build=lambda: jeonse("N16"),
         notes=["소득·자산 요건이 없다. 선정은 신생아 가구·자녀 수 배점 순이며 동점이면 추첨(p.3).",
                "주민등록상 거주하는 모집권역(서울·인천·경기 중 하나)에만 신청할 수 있다(p.3)."]),
    dict(nid="N17", key="LH05", title="서울지역본부 든든전세주택(비분양전환형, 2차)", ann="2026-10-01",
         program="든든전세(비분양전환형)", build=lambda: jeonse("N17"),
         notes=["소득·자산 요건이 없다. 선정은 신생아 가구·자녀 수 배점 순이며 동점이면 추첨(p.3).",
                "주민등록이 거주불명·말소 상태이면 신청할 수 없다(p.8·p.11) — 이 판정은 주민등록 상태를 묻지 않는다."]),
]

ANCHORS = {"청년": ("입주자격", 3), "대학생": ("입주자격", 3), "취업준비생": ("입주자격", 3),
           "신혼·신생아": ("입주자격", 3), "일반": ("입주자격", 3)}


def pdf_for(key):
    index = json.loads((ROOT / "docs" / "notice-analysis" / "index.json").read_text(encoding="utf-8"))
    return ROOT / next(x["file"] for x in index if x["key"] == key)


def walk(conditions):
    for c in conditions:
        yield c
        for t in c.get("tracks", []):
            yield from walk(t["conditions"])


def main():
    for plan in PLAN:
        pdf = pdf_for(plan["key"])
        from pypdf import PdfReader
        import logging
        logging.disable(logging.CRITICAL)
        pages = sv.extract_pages(pdf)
        layers, tables = plan["build"]()
        missing = []
        for layer, ldoc in layers.items():
            text, hint = ANCHORS[layer]
            anchor = locate(pages, text, hint) or hint
            for c in walk(ldoc["conditions"]):
                place_quotes(c["source"], pages, anchor, f"{layer}/{c['id']}", missing)
        for name, t in tables.items():
            place_quotes(t["source"], pages, 4 if "rental" in name else 3, f"table:{name}", missing)
        doc = {
            "notice_id": plan["nid"], "title": plan["title"], "announcement_date": plan["ann"],
            "issuer": "LH", "program": plan["program"],
            "version": 1, "valid_from": plan["ann"], "supersedes": None,
            "source": {"document": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "pages": len(pages)},
            "review": {"status": "DRAFT", "note": "C4a 생성(tools/gen_c4_lh.py). 원문 표 수치는 손으로 옮김. 독립 검토 전.",
                       "log": []},
            "notes": plan["notes"], "unsupported_layers": [], "tables": tables, "layers": layers,
        }
        out = ROOT / "rules" / "notices" / f"{plan['nid']}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(plan["nid"], plan["title"], list(layers), "MISSING", len(missing))
        for m in missing:
            print("   -", m)


if __name__ == "__main__":
    main()
