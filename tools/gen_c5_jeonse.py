# -*- coding: utf-8 -*-
"""C5b: SH 장기전세·장기전세2(미리내집) 4건(N23~N26). 사용: python tools/gen_c5_jeonse.py   (재실행 안전)

| ID  | 원문 | 사업 | 공고일 |
| N23 | SH25 | 제7차 장기전세주택2(미리내집) | 2026-04-24 |
| N24 | SH26 | 제8차 장기전세주택2(미리내집) | 2026-08-21 |
| N25 | SH23 | 제49차 장기전세주택 | 2025-12-15 (이전 연도 소득표) |
| N26 | SH24 | 제50차 장기전세주택 | 2026-04-27 |

주택형 축(S3): 소득 기준이 **신청 주택 면적**에 따라 달라 변형 계층 `기본계층(주택형)`으로 나눈다.
- 장기전세2(SH25 p.13·16·17, SH26 p.13·16·17): 신혼부부·예비신혼부부, 60㎡ 이하 120%(맞벌이 180%) / 60㎡ 초과 150%(200%),
  2~5인 금액만 원문에 있음. 자산 662/728/794M·자동차 45.42/49.96/54.51M. 서울 거주, 5년 계속 무소유. SH26은 주거약자형(①~⑦).
- 장기전세(SH23·SH24 p.6~7·20·23·24): 순위가 여러 개지만 자격 판정에는 면적별 **최대 상한**만 남는다 — 60㎡ 이하는 3·4순위·매입형의
  105%(맞벌이 140%, 출생자녀 115/125%), 60㎡ 초과(85㎡ 초과 포함)는 150%(200%, 160/170%). 순위(청약저축 회차·청약예금·자치구)는
  자격이 아니라 접수 순서라 판정하지 않고 유의사항으로 안내. 출생자녀 가산은 맞벌이 기준과 중복하지 않는다.
- 소득 상한은 결정표에 원문 금액을 직접 적는다(공유 기준표 미사용 — 사업·연도 간 누수 방지). 원문 표의 빈칸(1인+자녀, 1인 맞벌이 등)은
  입력 모순, 표에 없는 가구원수(장기전세2 6인 이상, 장기전세 7인 이상)는 MANUAL_REVIEW.
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import source_verify as sv  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C3, C4, C5 = _load("gen_c3_layers"), _load("gen_c4_lh"), _load("gen_c5_housing_weak")
cond, r, locate, place_quotes = C3.cond, C3.r, C3.locate, C3.place_quotes
HOME = C4.HOME
WEAK_TYPES = C5.WEAK_TYPES


def incons(detail):
    return {"result": "NO_ROW", "no_row": {"code": "INPUT_INCONSISTENT", "detail": detail}}


def ambiguous(detail):
    return {"result": "NO_ROW", "no_row": {"code": "AMBIGUOUS_SOURCE", "detail": detail}}


# --- 장기전세2 소득 상한(원문 p.16·p.17 금액) --------------------------------------------------------
J2 = {"60이하": dict(base={2: 7039524, 3: 9802115, 4: 10562642, 5: 11192382},
                    dual={2: 10559286, 3: 14703172, 4: 15843964, 5: 16788573}, ratio=("120%", "180%")),
      "60초과": dict(base={2: 8799405, 3: 12252644, 4: 13203303, 5: 13990478},
                    dual={2: 11732540, 3: 16336858, 4: 17604404, 5: 18653970}, ratio=("150%", "200%"))}


def j2_income_rows(t):
    rows = [r({"size": 1, "dual": "any"}, **incons(
        "신혼부부·예비신혼부부 가구원수는 2인 이상입니다(예비신혼부부는 혼인으로 구성될 세대). 가구원수를 확인해 주세요."))]
    for size in (2, 3, 4, 5):
        rows += [r({"size": size, "dual": False}, [t["base"][size]]), r({"size": size, "dual": True}, [t["dual"][size]])]
    rows.append(r({"size": "6+", "dual": "any"}, **ambiguous("원문 소득표에 6인 이상 가구 금액이 없습니다(2~5인만 표기).")))
    return rows


# --- 장기전세 소득 상한(SH23·SH24 p.23 금액): 기본 / 출생자녀 1명(+10%p) / 2명 이상·1명+기존 미성년(+20%p) / 맞벌이 --------
JS = {
    "N25": {"60이하": dict(base=[3778072, 5750853, 8008322, 9006992, 9482600, 10219740],
                           c1=[None, 6298553, 8771019, 9864801, 10385705, 11193049],
                           c2=[None, None, 9533716, 10722610, 11288810, 12166358],
                           dual=[None, 7667804, 10677762, 12009323, 12643467, 13626320], ratio="105%(맞벌이 140%)"),
            "60초과": dict(base=[5397246, 8215505, 11440460, 12867132, 13546572, 14599629],
                           c1=[None, 8763205, 12203157, 13724941, 14449677, 15572938],
                           c2=[None, None, 12965854, 14582750, 15352782, 16546246],
                           dual=[None, 10954006, 15253946, 17156176, 18062096, 19466172], ratio="150%(맞벌이 200%)"),
            "assets": [640000000, 704000000, 768000000], "cars": [45630000, 50200000, 54760000]},
    "N26": {"60이하": dict(base=[4004031, 6159584, 8576850, 9242312, 9793334, 10401576],
                           c1=[None, 6746211, 9393693, 10122532, 10726033, 11392202],
                           c2=[None, None, 10210536, 11002753, 11658731, 12382829],
                           dual=[None, 8212778, 11435801, 12323083, 13057779, 13868768], ratio="105%(맞벌이 140%)"),
            "60초과": dict(base=[5720045, 8799405, 12252644, 13203303, 13990478, 14859395],
                           c1=[None, 9386032, 13069486, 14083523, 14923176, 15850021],
                           c2=[None, None, 13886329, 14963743, 15855875, 16840647],
                           dual=[None, 11732540, 16336858, 17604404, 18653970, 19812526], ratio="150%(맞벌이 200%)"),
            "assets": [662000000, 728000000, 794000000], "cars": [45420000, 49960000, 54510000]},
}


def js_income_rows(t):
    rows = []
    for size in range(1, 7):
        i = size - 1
        # 맞벌이는 출생자녀 가산과 중복 적용하지 않는다(맞벌이 열) — 1인 맞벌이는 원문 빈칸
        rows.append(r({"size": size, "child": "any", "dual": True},
                      [t["dual"][i]]) if t["dual"][i] else r({"size": size, "child": "any", "dual": True}, **incons(
                          "가구원수 1인인데 맞벌이로 입력했습니다(원문 표의 1인 맞벌이 칸은 비어 있음). 입력을 확인해 주세요.")))
        rows.append(r({"size": size, "child": 0, "dual": False}, [t["base"][i]]))
        rows.append(r({"size": size, "child": 1, "dual": False}, [t["c1"][i]]) if t["c1"][i] else r(
            {"size": size, "child": 1, "dual": False}, **incons("가구원수 1인인데 출생자녀 가산 대상 자녀가 있습니다(원문 표 빈칸).")))
        rows.append(r({"size": size, "child": "2+", "dual": False}, [t["c2"][i]]) if t["c2"][i] else r(
            {"size": size, "child": "2+", "dual": False},
            **incons(f"가구원수 {size}인인데 출생자녀 가산 대상 자녀가 2명 이상입니다(원문 표 빈칸).")))
    rows.append(r({"size": "7+", "child": "any", "dual": "any"},
                  **ambiguous("원문 소득표에 7인 이상 가구 금액이 없습니다(1~6인만 표기).")))
    return rows


def money(n):
    return f"{n:,}원"


def common(nid, quotes, residence_check, residence_note):
    return [
        cond(f"{nid}-home", "home_ownership", [quotes["home"]], "무주택세대구성원인지(세대 전원 무주택)", HOME),
        cond(f"{nid}-region", "residence_area", [quotes["region"]], residence_note, residence_check),
        cond(f"{nid}-adult", "age", [quotes["adult"]],
             "만 19세 이상인지(미성년자는 자녀가 있거나 형제자매를 부양하는 미성년 세대주 등 예외에 해당할 때만 신청 가능)",
             {"any": [{"gte": [{"var": "age"}, 19]},
                      {"lte": [{"var": "age"}, 18], "review_if_true": {
                          "code": "SELF_REPORT_UNVERIFIED",
                          "detail": "미성년자는 원문의 예외(자녀가 있는 미성년 세대주 등)에 해당할 때만 신청 가능 — 예외 여부는 확인하지 않음"}}]}),
    ]


def weak_cond(nid, quote):
    return cond(f"{nid}-W-weak", "housing_weak_type/age", [quote],
                "신청자 본인이 주거약자인지 — 65세 이상 고령자이거나 장애인, 상이등급 1~7급 국가유공자·보훈보상대상자·준군경, "
                "5·18 부상자(장해 1~14급), 고엽제후유의증환자(경도 이상)",
                {"any": [{"gte": [{"var": "age"}, 65]}, {"in": [{"var": "housing_weak_type"}, WEAK_TYPES]}]})


def assets_table(assets, cars, quotes):
    return {"label": "자산·자동차 기준: 2023.3.28. 이후 출생 자녀(태아 포함) — 1명 / 2명 이상 또는 1명+기존 미성년 자녀",
            "columns": ["child"], "inputs": {"child": {"fn": "child_bonus_count"}},
            "outputs": ["asset_limit", "car_limit"],
            "rows": [r({"child": 0}, [assets[0], cars[0]]), r({"child": 1}, [assets[1], cars[1]]),
                     r({"child": "2+"}, [assets[2], cars[2]])],
            "source": {"quote": quotes}}


def jeonse2(nid, dates, quotes, weak_quote=None):
    """장기전세2(미리내집): 신혼부부(혼인 7년, SH 관행 날짜)·예비신혼부부."""
    seoul = {"eq": [{"var": "residence_area"}, "서울특별시"]}
    types = {"id": f"{nid}-type", "field": "유형", "required": True, "source": {"quote": [quotes["type"]]},
             "note": "신혼부부(혼인 7년 이내) 또는 예비신혼부부인지",
             "tracks": [
                 {"id": "신혼부부", "label": "혼인신고 후 7년 이내", "conditions": [
                     cond(f"{nid}-T-newlywed", "marital_status/marriage_date", [quotes["marriage"]],
                          f"혼인 중이고 혼인신고일이 {dates['marriage']} 이후(당일 포함)인지",
                          {"all": [{"eq": [{"var": "marital_status"}, "혼인중"]},
                                   {"gte": [{"var": "marriage_date"}, {"date": dates["marriage"]}]}]})]},
                 {"id": "예비신혼부부", "label": "입주 전까지 혼인 사실을 증명할 예비신혼부부", "conditions": [
                     cond(f"{nid}-T-prospective", "marital_status", [quotes["prospective"]],
                          "혼인 예정(예비신혼)인지 — 입주 전까지 혼인 사실을 증명해야 함",
                          {"eq": [{"var": "marital_status"}, "예비신혼"]})]}]}
    five = cond(f"{nid}-5y", "owned_home_in_5y", [quotes["five"]],
                f"신청자와 배우자(예비배우자)가 5년 동안({dates['five']} 이후) 계속 주택을 소유하지 않았는지",
                {"eq": [{"var": "owned_home_in_5y"}, False]})
    layers, tables = {}, {}
    for band, label in (("60이하", "전용 60㎡ 이하"), ("60초과", "전용 60㎡ 초과")):
        t = J2[band]
        tname = f"j2_income_{band}"
        tables[tname] = {
            "label": f"장기전세2 소득 상한({label}): 가구원수×맞벌이 — {t['ratio'][0]}(맞벌이 {t['ratio'][1]})",
            "columns": ["size", "dual"], "inputs": {"size": {"var": "household_size"}, "dual": {"var": "dual_income"}},
            "outputs": ["limit"], "rows": j2_income_rows(t),
            "source": {"quote": [money(v) for v in t["base"].values()] + [money(v) for v in t["dual"].values()]}}
        income = cond(f"{nid}-income", "monthly_income", [quotes[f"income_{band}"]],
                      f"해당 세대 월평균소득이 {t['ratio'][0]}(맞벌이 {t['ratio'][1]}) 이하인지 — {label} 주택 신청 기준",
                      {"lte": [{"var": "monthly_income"}, {"term": "limit"}]}, table=tname)
        conds = common(nid, quotes, seoul, "공고일 현재 서울특별시에 거주하는지") + [
            types, income,
            cond(f"{nid}-assets", "total_assets", [quotes["assets"]], "총자산이 출생자녀 가산을 반영한 기준 이내인지",
                 {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table="j2_assets"),
            cond(f"{nid}-car", "car_value", [quotes["car"]], "자동차가액이 출생자녀 가산을 반영한 기준 이내인지",
                 {"lte": [{"var": "car_value", "unknown_values": ["확인불가"]}, {"term": "car_limit"}]}, table="j2_assets"),
            five]
        layers[f"신혼부부({label})"] = {"conditions": json.loads(json.dumps(conds))}
        if band == "60이하" and weak_quote:
            layers["신혼부부(주거약자형·전용 60㎡ 이하)"] = {
                "conditions": json.loads(json.dumps(conds)) + [weak_cond(nid, weak_quote)]}
    tables["j2_assets"] = assets_table([662000000, 728000000, 794000000], [45420000, 49960000, 54510000],
                                       ["66,200만원", "72,800만원", "79,400만원", "4,542만원", "4,996만원", "5,451만원"])
    return layers, tables


def priority_types(nid, minor_date, with_elderly, q):
    """서울시 매입형 60㎡ 이하 우선공급(SH23 p.27~28 / SH24 p.28~29): 일반공급 자격 + 유형별 조건."""
    out = {}
    if with_elderly:
        out["고령자"] = cond(f"{nid}-P-elderly", "age/household_size/marital_status", [q["elderly"]],
                          "만 65세 이상이고 2인 이하 무주택 세대(신청자와 배우자)인지",
                          {"all": [{"gte": [{"var": "age"}, 65]},
                                   {"any": [{"lte": [{"var": "household_size"}, 1]},
                                            {"all": [{"eq": [{"var": "household_size"}, 2]},
                                                     {"eq": [{"var": "marital_status"}, "혼인중"]}]},
                                            {"all": [{"eq": [{"var": "household_size"}, 2]},
                                                     {"ne": [{"var": "marital_status"}, "혼인중"]}],
                                             "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                                                "detail": "원문의 2인 기준은 '신청자와 신청자의 배우자' — 배우자가 아닌 "
                                                                          "세대원과 2인이면 해당 여부가 원문에서 불명확"}}]}]})
    out["장애인"] = cond(f"{nid}-P-disabled", "housing_weak_type/disabled_spouse_qualifies", [q["disabled"]],
                      "본인이 장애인등록증을 교부받았거나, 배우자가 지적·정신장애인 또는 장애 정도가 심한 뇌병변장애인인지",
                      {"any": [{"eq": [{"var": "housing_weak_type"}, "장애인"]},
                               {"eq": [{"var": "disabled_spouse_qualifies"}, True]}]})
    out["노부모부양"] = cond(f"{nid}-P-parent", "supports_elderly_parent_1y", [q["parent"]],
                         "만 65세 이상 직계존속(배우자의 직계존속 포함)을 같은 등본에서 1년 이상 부양하고, 피부양자와 그 배우자도 무주택인지",
                         {"eq": [{"var": "supports_elderly_parent_1y"}, True]})
    out["2자녀이상"] = cond(f"{nid}-P-children", "children_birth_dates", [q["children"]],
                         f"미성년 자녀({minor_date} 이후 출생, 태아 포함) 2명 이상이 같은 등본에 있는지 "
                         "(조부모·손자녀로만 구성된 세대의 손자녀도 인정 — 그 경우 손자녀를 자녀 칸에 입력)",
                         {"gte": [{"fn": "children_on_or_after", "args": [{"date": minor_date}]}, 2]})
    out["국가유공자"] = cond(f"{nid}-P-veteran", "veteran_priority_notified", [q["veteran"]],
                          "국가보훈부가 우선공급 대상자로 선정·통보한 국가유공자 등(유족 포함)인지",
                          {"eq": [{"var": "veteran_priority_notified"}, True],
                           "review_if_true": {"code": "SELF_REPORT_UNVERIFIED",
                                              "detail": "국가보훈부가 선정·통보한 사람만 대상 — 통보 여부와 순위는 이 화면에서 확인할 수 없음"}})
    return out


def jeonse(nid, quotes, weak_quote, income):
    """장기전세: 면적별 최대 소득 상한 + 출생자녀 가산(맞벌이와 중복 없음), 서울(상계장암은 의정부 포함).
    income: 면적대별 소득 상한 원문 금액(JS[공고]) — 공고마다 기준 연도가 달라 파라미터로 받는다."""
    data = income
    residence = {"any": [{"eq": [{"var": "residence_area"}, "서울특별시"]},
                         {"eq": [{"var": "residence_area"}, "의정부시"],
                          "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                             "detail": "의정부시 거주자는 상계장암지구 주택을 신청할 때만 포함된다(원문) — 신청 단지를 확인해야 함"}}]}
    layers, tables = {}, {}
    for band, label in (("60이하", "전용 60㎡ 이하"), ("60초과", "전용 60㎡ 초과")):
        t = data[band]
        tname = f"js_income_{band}"
        tables[tname] = {
            "label": f"장기전세 소득 상한({label}): 가구원수×출생자녀×맞벌이 — {t['ratio']}, 출생자녀 +10%p/+20%p(맞벌이와 중복 없음)",
            "columns": ["size", "child", "dual"],
            "inputs": {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"}, "dual": {"var": "dual_income"}},
            "outputs": ["limit"], "rows": js_income_rows(t),
            "source": {"quote": [money(v) for v in t["base"]] + [money(v) for v in t["dual"] if v]}}
        conds = common(nid, quotes, residence, "공고일 현재 서울특별시에 거주하는지(상계장암지구는 의정부시 거주자 포함)") + [
            cond(f"{nid}-income", "monthly_income", [quotes["income"]],
                 f"해당 세대 월평균소득이 {t['ratio']} 이하인지 — {label} 주택 기준(순위별 상한 중 최대; 출생자녀 가산 반영)",
                 {"lte": [{"var": "monthly_income"}, {"term": "limit"}]}, table=tname),
            cond(f"{nid}-assets", "total_assets", [quotes["assets"]], "총자산이 출생자녀 가산을 반영한 기준 이내인지",
                 {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table="js_assets"),
            cond(f"{nid}-car", "car_value", [quotes["car"]], "자동차가액이 출생자녀 가산을 반영한 기준 이내인지",
                 {"lte": [{"var": "car_value", "unknown_values": ["확인불가"]}, {"term": "car_limit"}]}, table="js_assets")]
        layers[f"일반({label})"] = {"conditions": json.loads(json.dumps(conds))}
        if band == "60이하":
            layers["일반(주거약자형·전용 60㎡ 이하)"] = {"conditions": json.loads(json.dumps(conds)) + [weak_cond(nid, weak_quote)]}
            for kind, extra in priority_types(nid, quotes["minor_date"], quotes["with_elderly"], quotes["priority"]).items():
                layers[f"일반(우선공급·{kind})"] = {"conditions": json.loads(json.dumps(conds)) + [extra]}
    a, c = data["assets"], data["cars"]
    tables["js_assets"] = assets_table(a, c, [f"{a[0] // 10000:,}만원", f"{a[1] // 10000:,}만원", f"{a[2] // 10000:,}만원",
                                              f"{c[0] // 10000:,}만원", f"{c[1] // 10000:,}만원", f"{c[2] // 10000:,}만원"])
    return layers, tables


Q_J2 = dict(home="현재 서울특별시에 거주하는 무주택세대구성원", region="현재 서울특별시에 거주하는 무주택세대구성원",
            adult="민법상 미성년자(만19세 미만)는 공급 신청 할 수 없습니다",
            type="신혼부부는 ①-㉮와 ②~③과 ⑤를, 예비신혼부부는 ①-㉯와 ②~⑤를 모두 갖추어야 함",
            prospective="혼인을 계획 중이며 해당 주택의 입주전까지",
            income_60이하="(전용면적 60㎡ 이하) 해당 무주택세대구성원", income_60초과="(전용면적 60㎡ 초과) 해당 무주택세대구성원",
            assets="⑷ ⑴,⑵,⑶에 해당하지 않는 경우: 66,200만원", car="⑷ ⑴,⑵,⑶에 해당하지 않는 경우: 4,542만원")
Q_JS = dict(home="성년자인 무주택세대구성원으로서", region="현재 서울특별시에 거주하는 성년자인 무주택세대구성원",
            adult="민법상 미성년자(만19세 미만)·외국인은 신청할 수 없습니다",
            income="신청주택 면적 별로 각각 아래 기준 이하인 자")

PLAN = [
    dict(nid="N23", key="SH25", title="SH 제7차 장기전세주택2(미리내집)", ann="2026-04-24", program="SH 장기전세주택2(미리내집)",
         template="jeonse2", params=dict(
             dates=dict(marriage="2019-04-25", five="2021-04-25"),
             quotes=dict(Q_J2, marriage="혼인 신고를 한 날로부터 7년 이내(2019. 4. 25. 이후",
                                    five="5년 동안(2021. 4. 25.이후) 계속하여 주택을 소유하지 않았을 것")),
         unsupported=[],
         notes=["신청 주택의 전용면적(60㎡ 이하/초과)에 따라 소득 기준이 다르다 — 신청할 주택형의 계층을 고르세요(p.13).",
                "선정은 가점(서울 거주기간·청약통장)·감점 순이며 신규공급 물량의 40%는 소득 우선배정 — 이 판정과 무관(p.19)."]),
    dict(nid="N24", key="SH26", title="SH 제8차 장기전세주택2(미리내집)", ann="2026-08-21", program="SH 장기전세주택2(미리내집)",
         template="jeonse2", params=dict(
             dates=dict(marriage="2019-08-22", five="2021-08-22"),
             quotes=dict(Q_J2, marriage="혼인 신고를 한 날로부터 7년 이내(2019. 8. 22. 이후",
                                    five="5년 동안(2021.8.22. 이후) 계속하여 주택을 소유하지 않았을 것"),
             weak_quote="주거약자형 주택 신청자는 ‘가.신청자격’에 더하여 아래 신청자격 ①~⑦ 중 한 개 이상의"),
         unsupported=[],
         notes=["신청 주택의 전용면적(60㎡ 이하/초과 — 85㎡ 초과 주택도 60㎡ 초과 기준)에 따라 소득 기준이 다르다(p.13).",
                "주거약자형 주택은 신청자 본인이 주거약자여야 하며, 일반 자격으로 신청하면 주거약자형으로 공급되지 않는다(p.11)."]),
    dict(nid="N25", key="SH23", title="SH 제49차 장기전세주택", ann="2025-12-15", program="SH 장기전세주택",
         template="jeonse", params=dict(
             quotes=dict(Q_JS, assets="가액 합산: 64,000만원 이하", car="보건복지부장관이 정하는 금액: 4,563만원 이하",
                                          minor_date="2006-12-16", with_elderly=False, priority=dict(
                                              disabled="「장애인복지법」 제32조에 따라 장애인등록증이 교부된 사람",
                                              parent="[1960.12.15.이전 출생(당일 포함)]의 직계존속(배우자의 직계존속 포함)을",
                                              children="민법상 미성년자(2006.12.16.이후 출생, 당일 포함)인 2명 이상의 자녀",
                                              veteran="국가보훈부에서 우선공급 대상자로 선정하여 통보한 사람")),
             weak_quote="주거약자형 주택 신청자는 ‘가. 신청자격’에 더하여 아래 신청자격 ①-⑦ 중 한 개 이상의 자격을 추가로",
             income=JS["N25"]),
         unsupported=[],
         notes=["이 공고는 2025.12.15. 공고라 소득 기준이 이전 연도 도시근로자 소득표다(3인 105% 8,008,322원).",
                "순위(청약저축 회차, 85㎡ 초과 청약예금, 매입형 자치구)는 자격이 아니라 접수 순서다 — 선순위 접수가 마감되면 후순위는 "
                "접수 자체가 없을 수 있다(p.6~7).", "상계장암지구는 의정부시 거주자도 신청할 수 있다(p.20)."]),
    dict(nid="N26", key="SH24", title="SH 제50차 장기전세주택", ann="2026-04-27", program="SH 장기전세주택",
         template="jeonse", params=dict(
             quotes=dict(Q_JS, assets="가액 합산: 66,200만원 이하", car="보건복지부장관이 정하는 금액: 4,542만원 이하",
                                          minor_date="2007-04-28", with_elderly=True, priority=dict(
                                              elderly="만65세 이상[1961.04.27.이전 출생(당일 포함)]인 2인 이하 무주택 세대구성원",
                                              disabled="「장애인복지법」 제32조에 따라 장애인등록증이 교부된 사람",
                                              parent="[1961.4.27.이전 출생(당일 포함)]의 직계존속(배우자의 직계존속 포함)을",
                                              children="민법상 미성년자(2007.4.28.이후 출생, 당일 포함)인 2명 이상의 자녀",
                                              veteran="국가보훈부에서 우선공급 대상자로 선정하여 통보한 사람")),
             weak_quote="주거약자형 주택 신청자는 ‘가. 신청자격’에 더하여 아래 신청자격 ①-⑦ 중 한 개 이상의 자격을 추가로",
             income=JS["N26"]),
         unsupported=[],
         notes=["순위(청약저축 회차, 85㎡ 초과 청약예금, 매입형 자치구)는 자격이 아니라 접수 순서다 — 선순위 접수가 마감되면 후순위는 "
                "접수 자체가 없을 수 있다(p.6~7).", "상계장암지구는 의정부시 거주자도 신청할 수 있다(p.20)."]),
]
ANCHOR = {"N23": 13, "N24": 13, "N25": 20, "N26": 20}


# 템플릿(사업별 규칙 생성 함수) — 공고별 값은 PLAN의 params(파라미터 시트, P1 docs/09 §5)
BUILDERS = {"jeonse2": jeonse2, "jeonse": jeonse}


def make_doc(plan, pdf, pages, anchor=None):
    """PLAN 항목(또는 같은 모양의 파라미터 시트) + 원문 쪽 텍스트 → 공고 규칙 문서, 찾지 못한 인용문 목록."""
    layers, tables = BUILDERS[plan["template"]](plan["nid"], **plan["params"])
    missing = []
    anchor = anchor or ANCHOR.get(plan["nid"]) or (13 if plan["template"] == "jeonse2" else 20)
    for layer, ldoc in layers.items():
        for c in C4.walk(ldoc["conditions"]):
            if isinstance(c["source"].get("quote", [None])[0], str) and "page" not in c["source"]:
                place_quotes(c["source"], pages, anchor, f"{layer}/{c['id']}", missing)
    for name, t in tables.items():
        place_quotes(t["source"], pages, anchor + 3, f"table:{name}", missing)
    doc = {
        "notice_id": plan["nid"], "title": plan["title"], "announcement_date": plan["ann"],
        "issuer": "SH", "program": plan["program"], "version": 1, "valid_from": plan["ann"], "supersedes": None,
        "source": {"document": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "pages": len(pages)},
        "review": {"status": "DRAFT", "note": "C5b 생성(tools/gen_c5_jeonse.py). 원문 표 수치는 손으로 옮김. 독립 검토 전.",
                   "log": []},
        "notes": plan["notes"], "unsupported_layers": plan["unsupported"], "tables": tables, "layers": layers,
    }
    return doc, missing


def main():
    for plan in PLAN:
        pdf = C4.pdf_for(plan["key"])
        doc, missing = make_doc(plan, pdf, sv.extract_pages(pdf))
        out = ROOT / "rules" / "notices" / f"{plan['nid']}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(plan["nid"], plan["title"], list(doc["layers"]), "MISSING", len(missing))
        for m in missing:
            print("   -", m)


if __name__ == "__main__":
    main()
