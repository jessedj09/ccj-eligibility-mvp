# -*- coding: utf-8 -*-
"""C4b: SH 매입임대·장기미임대 5건(N18~N22)을 만든다. 사용: python tools/gen_c4_sh.py   (재실행 안전)

| ID  | 원문 | 사업 | 공고일 |
| N18 | SH21 | SH 신혼·신생아 매입임대Ⅰ | 2026-09-30 |
| N19 | SH22 | SH 신혼·신생아 매입임대Ⅱ | 2026-09-30 |
| N20 | SH18 | 일반주택형 미리내집(신혼·신생아 매입임대Ⅱ) | 2026-08-14 |
| N21 | SH19 | 일반주택형 미리내집(공공한옥) 잔여세대 | 2026-08-24 |
| N22 | SH20 | 장기미임대 매입임대 | 2026-08-28 |

SH가 LH와 다른 점(원문 확인):
- 기간 기준일은 공고일−N년의 **다음 날**(예: 공고 9.30 → 혼인 '19.10.1~, 신생아 '24.10.1 이후). 원문 날짜 리터럴을 쓴다.
- 소득표는 2~5인 금액만 싣고(1인 칸 없음 — 장기미임대만 1인 있음) 6인 이상은 "5인 금액 + 1인당 가산액"으로 정한다.
  → 공유 소득 기준표에 넣지 않고 결정표 출력에 금액을 직접 적는다(사업 간 누수 방지 — C4a 사고). 6인 이상 금액은 원문 규칙으로
  계산하고 `source.derivation`에 적는다. 1인은 원문에 금액이 없어 MANUAL_REVIEW.
- 장기미임대는 소득이 순위(1순위 130% 이하 / 2순위 초과)에만 쓰여 자격요건이 아니다 — 소득 조건을 두지 않는다.
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


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


C3 = _load("gen_c3_layers")
C4 = _load("gen_c4_lh")
cond, r, no_row, locate, place_quotes = C3.cond, C3.r, C3.no_row, C3.locate, C3.place_quotes
HOME, WELFARE_EXEMPT = C4.HOME, C4.WELFARE_EXEMPT
MAX_SIZE = 15     # 6인~15인은 원문 규칙으로 계산, 16인 이상은 표에 없음(현실적으로 없음)


def income_rows(base, adder, base_dual, adder_dual):
    """원문 2~5인 금액 + 6인 이상 '5인 + 1인당 가산액'. 1인은 원문에 없음."""
    rows = [r({"size": 1, "dual": "any"}, result="NO_ROW", no_row={
        "code": "AMBIGUOUS_SOURCE",
        "detail": "원문 소득표에 1인 가구 금액이 없습니다(2~5인만 표기, 가구원수에는 태아 포함). 가구원수를 확인하거나 SH에 문의하세요."})]
    for size in range(2, MAX_SIZE + 1):
        for dual, b, a in ((False, base, adder), (True, base_dual, adder_dual)):
            amount = b[size] if size <= 5 else b[5] + a * (size - 5)
            rows.append(r({"size": size, "dual": dual}, [amount]))
    rows.append(r({"size": f"{MAX_SIZE + 1}+", "dual": "any"}, result="NO_ROW",
                  no_row={"code": "AMBIGUOUS_SOURCE", "detail": f"{MAX_SIZE + 1}인 이상 가구는 판정 범위 밖입니다."}))
    return rows


INCOME_I = dict(  # SH21 p.16: 70%(배우자 소득 있는 경우 90%) — 2인은 +10%p 반영 금액
    base={2: 4693016, 3: 5717900, 4: 6161541, 5: 6528890}, adder=405494,
    base_dual={2: 5866270, 3: 7351586, 4: 7921982, 5: 8394287}, adder_dual=521350)
INCOME_II = dict(  # SH22 p.10 / SH18 p.13 / SH19 p.12: 130%(배우자 소득 있는 경우 200%)
    base={2: 8212778, 3: 10618958, 4: 11442863, 5: 12125081}, adder=753061,
    base_dual={2: 12319167, 3: 16336858, 4: 17604404, 5: 18653970}, adder_dual=1158556)


def sh_newlywed(nid, kind, dates, single_parent_minor, quotes):
    """kind: "I"(SH21) / "II"(SH22·SH18·SH19). dates: marriage/child6/newborn/minor(지원대상 한부모 미성년 자녀) 리터럴."""
    p = nid
    exempt = {"all": [{"ne": [{"var": "marital_status"}, "예비신혼"]},
                      {"any": [{"in": [{"var": "welfare_status"}, WELFARE_EXEMPT]},
                               {"eq": [{"var": "is_supported_single_parent"}, True]}]}]}

    def youngest_after(d):
        return {"if": [{"is": [{"var": "has_children"}, False]}, False,
                       {"gte": [{"var": "youngest_child_birth_date"}, {"date": d}]}]}

    supported = {"eq": [{"var": "is_supported_single_parent"}, True]}
    if single_parent_minor:
        supported = {"all": [supported, youngest_after(dates["minor"])]}
    types = [
        {"id": "신생아가구", "label": "2년 이내 출생한 자녀(태아 포함)가 있는 가구 — 혼인 여부 무관", "conditions": [
            cond(f"{p}-T-newborn", "youngest_child_birth_date", [quotes["newborn"]],
                 f"{dates['newborn']} 이후 출생(태아는 출산예정일) 자녀가 있는지 — 혼인 여부와 무관",
                 youngest_after(dates["newborn"]))]},
        {"id": "지원대상한부모", "label": "「한부모가족지원법」 지원대상 한부모가족(증명서 발급 가능)", "conditions": [
            cond(f"{p}-T-supported", "is_supported_single_parent", [quotes["supported"]],
                 "지원대상 한부모가족(한부모가족 증명서 발급 가능)인지"
                 + (f" — 미성년 자녀({dates['minor']} 이후 출생)가 있어야 함" if single_parent_minor else ""),
                 supported)]},
        {"id": "신혼부부", "label": "혼인 7년 이내(재혼 포함)", "conditions": [
            cond(f"{p}-T-newlywed", "marital_status/marriage_date", [quotes["marriage"]],
                 f"혼인 중이고 혼인신고일이 {dates['marriage']} 이후인지(재혼 포함)",
                 {"all": [{"eq": [{"var": "marital_status"}, "혼인중"]},
                          {"gte": [{"var": "marriage_date"}, {"date": dates["marriage"]}]}]})]},
        {"id": "예비신혼부부", "label": "입주일 전일까지 혼인신고할 예비신혼부부", "conditions": [
            cond(f"{p}-T-prospective", "marital_status", ["입주일 전일까지 혼인신고를 하는 사람"],
                 "혼인 예정(예비신혼)인지 — 입주일 전일까지 혼인신고해야 함", {"eq": [{"var": "marital_status"}, "예비신혼"]})]},
        {"id": "6세이하한부모", "label": "6세 이하 자녀를 둔 한부모가족", "conditions": [
            cond(f"{p}-T-singleparent", "marital_status/youngest_child_birth_date", [quotes["child6_sp"]],
                 f"한부모이고 6세 이하 자녀({dates['child6']} 이후 출생)가 있는지",
                 {"all": [{"eq": [{"var": "marital_status"}, "한부모"]}, youngest_after(dates["child6"])]})]},
        {"id": "6세이하혼인가구", "label": "6세 이하 자녀가 있는 혼인가구", "conditions": [
            cond(f"{p}-T-married-child", "marital_status/youngest_child_birth_date", [quotes["child6_m"]],
                 f"혼인 중이고 6세 이하 자녀({dates['child6']} 이후 출생)가 있는지",
                 {"all": [{"eq": [{"var": "marital_status"}, "혼인중"]}, youngest_after(dates["child6"])]})]},
    ]
    if kind == "II":
        types.append({"id": "혼인가구", "label": "공고일 현재 혼인신고가 완료된 기타 혼인가구", "conditions": [
            cond(f"{p}-T-married", "marital_status", [quotes["married"]], "공고일 현재 혼인 중(혼인신고 완료)인지",
                 {"eq": [{"var": "marital_status"}, "혼인중"]})]})
    inc = INCOME_I if kind == "I" else INCOME_II
    ratio = ("70%", "90%") if kind == "I" else ("130%", "200%")
    table_quote = ([f"{inc['base'][s]:,}" for s in (2, 3, 4, 5)] + [f"{inc['base_dual'][s]:,}" for s in (2, 3, 4, 5)]
                   + [f"1인당 평균금액({inc['adder']:,}원)", f"1인당 평균금액({inc['adder_dual']:,}원)"])
    if kind == "I":
        assets, cars = [345000000, 379000000, 413000000], [45420000, 49960000, 54510000]
        asset_quote = ["34,500만원 이하", "379,000,000원 이하", "413,000,000원 이하"]
    else:
        assets, cars = [362000000, 396000000, 431000000], None
        asset_quote = ["36,200만원 이하", "396,000,000원 이하", "431,000,000원 이하"]
    exempt_quote = quotes["exempt"]
    conds = [
        cond(f"{p}-home", "home_ownership", [quotes["home"]], "무주택세대구성원인지(세대 전원 무주택)", HOME),
        {"id": f"{p}-type", "field": "유형", "required": True, "source": {"quote": [quotes["type_head"]]},
         "note": "세부 신청자격(신생아가구·지원대상 한부모·신혼부부·예비신혼부부·6세 이하 자녀 한부모·6세 이하 자녀 혼인가구"
                 + ("·혼인가구" if kind == "II" else "") + ") 중 하나에 해당하는지(순위는 자격으로 정해짐)",
         "tracks": types},
        cond(f"{p}-income", "monthly_income", [quotes["income"], exempt_quote],
             f"해당 세대 월평균소득이 {ratio[0]}(배우자 소득이 있으면 {ratio[1]}) 이하인지 — 2인은 +10%p, 수급자 등은 검증 면제",
             {"any": [exempt, {"lte": [{"var": "monthly_income"}, {"term": "limit"}]}]}, table="sh_rental_income"),
        cond(f"{p}-assets", "total_assets", asset_quote[:1] + [exempt_quote],
             "총자산이 출생자녀 가산을 반영한 기준 이내인지 — 수급자 등은 검증 면제",
             {"any": [exempt, {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}]}, table="sh_rental_assets"),
    ]
    if cars:
        conds.append(cond(f"{p}-car", "car_value", ["4,542만원 이하", exempt_quote],
                          "자동차가액이 출생자녀 가산을 반영한 기준 이내인지 — 수급자 등은 검증 면제",
                          {"any": [exempt, {"lte": [{"var": "car_value", "unknown_values": ["확인불가"]},
                                                    {"term": "car_limit"}]}]}, table="sh_rental_assets"))
    tables = {
        "sh_rental_income": {
            "label": f"SH 매입임대 소득 상한액: 가구원수×배우자 소득 유무 ({ratio[0]}/{ratio[1]}, 2인 +10%p 반영 금액)",
            "columns": ["size", "dual"], "inputs": {"size": {"var": "household_size"}, "dual": {"var": "dual_income"}},
            "outputs": ["limit"], "rows": income_rows(**inc),
            "source": {"quote": table_quote, "derivation": (
                f"2~5인은 원문 금액. 6인 이상은 원문 규칙대로 5인 금액에 1인당 평균금액({inc['adder']:,}원 / "
                f"배우자 소득 시 {inc['adder_dual']:,}원)을 더해 계산했다. 1인 가구 금액은 원문에 없다.")}},
        "sh_rental_assets": {
            "label": "SH 매입임대 자산 기준: 2023.3.28. 이후 출생 자녀 수(기존 미성년 자녀 포함 최대 2명)",
            "columns": ["child"], "inputs": {"child": {"fn": "child_bonus_count"}},
            "outputs": ["asset_limit"] + (["car_limit"] if cars else []),
            "rows": [r({"child": 0}, [assets[0]] + ([cars[0]] if cars else [])),
                     r({"child": 1}, [assets[1]] + ([cars[1]] if cars else [])),
                     r({"child": "2+"}, [assets[2]] + ([cars[2]] if cars else []))],
            "source": {"quote": asset_quote}},
    }
    return {"신혼·신생아": {"conditions": conds}}, tables


def sh_vacant(nid):
    p = nid
    return {"일반": {"conditions": [
        cond(f"{p}-home", "home_ownership", ["성년자인 무주택세대 구성원이어야"], "무주택세대구성원인지(세대 전원 무주택)", HOME),
        cond(f"{p}-region", "residence_area", ["현재 서울특별시에 주민등록이 등재된 성년자인 무주택세대 구성원이어야"],
             "공고일 현재 서울특별시에 주민등록이 돼 있는지(계약 후에도 계속 서울 거주)",
             {"eq": [{"var": "residence_area"}, "서울특별시"]}),
        cond(f"{p}-adult", "age", ["민법상 미성년자(만 19세 미만)는 공급 신청할 수 없습니다"],
             "만 19세 이상인지(미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청 가능)",
             {"any": [{"gte": [{"var": "age"}, 19]},
                      {"lte": [{"var": "age"}, 18], "review_if_true": {
                          "code": "SELF_REPORT_UNVERIFIED",
                          "detail": "미성년자는 원문의 예외(자녀가 있는 미성년 세대주, 형제자매를 부양하는 미성년 세대주, 외국인 부모의 "
                                    "한부모가족 미성년 세대주)에 해당할 때만 신청 가능 — 이 화면은 예외 여부를 확인하지 않음"}}]}),
    ]}}, {}


Q_I = dict(home="무주택세대구성원으로서 아래의 신혼·신생아Ⅰ 매입임대주택 세부 신청자격 중",
           type_head="신혼·신생아 매입임대Ⅰ 세부 신청자격",
           income="해당 세대의 월평균 소득이 [전년도 도시근로자 가구원수별 가구당 월평균소득]의 70%",
           exempt="수급자(생계·의료·주거·교육급여), 지원대상 한부모가족(한부모가족 증명서), 차상위계층은 소득·",
           newborn="2년 이내 출생한 자녀가 있는 가구 (‘24. 10. 1. 이후 출생한 자녀 및 태아)",
           supported="미성년 자녀가 있는 자(’07. 10. 1. 이후 출생한 자녀)",
           marriage="혼인 7년 이내(혼인신고일이 ‘19. 10. 1. ~ ’26. 9. 30.)인 사람",
           child6_sp="만 6세 이하 자녀를 둔 모자가족 또는 부자가족(‘19. 10. 1. 이후 출생한 자녀)",
           child6_m="만 6세 이하 자녀가 있는 혼인가구(‘19. 10. 1. 이후 출생한 자녀)")
Q_II = dict(Q_I, home="무주택세대구성원으로서 아래의 신혼·신생아Ⅱ 매입임대주택 세부 신청자격 중",
            type_head="신혼·신생아 매입임대Ⅱ 세부 신청자격",
            income="해당 세대의 월평균 소득이 [전년도 도시근로자 가구원수별 가구당 월평균소득]의 130%",
            married="기타 혼인가구(‘26. 9. 30. 현재 혼인신고가 완료된 사람)")
Q_M1 = dict(home="무주택세대구성원으로서 아래의 일반주택형 미리내집 입주자 모집공고(신혼·신생아",
            type_head="미리내집(신혼·신생아 매입임대주택Ⅱ) 세부 신청자격",
            income="도시근로자 가구원수별 가구당 월평균소득의 130% 이하(맞벌이 인 경우 200% 이하)",
            exempt="수급자(생계·의료·주거·교육급여), 지원대상 한부모가족(한부모가족 증명서), 차상위계층은 소득·자산검증",
            newborn="(’24. 08. 15. 이후 출생한 자녀 및 태아)",
            supported="한부모가족 증명서 발급이 가능한 자",
            marriage="혼인 7년 이내(혼인신고일이 ’19. 08. 15. ~ ’26. 08. 14.)인 사람",
            child6_sp="6세 이하 자녀를 둔 모자가족 또는 부자가족(’19. 08. 15. 이후 출생한 자녀)",
            child6_m="6세 이하 자녀가 있는 혼인가구(’19. 08. 15. 이후 출생한 자녀)",
            married="기타 혼인가구(’26. 08. 14. 현재 혼인신고가 완료된 사람)")
Q_M2 = dict(home="무주택세대구성원으로서 아래의 일반주택형 미리내집(공공한옥) 입주자 모집공고의",
            type_head="일반주택형 미리내집(공공한옥) 세부 신청자격",
            income="도시근로자 가구원수별 가구당 월평균소득의 130% 이하 (맞벌이의 경우 200%이하)",
            exempt="수급자(생계·의료·주거·교육급여), 보호대상 한부모가족(한부모가족 증명서), 차상위계층은 소득·자산검증",
            newborn="공고일로부터 2년 이내 출생한 자녀가 있는 가구(’24. 8. 25. 이후 출생한 자녀 및 태아)",
            supported="한부모가족 증명서가 발급이 가능한 자",
            marriage="혼인 7년 이내(혼인신고일이 ’19. 8. 25. ~ ’26. 8. 24.)인 사람",
            child6_sp="6세 이하 자녀를 둔 모자가족 또는 부자가족(’19. 8. 25. 이후 출생한 자녀 및 태아)",
            child6_m="6세 이하 자녀가 있는 혼인가구(’19. 8. 25. 이후 출생한 자녀 및 태아)",
            married="기타 혼인가구(’26. 8. 24. 현재 혼인신고가 완료된 사람)")

PLAN = [
    dict(nid="N18", key="SH21", title="SH 2026년 하반기 신혼·신생아 매입임대주택Ⅰ", ann="2026-09-30",
         program="SH 신혼·신생아 매입임대Ⅰ",
         build=lambda: sh_newlywed("N18", "I", dict(marriage="2019-10-01", child6="2019-10-01", newborn="2024-10-01",
                                                   minor="2007-10-01"), True, Q_I),
         notes=["배우자 자격검증이 불가능한 경우(국내 미거주 재외국민, 외국인 미등록, 주민등록 말소·거주불명·해외체류)는 신청할 수 없다(p.13).",
                "수급자 등 소득·자산 검증 면제는 해당 증명서를 제출해야 적용된다(p.17)."]),
    dict(nid="N19", key="SH22", title="SH 2026년 하반기 신혼·신생아 매입임대주택Ⅱ", ann="2026-09-30",
         program="SH 신혼·신생아 매입임대Ⅱ",
         build=lambda: sh_newlywed("N19", "II", dict(marriage="2019-10-01", child6="2019-10-01", newborn="2024-10-01",
                                                    minor="2007-10-01"), True, Q_II),
         notes=["배우자 자격검증이 불가능한 경우는 신청할 수 없다.", "수급자 등 소득·자산 검증 면제는 해당 증명서를 제출해야 적용된다(p.11)."]),
    dict(nid="N20", key="SH18", title="SH 2026년 제1차 일반주택형 미리내집", ann="2026-08-14",
         program="SH 일반주택형 미리내집(신혼·신생아 매입임대Ⅱ)",
         build=lambda: sh_newlywed("N20", "II", dict(marriage="2019-08-15", child6="2019-08-15", newborn="2024-08-15"),
                                   False, Q_M1),
         notes=["수급자 등 소득·자산 검증 면제는 해당 증명서를 제출해야 적용된다(p.13).",
                "미리내집 거주 중 출산하면 장기전세주택2 이주 혜택이 있다 — 이 판정과 무관."]),
    dict(nid="N21", key="SH19", title="SH 2026년 일반주택형 미리내집(공공한옥) 잔여세대", ann="2026-08-24",
         program="SH 일반주택형 미리내집(신혼·신생아 매입임대Ⅱ)",
         build=lambda: sh_newlywed("N21", "II", dict(marriage="2019-08-25", child6="2019-08-25", newborn="2024-08-25"),
                                   False, Q_M2),
         notes=["한옥 일부 세대는 3대 이상 대가족 우선 선정 — 이 판정과 무관.", "배우자가 주민등록 말소·거주불명이면 신청할 수 없다."]),
    dict(nid="N22", key="SH20", title="SH 2026년 2차 장기미임대 매입임대주택", ann="2026-08-28",
         program="SH 장기미임대 매입임대", build=lambda: sh_vacant("N22"),
         notes=["소득은 자격이 아니라 순위에만 쓴다: 도시근로자 월평균소득 130% 이하(1인 5,720,045원·3인 10,618,958원 등)면 1순위, "
                "초과면 2순위(p.6·p.8).", "계약 후에도 공고일 이후 계속 서울에 거주해야 한다(p.7). 외국인은 신청할 수 없다."]),
]

ANCHORS = {"신혼·신생아": ("세부 신청자격", 10), "일반": ("신청자격", 6)}


def main():
    from pypdf import PdfReader
    import logging
    logging.disable(logging.CRITICAL)
    for plan in PLAN:
        pdf = C4.pdf_for(plan["key"])
        pages = sv.extract_pages(pdf)
        layers, tables = plan["build"]()
        missing = []
        for layer, ldoc in layers.items():
            text, hint = ANCHORS[layer]
            anchor = locate(pages, text, hint) or hint
            for c in C4.walk(ldoc["conditions"]):
                place_quotes(c["source"], pages, anchor, f"{layer}/{c['id']}", missing)
            for name, t in tables.items():
                place_quotes(t["source"], pages, anchor + 3, f"table:{name}", missing)
        doc = {
            "notice_id": plan["nid"], "title": plan["title"], "announcement_date": plan["ann"],
            "issuer": "SH", "program": plan["program"], "version": 1, "valid_from": plan["ann"], "supersedes": None,
            "source": {"document": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "pages": len(pages)},
            "review": {"status": "DRAFT", "note": "C4b 생성(tools/gen_c4_sh.py). 원문 표 수치는 손으로 옮김. 독립 검토 전.",
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
