# -*- coding: utf-8 -*-
"""G2: 공공임대 새 사업(국민임대 …)의 규칙을 만든다. 사용: python tools/gen_c6_public.py   (재실행 안전 — 같은 결과)

| ID  | 원문 | 사업 | 공고일 |
| N30 | LH30 | 국민임대 남양주마석2단지 예비입주자(LH 표준 공고) | 2026-09-07 |
| N31 | LH31 | 국민임대 김포지역 예비입주자(LH 표준 공고, 정정) | 2026-09-07 |
| N32 | LH32 | 국민임대 부천시지역 예비입주자(고령자 주택형 포함) — 처음 보는 공고 검증 | 2026-09-07 |
| N33 | LH33 | 영구임대 양주회천 A25BL 예비입주자(주거약자용 포함) | 2026-09-21 |
| N34 | LH34 | 영구임대 부천시 예비입주자 | 2026-09-04 |
| N35 | LH35 | 통합공공임대 평창장평(일반형) | 2026-10-30 |
| N36 | LH36 | 통합공공임대 강서염창(정정) — 처음 보는 공고 검증 | 2026-09-17 |
| N37 | LH37 | 분양전환 공공임대(리츠) 파주운정3 A12 예비입주자 (G4 개발용) | 2026-05-28 |
| N38 | LH38 | 10년 공공임대(리츠) 양주옥정 예비입주자 (G4 개발용) | 2026-06-24 |
| N39 | LH39 | 50년 공공임대 오산운암6단지 예비입주자 (G4 개발용) | 2026-06-10 |
| N45·N46 | LH45·46 | 신혼희망타운(공공분양) 평택고덕 A-57-2(불문 잔여)·시흥하중 A-4(정규 잔여) (G3 개발용) | |
| N47·N48 | LH47·48 | G3 처음 보는 공고: 수원당수 A-3(불문 잔여)·안산신길2 A-6(정규, 사전청약 당첨자 유형은 미지원) | |
| N40~N44 | LH40~44 | G4 처음 보는 공고: 김포 Ac-01a·대전천동 35BL·김포 센트럴블루힐(10년)·구리갈매 S1(10년)·동해천곡5(50년) | |

- 판정 범위는 신청 자격(무주택·성년·소득·자산·자동차)이다. 순위(청약저축 납입 횟수·거주지)와 배점은 경쟁이 있을 때의
  선정 순서라 판정하지 않는다(notes에 적는다).
- 원문 표의 수치(자산·자동차 한도)는 손으로 옮긴 리터럴이다 — 다음 해 기준이 바뀐 공고는 인용문을 찾지 못해 보류된다.
- 소득 기준표는 국민임대 공고의 70%·80%·90% 열(1~8인)을 rules/reference/income_standard_public.json에 따로 둔다
  (다른 사업 표와 섞지 않는다 — C4a의 행복주택·매입임대 표 누수 교훈).
- 인용문 쪽은 대상 PDF에서 자동 탐색한다. 생성 후 tools/verify_sources.py, pytest(tests/test_g2_public.py)로 확인.
"""
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
HOME = {"eq": [{"var": "home_ownership"}, "무주택"]}
CAR = {"var": "car_value", "unknown_values": ["확인불가"]}


# ------------------------------------------------------------------------------------------------
# 국민임대 (LH 표준 공고 — 남양주마석 p.4~6 / 김포 p.5~8)
# ------------------------------------------------------------------------------------------------
def national_rental(nid, elderly_quote=None):
    """elderly_quote: 고령자 전용 주택형 문구(예: 부천 p.3 '범박1단지46형고령자임대주택은(공고일현재65세이상만신청)가능') —
    있으면 같은 자격에 '공고일 현재 65세 이상'을 더한 계층을 만든다."""
    p = f"{nid}-G"
    terms = "national_terms"
    conditions = [
        cond(f"{p}-home", "home_ownership",
             ["현재 무주택세대구성원으로서 아래의 '소득 및 자산보유기준'을 충족하는 사람"],
             "무주택세대구성원인지(세대 전원 무주택, 분양권 등 포함)", HOME),
        cond(f"{p}-adult", "age", ["「민법」상 미성년자(19세 미만)는 공급신청할 수 없습니다"],
             "성년(만 19세 이상)인지 — 미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청 가능",
             {"any": [{"gte": [{"var": "age"}, 19]},
                      {"lte": [{"var": "age"}, 18],
                       "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                          "detail": "미성년자는 원칙적으로 신청할 수 없고, 자녀가 있는 미성년 세대주·형제자매를 부양하는 "
                                                    "미성년 세대주 등 예외에 해당할 때만 신청할 수 있습니다(법정대리인 동의 필요). "
                                                    "예외 해당 여부는 이 화면이 묻지 않습니다."}}]}),
        cond(f"{p}-income", "monthly_income",
             # '20%가산'(남양주·김포)과 '20%p가산'(부천) 두 표기가 있어 비율 문구 대신 가산 항목 머리말을 인용한다
             ["소득기준가산", "가구원수 가산항목 및 비율", "출산자녀수 가산항목 및 비율"],
             "세대 전원의 월평균소득 합계가 70%(1인 +20%p·2인 +10%p, 출산자녀 1명 +10%p·2명 이상 +20%p) 기준 이내인지",
             {"lte": [{"var": "monthly_income"},
                      {"lookup": ["income_standard_public", {"var": "household_size"}, {"term": "ratio"}]}]},
             table=terms),
        cond(f"{p}-assets", "total_assets", ["총자산가액 합산기준 (345)백만원 이하"],
             "세대 전원의 총자산이 3억4,500만원(출산자녀 1명 3억7,900만원·2명 이상 4억1,300만원) 이하인지",
             {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table=terms),
        cond(f"{p}-car", "car_value", ["개별자동차가액 (4,542)만원 이하"],
             "자동차가액(여러 대면 가장 높은 차량가액)이 4,542만원(출산자녀 1명 4,996만원·2명 이상 5,451만원) 이하인지",
             {"lte": [CAR, {"term": "car_limit"}]}, table=terms),
    ]
    tables = {terms: {
        "label": "국민임대 소득 비율·자산·자동차 한도: 가구원수 × 출산자녀수(가구원수 가산과 출산자녀 가산을 더함)",
        "columns": ["size", "child"],
        "inputs": {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"}},
        "outputs": ["ratio", "asset_limit", "car_limit"],
        "rows": [
            r({"size": 1, "child": 0}, [90] + B1),
            r({"size": 1, "child": "1+"}, **no_row(C3.D_ALONE_CHILD)),
            r({"size": 2, "child": 0}, [80] + B1),
            r({"size": 2, "child": 1}, [90] + B2),
            r({"size": 2, "child": "2+"}, **no_row(C3.D_TWO_KIDS)),
            r({"size": "3+", "child": 0}, [70] + B1),
            r({"size": "3+", "child": 1}, [80] + B2),
            r({"size": "3+", "child": "2+"}, [90] + B3),
        ],
        "source": {"quote": ["0명(기준) 34,500 4,542", "1명 37,900 4,996", "2명 41,300 5,451"]},
    }}
    layers = {"일반": {"conditions": conditions}}
    if elderly_quote:
        layers["일반(고령자 주택형)"] = {"conditions": [dict(json.loads(json.dumps(c)), id=c["id"].replace(f"{p}-", f"{nid}-E-"))
                                             for c in conditions] + [
            cond(f"{nid}-E-age65", "age", [elderly_quote], "공고일 현재 65세 이상인지(고령자 전용 주택형)",
                 {"gte": [{"var": "age"}, 65]})]}
    return layers, tables


# ------------------------------------------------------------------------------------------------
# 영구임대 (LH 영구임대 표준 공고 — 양주회천 A25 p.4~7·p.9 / 부천시 p.4~6)
# ------------------------------------------------------------------------------------------------
PERM_B1, PERM_B2, PERM_B3 = [245000000, 45420000], [270000000, 49960000], [294000000, 54510000]
WELFARE_ANY = ["생계·의료·주거급여 수급자", "교육급여만 수급", "차상위계층"]     # 수급권자(급여 종류 무관)·차상위
WEAK_TYPES = ["장애인", "국가유공자(상이 1~7급)", "보훈보상대상자(상이 1~7급)", "5·18민주화운동부상자(장해 1~14급)",
              "고엽제후유의증환자(경도 이상)", "국가유공자에 준하는 군경(상이 1~7급)"]
Q70 = "전년도 도시근로자 가구당 월평균소득의 70%(1인 90%, 2인 80%) 이하이고 영구임대주택의 자산요건을 충족한"


def _money(prefix, term, quote, pct):
    """영구임대 신분별 소득(기준 비율은 신분마다 다름)·자산·자동차 조건."""
    return [
        cond(f"{prefix}-income", "monthly_income", [quote], f"세대 월평균소득이 {pct}(가구원수·출생자녀 가산 반영) 이하인지",
             {"lte": [{"var": "monthly_income"},
                      {"lookup": ["income_standard_permanent", {"var": "household_size"}, {"term": term}]}]},
             table="permanent_terms"),
        # 총자산·자동차 한도는 '(24,500)만원'(부천)·'24,500만원'(양주) 두 표기 — 괄호 밖 공통 부분을 인용한다
        cond(f"{prefix}-assets", "total_assets", ["가액합산기준", "24,500"],
             "세대 총자산이 2억4,500만원(출생자녀 1명 2억7,000만·2명 이상 2억9,400만) 이하인지",
             {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table="permanent_terms"),
        cond(f"{prefix}-car", "car_value", ["개별자동차가액", "4,542"],
             "자동차가액(가장 높은 차량가액)이 4,542만원(출생자녀 가산) 이하인지",
             {"lte": [CAR, {"term": "car_limit"}]}, table="permanent_terms"),
    ]


def permanent_rental(nid, city, residence_quote, adult_quote, weak_quote=None):
    """영구임대 일반공급: 그 시·군 거주 + 성년 + 무주택세대구성원 + 「공공주택 특별법 시행규칙」 별표3 신분 중 하나.
    신분마다 소득 기준이 다르다(수급자 등 검증 없음 / 70% / 50% / 100%) — 트랙 묶음으로 표현한다.
    weak_quote: 주거약자용 주택형 문구 — 있으면 같은 자격 + 주거약자(65세 이상·장애인·상이 국가유공자 등) 계층을 만든다."""
    p = f"{nid}-P"
    disabled = {"any": [{"eq": [{"var": "housing_weak_type"}, "장애인"]},
                        {"eq": [{"var": "disabled_spouse_qualifies"}, True]}]}
    tracks = [
        {"id": "가", "label": "생계급여 또는 의료급여 수급자(소득·자산 검증 없음)", "conditions": [
            cond(f"{p}-Ta", "livelihood_medical_recipient", ["국민기초생활보장법상의 생계급여수급자 또는 의료급여수급자"],
                 "생계급여 또는 의료급여 수급자인지(주거·교육급여만 받는 경우는 아님)",
                 {"eq": [{"var": "livelihood_medical_recipient"}, True]})]},
        {"id": "나", "label": "국가유공자·보훈보상대상자·5·18·특수임무·참전유공자(유족 포함), 소득 70%", "conditions": [
            cond(f"{p}-Tb", "merit_person", ["「국가유공자 등 예우 및 지원에 관한 법률」에 따른 국가유공자 또는 그 유족"],
                 "국가유공자·보훈보상대상자·5·18민주유공자·특수임무유공자(또는 그 유족)·참전유공자인지",
                 {"eq": [{"var": "merit_person"}, True]})] + _money(f"{p}-Tb", "ratio70", Q70, "70%")},
        {"id": "라", "label": "지원대상 한부모가족(소득·자산 검증 없음)", "conditions": [
            cond(f"{p}-Td", "is_supported_single_parent", ["라.지원대상한부모가족"],
                 "지원대상 한부모가족(한부모가족 증명서 발급 대상)인지", {"eq": [{"var": "is_supported_single_parent"}, True]})]},
        {"id": "마", "label": "북한이탈주민, 소득 70%", "conditions": [
            cond(f"{p}-Te", "north_korean_defector", ["영구임대주택의 자산요건을 충족하는 북한이탈주민"], "북한이탈주민인지",
                 {"eq": [{"var": "north_korean_defector"}, True]})] + _money(f"{p}-Te", "ratio70", Q70, "70%")},
        {"id": "바", "label": "장애인(지적·정신·중증 뇌병변장애인은 그 배우자 포함), 소득 70%", "conditions": [
            cond(f"{p}-Tf", "housing_weak_type/disabled_spouse_qualifies", ["장애인등록증이 교부된 자"],
                 "장애인등록증이 교부된 장애인이거나, 지적·정신·중증 뇌병변장애인의 배우자인지", disabled)]
            + _money(f"{p}-Tf", "ratio70", Q70, "70%")},
        {"id": "사", "label": "65세 이상 직계존속 부양자로서 수급자 선정기준 소득인정액 이하", "conditions": [
            cond(f"{p}-Tg", "supports_elderly_parent", ["65세 이상 직계존속(배우자의 직계존속 포함)을 부양"],
                 "만 65세 이상 직계존속(배우자 부모 포함)을 같은 등본에서 부양하는지 — 소득인정액은 이 화면이 계산하지 않는다",
                 {"eq": [{"var": "supports_elderly_parent"}, True],
                  "review_if_true": {"code": "SELF_REPORT_UNVERIFIED",
                                     "detail": "65세 이상 직계존속 부양자는 생계·의료급여 수급자 선정기준의 '소득인정액' 이하여야 "
                                               "합니다. 소득인정액(소득+재산 환산액)은 이 화면이 계산하지 않으니 주민센터에 확인하세요."}})]},
        {"id": "아", "label": "아동복지시설 퇴소자(시설장 추천), 소득 70%", "conditions": [
            cond(f"{p}-Th", "child_facility_leaver", ["아동복지시설에서 퇴소하는 자로서 아동복지시설의 장이 추천하는 자"],
                 "아동복지시설에서 퇴소하며 시설장의 추천을 받았는지", {"eq": [{"var": "child_facility_leaver"}, True]})]
            + _money(f"{p}-Th", "ratio70", Q70, "70%")},
        {"id": "자", "label": "65세 이상 수급권자 또는 차상위계층", "conditions": [
            cond(f"{p}-Ti", "age/welfare_status", ["65세 이상인 사람으로서 「국민기초생활보장법」 제2조 제1호에 따른 수급권자"],
                 "만 65세 이상이고 기초생활 수급권자(급여 종류 무관) 또는 차상위계층인지",
                 {"all": [{"gte": [{"var": "age"}, 65]}, {"in": [{"var": "welfare_status"}, WELFARE_ANY]}]})]},
        {"id": "차", "label": "2순위 — 일반(소득 50%)", "conditions": _money(
            f"{p}-Tj", "ratio50", "전년도 도시근로자 가구원수별 가구당 월평균소득 50%(1인 70%, 2인 60%) 이하인 자", "50%")},
        {"id": "타", "label": "2순위 — 장애인, 소득 100%", "conditions": [
            cond(f"{p}-Tl", "housing_weak_type/disabled_spouse_qualifies", ["장애인등록증이 교부된 자"],
                 "장애인등록증이 교부된 장애인이거나, 지적·정신·중증 뇌병변장애인의 배우자인지", disabled)]
            + _money(f"{p}-Tl", "ratio100",
                     "전년도 도시근로자 가구원수별 가구당 월평균소득의 100%(1인 120%, 2인 110%) 이하이고", "100%")},
    ]
    common = [
        cond(f"{p}-home", "home_ownership", [residence_quote], "무주택세대구성원인지(세대 전원 무주택, 분양권 등 포함)", HOME),
        cond(f"{p}-region", "residence_area", [residence_quote], f"공고일 현재 {city}에 주민등록이 되어 있는지",
             {"in": [{"var": "residence_area"}, [city]]}),
        cond(f"{p}-adult", "age", [adult_quote],
             "성년(만 19세 이상)인지 — 미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청 가능",
             {"any": [{"gte": [{"var": "age"}, 19]},
                      {"lte": [{"var": "age"}, 18],
                       "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                          "detail": "미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청할 수 있습니다. "
                                                    "예외 해당 여부는 이 화면이 묻지 않습니다."}}]}),
        {"id": f"{p}-rank", "field": "입주자격", "required": True,
         "source": {"quote": ["1순위 가. 국민기초생활보장법상의 생계급여수급자", "2순위 차."]},
         "note": "「공공주택 특별법 시행규칙」 별표3의 영구임대 입주자격(1순위 가~자, 2순위 차·타) 중 하나 이상에 해당하는지 "
                 "(신분마다 소득 기준이 다름 — 수급자 등 없음 / 70% / 50% / 100%)",
         "tracks": tracks},
    ]
    tables = {"permanent_terms": {
        "label": "영구임대 소득 비율(일반 50%·국가유공자 등 70%·2순위 장애인 100% 기준)·자산·자동차 한도: 가구원수 × 출생자녀수",
        "columns": ["size", "child"],
        "inputs": {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"}},
        "outputs": ["ratio50", "ratio70", "ratio100", "asset_limit", "car_limit"],
        "rows": [
            r({"size": 1, "child": 0}, [70, 90, 120] + PERM_B1),
            r({"size": 1, "child": "1+"}, **no_row(C3.D_ALONE_CHILD)),
            r({"size": 2, "child": 0}, [60, 80, 110] + PERM_B1),
            r({"size": 2, "child": 1}, [70, 90, 120] + PERM_B2),
            r({"size": 2, "child": "2+"}, **no_row(C3.D_TWO_KIDS)),
            r({"size": "3+", "child": 0}, [50, 70, 100] + PERM_B1),
            r({"size": "3+", "child": 1}, [60, 80, 110] + PERM_B2),
            r({"size": "3+", "child": "2+"}, [70, 90, 120] + PERM_B3),
        ],
        "source": {"quote": ["245,000,000", "270,000,000", "294,000,000"]},
    }}
    layers = {"일반": {"conditions": common}}
    if weak_quote:
        weak = json.loads(json.dumps(common, ensure_ascii=False).replace(f'"{p}-', f'"{nid}-W-'))
        weak.append(cond(f"{nid}-W-weak", "age/housing_weak_type", [weak_quote],
                         "주거약자(만 65세 이상, 장애인, 상이 1~7급 국가유공자·보훈보상대상자, 5·18 부상자, 고엽제후유의증환자)인지",
                         {"any": [{"gte": [{"var": "age"}, 65]}, {"in": [{"var": "housing_weak_type"}, WEAK_TYPES]}]}))
        layers["일반(주거약자용)"] = {"conditions": weak}
    return layers, tables


# ------------------------------------------------------------------------------------------------
# 통합공공임대 일반형 (LH 표준 공고 — 평창장평 p.9·p.12·p.14~18)
# ------------------------------------------------------------------------------------------------
# 판정은 일반공급 기준(기준중위소득 150% + 가산)이다. 우선공급(청년·신혼부부 등, 100% + 가산)은 일반공급보다 기준이 낮은
# 선정 순서라 판정하지 않는다 — 우선공급 신청자는 일반공급에도 자동 신청된다(p.4).
INT_B1, INT_B2, INT_B3 = B1, B2, B3        # 총자산 3억4,500만·3억7,900만·4억1,300만, 자동차 4,542만·4,996만·5,451만(p.12)
INT_ASSETS_Q = "총자산345,000,000원및자동차45,420,000원이하"
INT_INCOME = {"lte": [{"var": "monthly_income"},
                      {"lookup": ["income_standard_median", {"var": "household_size"}, {"term": "ratio"}]}]}
INT_ADULT = {"any": [{"gte": [{"var": "age"}, 19]},
                     {"lte": [{"var": "age"}, 18],
                      "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                         "detail": "미성년자는 자녀를 양육하는 미성년 세대주·형제자매를 부양하는 미성년 세대주·"
                                                   "예비신혼부부 등 예외에 해당할 때만 신청할 수 있습니다(법정대리인 동의). "
                                                   "예외 해당 여부는 이 화면이 묻지 않습니다."}}]}
D_NEWLYWED_ONE = ("신혼부부·예비신혼부부의 가구원수는 부부 2인 이상이어야 합니다(예비신혼부부는 혼인으로 구성될 세대). "
                  "가구원수를 확인해 주세요.")
D_COUPLE_CHILD = "가구원수가 2인(부부만)인데 출생자녀 가산 대상 자녀가 있습니다(부부+자녀면 3인 이상). 입력을 확인해 주세요."
D_COUPLE3_KIDS = "부부 3인 가구인데 출생자녀 가산 대상 자녀가 2명 이상입니다(부부+자녀 2명이면 4인 이상). 입력을 확인해 주세요."


def _int_rows(base=150):
    """가구원수 × 출산자녀수 — 기준 150%에 1인 +20%p·2인 +10%p, 출산자녀 1명 +10%p·2명 이상 +20%p(p.17 표)."""
    return [
        r({"size": 1, "child": 0}, [base + 20] + INT_B1),
        r({"size": 1, "child": "1+"}, **no_row(C3.D_ALONE_CHILD)),
        r({"size": 2, "child": 0}, [base + 10] + INT_B1),
        r({"size": 2, "child": 1}, [base + 20] + INT_B2),
        r({"size": 2, "child": "2+"}, **no_row(C3.D_TWO_KIDS)),
        r({"size": "3+", "child": 0}, [base] + INT_B1),
        r({"size": "3+", "child": 1}, [base + 10] + INT_B2),
        r({"size": "3+", "child": "2+"}, [base + 20] + INT_B3),
    ]


def _newlywed_rows():
    """신혼부부(맞벌이 +30%p) — p.17 '그 외' 표: 2인 160 / 3인 150·160 / 4인 이상 150·160·170, 맞벌이(○)는 각 +30."""
    rows = [r({"size": 1, "child": "any", "dual": "any"}, **no_row(D_NEWLYWED_ONE)),
            r({"size": 2, "child": "1+", "dual": "any"}, **no_row(D_COUPLE_CHILD)),
            r({"size": 3, "child": "2+", "dual": "any"}, **no_row(D_COUPLE3_KIDS))]
    for dual, add in ((False, 0), (True, 30)):
        rows += [r({"size": 2, "child": 0, "dual": dual}, [160 + add] + INT_B1),
                 r({"size": "3+", "child": 0, "dual": dual}, [150 + add] + INT_B1),
                 r({"size": "3+", "child": 1, "dual": dual}, [160 + add] + INT_B2),
                 r({"size": "4+", "child": "2+", "dual": dual}, [170 + add] + INT_B3)]
    return rows


def _int_money(prefix, table, income_quote, what):
    return [
        cond(f"{prefix}-income", "monthly_income", [income_quote],
             f"{what} 월평균소득이 기준중위소득 150%(1인 +20%p·2인 +10%p, 출산자녀 가산 반영) 이하인지", INT_INCOME, table=table),
        cond(f"{prefix}-assets", "total_assets", [INT_ASSETS_Q],
             f"{what} 총자산이 3억4,500만원(출산자녀 1명 3억7,900만원·2명 이상 4억1,300만원) 이하인지",
             {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table=table),
        cond(f"{prefix}-car", "car_value", [INT_ASSETS_Q],
             "자동차가액(여러 대면 가장 높은 차량가액)이 4,542만원(출산자녀 1명 4,996만원·2명 이상 5,451만원) 이하인지",
             {"lte": [CAR, {"term": "car_limit"}]}, table=table),
    ]


def integrated_rental(nid):
    """통합공공임대 일반공급 — 입주자격 구분(청년·신혼부부·한부모가족·고령자·일반)마다 계층 하나.
    공고별 값이 없다: 날짜 기준(6세 이하·혼인 7년·65세)은 공고일에서 계산하고, 소득표·자산 한도는 같은 연도 공고에서 같다."""
    adult = cond(f"{nid}-I-adult", "age", ["「민법」상미성년자(19세미만)는신청하실수없습니다"],
                 "성년(만 19세 이상)인지 — 미성년자는 자녀를 양육하는 미성년 세대주 등 예외에 해당할 때만 신청 가능", INT_ADULT)
    household_q = "무주택세대구성원으로서해당세대의월평균소득이기준중위소득의150퍼센트"

    def home(p, quote, note="무주택세대구성원인지(세대 전원 무주택, 분양권 등 포함)"):
        return cond(f"{p}-home", "home_ownership", [quote], note, HOME)

    def with_adult(p):
        return dict(json.loads(json.dumps(adult)), id=f"{p}-adult")

    y, m, s, e, g = (f"{nid}-I{x}" for x in "YMSEG")
    youth = [
        home(y, "무주택자로서다음의요건을모두갖춘사람", "무주택자인지(본인 기준 — 세대 내 다른 구성원의 주택 소유는 무관)"),
        cond(f"{y}-age", "age", ["18세이상39세이하일것"], "공고일 현재 만 18세 이상 39세 이하인지",
             {"between": [{"var": "age"}, 18, 39]}),
        cond(f"{y}-marital", "marital_status", ["혼인중이아닐것"], "혼인 중이 아닌지",
             {"in": [{"var": "marital_status"}, ["미혼", "예비신혼", "한부모"]]}),
        cond(f"{y}-income", "monthly_income", ["기준중위소득의150퍼센트(1~2인가구및출산가구의경우에는우대비율을가산)이하일것"],
             "본인 월평균소득(세대원이 있는 세대주는 세대 전체)이 기준중위소득 150%(1인 +20%p·2인 +10%p, 출산자녀 가산) 이하인지",
             {"lte": [{"var": "monthly_income"},
                      {"lookup": ["income_standard_median", {"term": "income_size"}, {"term": "ratio"}]}]},
             table="integrated_youth_terms"),
        cond(f"{y}-assets", "total_assets", [INT_ASSETS_Q],
             "본인 총자산(세대원이 있는 세대주는 세대 전체)이 3억4,500만원(출산자녀 가산) 이하인지",
             {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table="integrated_youth_terms"),
        cond(f"{y}-car", "car_value", [INT_ASSETS_Q], "자동차가액이 4,542만원(출산자녀 가산) 이하인지",
             {"lte": [CAR, {"term": "car_limit"}]}, table="integrated_youth_terms"),
    ]
    newlywed = [
        cond(f"{m}-marital", "marital_status",
             ["예비신혼부부(혼인을계획중이며해당주택의입주전까지혼인사실을증명할수있는사람)"], "혼인 중이거나 예비신혼부부인지",
             {"in": [{"var": "marital_status"}, ["혼인중", "예비신혼"]]}),
        cond(f"{m}-duration", "marriage_duration_or_child", ["혼인기간이7년", "혼인중인사람으로서6세이하자녀"],
             "혼인기간 7년 이내이거나 6세 이하 자녀(태아 포함)를 두었는지(예비신혼부부는 이 요건이 없음)",
             {"any": [{"eq": [{"var": "marital_status"}, "예비신혼"]},
                      {"gte": [{"var": "marriage_date"}, {"fn": "marriage_cutoff"}]},
                      {"if": [{"is": [{"var": "has_children"}, False]}, False,
                              {"gte": [{"var": "youngest_child_birth_date"}, {"fn": "young_child_cutoff"}]}]}]}),
        home(m, "무주택세대구성원(예비신혼부부의경우혼인으로구성될세대의세대구성원모두무주택자인경우)일것",
             "무주택세대구성원인지(예비신혼부부는 혼인으로 구성될 세대 전원)"),
        with_adult(m),
        cond(f"{m}-income", "monthly_income",
             ["기준중위소득의150퍼센트(맞벌이,2인가구및출산가구의경우에는우대비율을가산)이하일것", "신혼부부맞벌이우대비율:30%p가산"],
             "세대 월평균소득(예비신혼부부는 혼인으로 구성될 세대 합계)이 기준중위소득 150%(2인 +10%p, 출산자녀 가산, "
             "부부 모두 근로·사업소득이 있으면 +30%p) 이하인지", INT_INCOME, table="integrated_newlywed_terms"),
        cond(f"{m}-assets", "total_assets", [INT_ASSETS_Q], "세대 총자산이 3억4,500만원(출산자녀 가산) 이하인지",
             {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table="integrated_newlywed_terms"),
        cond(f"{m}-car", "car_value", [INT_ASSETS_Q], "자동차가액이 4,542만원(출산자녀 가산) 이하인지",
             {"lte": [CAR, {"term": "car_limit"}]}, table="integrated_newlywed_terms"),
    ]
    single = [
        cond(f"{s}-marital", "marital_status", ["를둔한부모가족(자녀가신청자와동일한세대별주민등록표에등재된경우에한함)"],
             "한부모가족인지", {"in": [{"var": "marital_status"}, ["한부모"]]}),
        cond(f"{s}-child6", "youngest_child_birth_date", ["를둔한부모가족(자녀가신청자와동일한세대별주민등록표에등재된경우에한함)"],
             "6세 이하 자녀(같은 주민등록표에 등재)를 둔 한부모가족인지",
             {"if": [{"is": [{"var": "has_children"}, False]}, False,
                     {"gte": [{"var": "youngest_child_birth_date"}, {"fn": "young_child_cutoff"}]}]}),
        home(s, household_q), with_adult(s),
    ] + _int_money(s, "integrated_terms", household_q, "세대")
    elderly = [
        home(e, "단독세대주로입주하려는사람의경우에는무주택자)으로서다음의요건을모두갖춘사람",
             "무주택세대구성원인지(혼인 중이 아닌 단독세대주는 본인만 무주택)"),
        cond(f"{e}-age", "age", ["65세이상("], "공고일 현재 만 65세 이상인지", {"gte": [{"var": "age"}, 65]}),
    ] + _int_money(e, "integrated_terms", household_q, "세대")
    general = [home(g, household_q), with_adult(g)] + _int_money(g, "integrated_terms", household_q, "세대")

    tables = {
        "integrated_terms": {
            "label": "통합공공임대 일반공급 소득 비율·자산·자동차 한도: 가구원수 × 출산자녀수(가구원수 가산과 출산자녀 가산을 더함)",
            "columns": ["size", "child"],
            "inputs": {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"}},
            "outputs": ["ratio", "asset_limit", "car_limit"], "rows": _int_rows(),
            "source": {"quote": ["신혼부부,한부모가족을제외한모든계층×1인0인170%"]}},
        "integrated_newlywed_terms": {
            "label": "통합공공임대 일반공급 신혼부부 소득 비율·자산·자동차 한도: 가구원수 × 출산자녀수 × 맞벌이",
            "columns": ["size", "child", "dual"],
            "inputs": {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"},
                       "dual": {"var": "dual_income"}},
            "outputs": ["ratio", "asset_limit", "car_limit"], "rows": _newlywed_rows(),
            "source": {"quote": ["○2인0인190%"]}},
        "integrated_youth_terms": {
            "label": "통합공공임대 일반공급 청년 소득 비율·소득 가구원수·자산·자동차 한도: 가구원수 × 출산자녀수 × 세대주/세대원 "
                     "(세대원은 본인 소득 1인 기준)",
            "columns": ["size", "child", "head"],
            "inputs": {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"},
                       "head": {"var": "house_head_status"}},
            "outputs": ["ratio", "income_size", "asset_limit", "car_limit"],
            "rows": [r({"size": "any", "child": 0, "head": "세대원"}, [170, 1] + INT_B1),
                     r({"size": "any", "child": "1+", "head": "세대원"}, **no_row(
                         "세대원(본인만 검증)인데 출산자녀 가산 대상 자녀가 있습니다. 세대주 여부 또는 자녀 입력을 확인해 주세요.")),
                     *[dict(x, when=dict(x["when"], head="any"),
                            **({"out": [x["out"][0], "=size"] + x["out"][1:]} if "out" in x else {}))
                       for x in _int_rows()]],
            "source": {"quote": ["청년계층의소득및자산은신청자본인에한하여검증"]}},
    }
    layers = {"청년": {"conditions": youth}, "신혼부부": {"conditions": newlywed}, "한부모": {"conditions": single},
              "고령자": {"conditions": elderly}, "일반": {"conditions": general}}
    return layers, tables


INTEGRATED_NOTES = [
    "판정은 일반공급 기준(기준중위소득 150% + 가산)이다. 우선공급(청년·신혼부부 등, 기준중위소득 100% + 가산)은 모집 인원을 "
    "먼저 배정하는 선정 순서라 판정하지 않는다 — 우선공급 신청자는 같은 주택형 일반공급에도 자동 신청된다.",
    "같은 세대에서 둘 이상 신청하면 모두 무효다(세대주가 아닌 청년 형제는 각각 신청 가능).",
    "과거 공공임대주택에서 불법 양도·전대로 적발된 뒤 4년이 지나지 않은 세대구성원이 있으면 선정될 수 없다 — 이 판정은 묻지 않는다.",
    "청년의 소득·자산은 본인만(세대원이 있는 세대주는 세대 전체), 고령자는 세대 전체를 본다. 입력한 소득·자산이 그 기준인지 확인한다.",
]


# ------------------------------------------------------------------------------------------------
# 공공임대(10년·분양전환·50년) 예비입주자 (G4 — LH 표준 공고: 파주운정3 A12·양주옥정·오산운암6)
# ------------------------------------------------------------------------------------------------
# 예비입주자 모집은 신청 자격이 단순하다: (지역) 거주 + 성년 + 무주택세대구성원 + (공고에 따라) 청약통장, 재당첨 제한.
# 소득·자산은 보지 않는 공고가 대부분이다(리츠·분양전환 "청약저축 가입여부, 소득 및 자산 기준 충족여부와 관계없이") —
# 소득·자산을 보는 공공임대(최초 입주자 모집의 특별·일반공급)는 이 틀이 아니다(sheet_extract가 막는다).
CAPITAL = "수도권"


def capital_areas():
    """수도권 = 서울·인천 + 경기도 시·군(지역 표준 이름 — rules/reference/regions.json)."""
    from rule_data import region_groups
    g = region_groups()
    return list(g["서울·인천"]) + list(g["경기도"])


def public_rental(nid, eligibility_quote, residence=None, account=None, account_quote=None, adult_quote=None,
                  rewin_quote=None):
    """residence: '수도권' 또는 None(거주 요건 없음·국내). account: None(관계없음) / '가입'(2순위도 가입은 필요) /
    {'months': N, 'count': N}(2순위 최소 가입기간·납입횟수). rewin_quote: 재당첨 제한 문구(있으면 그 조건)."""
    p = f"{nid}-PR"
    conds = [cond(f"{p}-home", "home_ownership", [eligibility_quote],
                  "무주택세대구성원인지(세대 전원 무주택, 분양권 등 포함)", HOME)]
    if residence == CAPITAL:
        conds.append(cond(f"{p}-region", "residence_area", [eligibility_quote],
                          "공고일 현재 수도권(서울특별시·인천광역시·경기도)에 주민등록이 되어 있는지",
                          {"in": [{"var": "residence_area"}, capital_areas()]}))
    conds.append(cond(f"{p}-adult", "age", [adult_quote or eligibility_quote],
                      "성년(만 19세 이상)인지 — 미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청 가능",
                      {"any": [{"gte": [{"var": "age"}, 19]},
                               {"lte": [{"var": "age"}, 18],
                                "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                                   "detail": "미성년자는 자녀가 있는 미성년 세대주·형제자매를 부양하는 미성년 세대주 등 "
                                                             "예외에 해당할 때만 신청할 수 있습니다. 예외 해당 여부는 이 화면이 묻지 "
                                                             "않습니다."}}]}))
    if account == "가입":
        conds.append(cond(f"{p}-account", "has_subscription_account", [account_quote],
                          "주택청약종합저축(청약저축 포함)에 가입되어 있는지(2순위도 가입은 필요)",
                          {"eq": [{"var": "has_subscription_account"}, True]}))
    elif isinstance(account, dict):
        conds.append(cond(f"{p}-account", "has_subscription_account/subscription_months/subscription_payment_count",
                          [account_quote],
                          f"청약통장에 가입해 {account['months']}개월이 지났고 월납입금을 {account['count']}회 이상 냈는지"
                          "(2순위 최소 요건)",
                          {"all": [{"eq": [{"var": "has_subscription_account"}, True]},
                                   {"gte": [{"var": "subscription_months"}, account["months"]]},
                                   {"gte": [{"var": "subscription_payment_count"}, account["count"]]}]}))
    if rewin_quote:
        conds.append(cond(f"{p}-rewin", "rewin_restricted", [rewin_quote],
                          "재당첨 제한 기간 중이 아닌지(본인·세대원이 과거 분양주택·분양전환 공공임대 등에 당첨되어 제한 기간이 "
                          "남았으면 신청·계약 불가)", {"eq": [{"var": "rewin_restricted"}, False]}))
    return {"일반": {"conditions": conds}}, {}


# ------------------------------------------------------------------------------------------------
# 신혼희망타운(공공분양) (G3 — LH: 평택고덕 A57-2 잔여세대·시흥하중 A-4 잔여세대)
# ------------------------------------------------------------------------------------------------
# 두 갈래: ① 잔여세대 추가모집 중 '입주자저축 가입 여부, 과거 당첨 여부, 소득 및 자산 요건 불문' 공고 — 거주·만19세·무주택·유형만,
# ② 정규형(최초·잔여) — 수도권 거주 + 유형 + 무주택 + 입주자저축 6개월·6회 + 소득 130%(맞벌이 200%, 출산 가산) + 총자산
# 3억6,200만(출산 가산) + 재당첨 제한 아님 + 과거 특별공급 이력 없음(특별공급은 1회).
# 1·2단계(우선·일반)의 소득 130%(맞벌이 140%)·배점은 선정 순서 — 3단계 추첨(130%/맞벌이 200%)까지 신청할 수 있으므로 그 기준으로 판정.
NH_ASSET = [362000000, 397000000, 431000000]
NH_INCOME = {"lte": [{"var": "monthly_income"},
                     {"lookup": ["income_standard_nhtown", {"fn": "max", "args": [{"var": "household_size"}, 3]},
                                 {"term": "ratio"}]}]}
NH_CHILD6 = {"if": [{"is": [{"var": "has_children"}, False]}, False,
                    {"gte": [{"var": "youngest_child_birth_date"}, {"fn": "young_child_cutoff"}]}]}
NH_DURATION = {"any": [{"gte": [{"var": "marriage_date"}, {"fn": "marriage_cutoff"}]}, NH_CHILD6]}
NH_PREFIX = {"신혼부부": "M", "예비신혼부부": "P", "한부모": "S"}


def newlywed_town_sale(nid, open_quote=None, eligibility_quote=None, residence=None, layer_quotes=None):
    """open_quote: '입주자저축 … 소득 및 자산 요건 불문' 문구(있으면 잔여세대 단순형 — 저축·소득·자산·재당첨·특별공급 이력을 보지
    않는다). eligibility_quote: 거주·나이 문장(단순형). residence: '수도권' 또는 None(전국). layer_quotes: 계층별 자격 문장 머리."""
    q = layer_quotes or {}
    types = {
        "신혼부부": [cond(f"{nid}-NM-marital", "marital_status", [q["신혼부부"]], "혼인 중인지",
                      {"in": [{"var": "marital_status"}, ["혼인중"]]}),
                 cond(f"{nid}-NM-duration", "marriage_duration_or_child", [q["신혼부부"]],
                      "혼인기간 7년 이내이거나 6세 이하 자녀(태아 포함)를 두었는지", NH_DURATION)],
        "예비신혼부부": [cond(f"{nid}-NP-marital", "marital_status", [q["예비신혼부부"]],
                        "예비신혼부부(입주 전까지 혼인 사실 증명)인지", {"in": [{"var": "marital_status"}, ["예비신혼"]]})],
        "한부모": [cond(f"{nid}-NS-marital", "marital_status", [q["한부모"]], "한부모가족인지",
                     {"in": [{"var": "marital_status"}, ["한부모"]]}),
                cond(f"{nid}-NS-child6", "youngest_child_birth_date", [q["한부모"]],
                     "6세 이하(만 7세 미만, 태아 포함) 자녀를 두었는지", NH_CHILD6)],
    }
    layers, tables = {}, {}
    for layer, tcs in types.items():
        p = f"{nid}-N{NH_PREFIX[layer]}"
        head = eligibility_quote or q[layer]
        conds = list(tcs) + [cond(f"{p}-home", "home_ownership", [head],
                                  "무주택세대구성원인지(예비신혼부부는 혼인으로 구성될 세대 전원)", HOME)]
        if residence == CAPITAL:
            conds.append(cond(f"{p}-region", "residence_area", [head],
                              "공고일 현재 수도권(서울특별시·인천광역시·경기도)에 주민등록이 되어 있는지",
                              {"in": [{"var": "residence_area"}, capital_areas()]}))
        if open_quote:
            conds.append(cond(f"{p}-adult", "age", [head], "만 19세 이상인지", {"gte": [{"var": "age"}, 19]}))
        else:
            table = "nhtown_single" if layer == "한부모" else "nhtown_terms"
            conds += [
                cond(f"{p}-account", "has_subscription_account/subscription_months/subscription_payment_count",
                     ["입주자저축에가입하여6개월이경과되고,매월약정납입일에월납입금을6회이상납입한분"],
                     "입주자저축에 가입해 6개월이 지났고 월납입금을 6회 이상 냈는지",
                     {"all": [{"eq": [{"var": "has_subscription_account"}, True]},
                              {"gte": [{"var": "subscription_months"}, 6]},
                              {"gte": [{"var": "subscription_payment_count"}, 6]}]}),
                cond(f"{p}-income", "monthly_income", ["의130%(단,본인및배우자가모두소득이있는경우"],
                     "세대 월평균소득이 전년도 도시근로자 월평균소득의 130%(본인·배우자 모두 소득이 있으면 200%, 출산자녀 1명 "
                     "+10%p·2명 이상 +20%p) 이하인지 — 3인 이하는 3인 기준", NH_INCOME, table=table),
                cond(f"{p}-assets", "total_assets", ["합계액에서5를차감한금액이362"],
                     "세대 총자산이 3억6,200만원(출산자녀 1명 3억9,700만원·2명 이상 4억3,100만원) 이하인지",
                     {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table=table),
                cond(f"{p}-rewin", "rewin_restricted", ["재당첨제한기간내에있는분"],
                     "본인·세대원이 재당첨 제한 기간 중이 아닌지", {"eq": [{"var": "rewin_restricted"}, False]}),
                cond(f"{p}-special", "past_special_supply", ["특별공급은1회에한하여공급함"],
                     "본인·세대원이 과거에 특별공급(신혼희망타운·신혼부부·생애최초·다자녀·노부모부양 등)을 받은 적이 없는지",
                     {"eq": [{"var": "past_special_supply"}, False]}),
            ]
        layers[layer] = {"conditions": conds}
    if not open_quote:
        tables["nhtown_terms"] = {
            "label": "신혼희망타운 소득 비율·총자산 한도: 출산자녀수 × 맞벌이(본인·배우자 모두 근로·사업소득)",
            "columns": ["child", "dual"],
            "inputs": {"child": {"fn": "child_bonus_count"}, "dual": {"var": "dual_income"}},
            "outputs": ["ratio", "asset_limit"],
            "rows": [r({"child": 0, "dual": False}, [130, NH_ASSET[0]]), r({"child": 1, "dual": False}, [140, NH_ASSET[1]]),
                     r({"child": "2+", "dual": False}, [150, NH_ASSET[2]]), r({"child": 0, "dual": True}, [200, NH_ASSET[0]]),
                     r({"child": 1, "dual": True}, [210, NH_ASSET[1]]), r({"child": "2+", "dual": True}, [220, NH_ASSET[2]])],
            "source": {"quote": ["합계액에서5를차감한금액이397", "합계액에서5를차감한금액이431"]}}
        tables["nhtown_single"] = {
            "label": "신혼희망타운 한부모가족 소득 비율·총자산 한도: 출산자녀수(배우자가 없어 맞벌이 가산 없음)",
            "columns": ["child"], "inputs": {"child": {"fn": "child_bonus_count"}},
            "outputs": ["ratio", "asset_limit"],
            "rows": [r({"child": 0}, [130, NH_ASSET[0]]), r({"child": 1}, [140, NH_ASSET[1]]),
                     r({"child": "2+"}, [150, NH_ASSET[2]])],
            "source": {"quote": ["합계액에서5를차감한금액이397", "합계액에서5를차감한금액이431"]}}
    return layers, tables


NHTOWN_NOTES = [
    "1단계 우선공급·2단계 일반공급의 소득 기준(130%, 맞벌이 140%)과 배점·지역 우선(해당 시 거주기간)은 선정 순서다 — "
    "3단계 추첨까지 신청할 수 있으므로 판정은 추첨 기준(130%, 맞벌이 200%)으로 한다.",
    "신혼희망타운에 당첨되면 신혼부부 특별공급을 받은 것으로 보아 이후 다른 주택의 특별공급을 받을 수 없다.",
    "공급가격이 총자산 기준(3억6,200만원)을 넘는 주택은 신혼희망타운 전용 주택담보 장기대출(수익공유형) 가입이 필요하다.",
]


PUBLIC_RENTAL_NOTES = [
    "순위(청약통장 가입기간·납입횟수)·무주택기간·저축총액은 신청자가 모집 인원보다 많을 때의 선정 순서라 판정하지 않는다.",
    "해당 단지 기계약자와 그 세대원은 같은 단지를 신청할 수 없고, 1세대에서 2명 이상 신청하면 모두 부적격이다.",
    "과거 공공임대주택에서 불법 양도·전대로 적발된 뒤 4년이 지나지 않은 세대구성원이 있으면 선정될 수 없다 — 이 판정은 묻지 않는다.",
    "예비입주자는 순번에 따라 입주까지 오래 걸릴 수 있고, 분양전환이 시작되면 예비입주자 지위가 없어진다.",
]


PERMANENT_NOTES = [
    "판정하지 않는 입주자격: 다목(일본군위안부 피해자)·카목(국토교통부장관 또는 시·도지사가 입주가 필요하다고 인정하는 자) — "
    "해당하면 공고문 문의처에 확인한다.",
    "1순위 안의 선정 순서·배점과 2순위는 신청자가 모집 인원보다 많을 때의 순서라 판정하지 않는다.",
    "과거 공공임대주택에서 불법 양도·전대로 적발된 뒤 4년이 지나지 않았으면 선정될 수 없다 — 이 판정은 묻지 않는다.",
]


NATIONAL_NOTES = [
    "순위(전용 50㎡ 미만은 거주지, 50㎡ 이상은 청약저축 납입 횟수)와 배점은 신청자가 모집 인원보다 많을 때의 선정 순서라 "
    "이 판정에 넣지 않았다 — 자격이 있으면 순위와 무관하게 신청할 수 있다.",
    "과거 공공임대주택에서 불법 양도·전대로 적발된 뒤 4년이 지나지 않았으면 선정될 수 없다 — 이 판정은 묻지 않는다.",
    "주거약자용 주택형(고령자·장애인)은 이 판정에 넣지 않았다 — 해당 주택형은 원문 주거약자 기준을 확인한다.",
]

PLAN = [
    dict(nid="N30", key="LH30", title="남양주마석2단지 국민임대주택 예비입주자", ann="2026-09-07",
         program="국민임대주택", template="national_rental", params={"elderly_quote": None},
         notes=NATIONAL_NOTES + ["입주자모집공고일 현재 2세 미만 자녀(태아 포함)가 있으면 모집호수의 30% 범위에서 우선 배정한다(p.3)."]),
    dict(nid="N31", key="LH31", title="김포시지역 국민임대주택 예비입주자(정정)", ann="2026-09-07",
         program="국민임대주택", template="national_rental", params={"elderly_quote": None},
         notes=NATIONAL_NOTES),
    # G2 처음 보는 공고 검증 — 초안은 등록 전에 docs/draft-checks/X-national-bucheon.g2.draft.json에 얼림
    dict(nid="N32", key="LH32", title="부천시지역 국민임대주택 예비입주자", ann="2026-09-07",
         program="국민임대주택", template="national_rental",
         params={"elderly_quote": "범박1단지46형고령자임대주택은(공고일현재65세이상만신청)가능"},
         notes=NATIONAL_NOTES[:2] + [
             "범박1단지 46형 고령자임대주택은 공고일 현재 65세 이상만 신청할 수 있고 다른 주택형과 중복 신청할 수 없다(p.3) — "
             "'일반(고령자 주택형)' 계층으로 판정한다.",
             "입주자모집공고일 현재 2세 미만 자녀(태아 포함)가 있으면 모집호수의 30% 범위에서 우선 배정한다(p.3)."]),
    # 영구임대(개발용) — LH 영구임대 표준 공고
    dict(nid="N33", key="LH33", title="양주회천A25BL 영구임대주택 예비입주자", ann="2026-09-21",
         program="영구임대주택", template="permanent_rental",
         params={"city": "양주시",
                 "residence_quote": "현재양주시에거주(주민등록이등재)하는무주택세대구성원중영구임대주택입주적격자에한합니다",
                 "adult_quote": "「민법」상 미성년자(19세 미만)는 공급신청할 수 없습니다",
                 "weak_quote": "26A1형은주거약자에한하여신청가능합니다"},
         notes=PERMANENT_NOTES + [
             "신청은 양주시 안 주소지 관할 행정복지센터 현장 접수만 받는다(인터넷 신청 불가, p.1·p.3).",
             "26A1형(주거약자용)은 주거약자만 신청할 수 있고, 모집 정원에 못 미쳐도 일반으로 전환하지 않는다(p.2·p.5)."]),
    dict(nid="N34", key="LH34", title="부천시 영구임대주택 예비입주자", ann="2026-09-04",
         program="영구임대주택", template="permanent_rental",
         params={"city": "부천시",
                 "residence_quote": "현재부천시에거주(주민등록등재)하는무주택세대구성원이지원가능하며",
                 "adult_quote": "신청자는 민법상 성년자(만19세)이어야 합니다",
                 "weak_quote": None},
         notes=PERMANENT_NOTES + [
             "같은 공고의 단지(중동한라1·중동덕유1) 중 1개 단지만 신청할 수 있다 — 중복 신청하면 모두 부적격(p.1).",
             "두 단지는 1기 신도시 정비사업 대상으로 입주 후 재건축 등으로 이주할 수 있다(p.1)."]),
    # 통합공공임대 일반형(개발용) — LH 표준 공고
    dict(nid="N35", key="LH35", title="평창장평 통합공공임대주택(일반형)", ann="2026-10-30",
         program="통합공공임대주택", template="integrated_rental", params={},
         notes=INTEGRATED_NOTES + [
             "이 공고의 우선공급은 청년·신혼부부 등만 있고, 31A·36A·46A 주택형마다 우선·일반 배정 호수가 다르다(p.4) — "
             "배정이 없는 입주자격 구분·주택형은 신청할 수 없다.",
             "고령자복지주택 36호는 별도 공고다(p.1)."]),
    # G3 신혼희망타운(공공분양) — 개발용
    dict(nid="N45", key="LH45", title="평택고덕 A-57-2블록 신혼희망타운(공공분양) 추가 입주자", ann="2026-09-08",
         program="신혼희망타운(분양)", template="newlywed_town_sale",
         params={"open_quote": "입주자저축가입여부,과거당첨여부,소득및자산요건을불문",
                 "eligibility_quote": "현재전국에거주(주민등록표등본기준)하는만19세이상의무주택세대구성원", "residence": None,
                 "layer_quotes": {"신혼부부": "혼인기간이7년이내또는6세이하자녀",
                                  "예비신혼부부": "혼인을계획중이며,입주전까지혼인사실을증명할수있는자", "한부모": "를둔부또는모"}},
         notes=["입주자저축 가입 여부·과거 당첨 여부·소득·자산 요건을 불문하며 당첨·계약해도 재당첨 제한을 적용하지 않는다(p.1).",
                "이 단지 당첨자·계약자(본인·세대원)는 신청할 수 없다(p.1). 3세대(전용 55㎡) 무작위 추첨."]),
    dict(nid="N46", key="LH46", title="시흥하중 A-4블록 신혼희망타운(공공분양) 잔여세대", ann="2026-09-18",
         program="신혼희망타운(분양)", template="newlywed_town_sale",
         params={"open_quote": None, "eligibility_quote": None, "residence": CAPITAL,
                 "layer_quotes": {
                     "신혼부부": "현재수도권[서울특별시,인천광역시,경기도]에거주하면서아래조건(1~4)을모두갖춘신혼부부",
                     "예비신혼부부": "현재수도권[서울특별시,인천광역시,경기도]에거주하면서아래조건(1~4)을모두갖춘예비신혼부부",
                     "한부모": "현재수도권[서울특별시,인천광역시,경기도]에거주하면서아래조건(1~4)을모두갖춘한부모가족"}},
         notes=NHTOWN_NOTES + ["시흥시 1년 이상 거주자가 우선이며 재당첨 제한은 10년, 전매 제한은 3년이다(p.2)."]),
    # G3 처음 보는 공고 — 판정 틀을 만든 뒤 등록 전에 초안을 얼림(docs/draft-checks/Y-nhtown-*.g3.draft.json)
    dict(nid="N47", key="LH47", title="수원당수 A-3블록 신혼희망타운(공공분양) 잔여세대(입주 후 해약)", ann="2026-09-29",
         program="신혼희망타운(분양)", template="newlywed_town_sale",
         params={"open_quote": "청약저축가입여부,소득·자산요건,과거당첨사실여부를불문",
                 "eligibility_quote": "현재전국에거주(주민등록표등본기준)하는만19세이상의무주택세대구성원", "residence": None,
                 "layer_quotes": {"신혼부부": "혼인기간이7년이내또는6세이하자녀",
                                  "예비신혼부부": "혼인을계획중이며,입주전까지혼인사실을증명할수있는자", "한부모": "를둔부또는모"}},
         notes=["청약저축 가입 여부·소득·자산 요건·과거 당첨 사실 여부를 불문하며 당첨·계약해도 재당첨 제한을 적용하지 않는다(p.1).",
                "이 단지 최초·추가 모집 기당첨자와 계약자(본인·세대원)는 신청할 수 없다(p.1). 해약 세대가 고른 옵션 그대로 공급한다."]),
    dict(nid="N48", key="LH48", title="안산신길2 A-6블록 신혼희망타운(공공분양) 입주자", ann="2026-10-30",
         program="신혼희망타운(분양)", template="newlywed_town_sale",
         params={"open_quote": None, "eligibility_quote": None, "residence": CAPITAL,
                 "layer_quotes": {
                     "신혼부부": "현재수도권[서울특별시,인천광역시,경기도]에거주하면서아래조건(1~4)을모두갖춘신혼부부",
                     "예비신혼부부": "현재수도권[서울특별시,인천광역시,경기도]에거주하면서아래조건(1~4)을모두갖춘예비신혼부부",
                     "한부모": "현재수도권[서울특별시,인천광역시,경기도]에거주하면서아래조건(1~4)을모두갖춘한부모가족"}},
         unsupported=[{"name": "사전청약당첨자", "page": 15,
                       "note": "2021.12.29. 사전청약 당첨자(입주예약자)의 본청약 — 사전청약 당시 자격·거주기간 기준이 따로 있어 판정하지 "
                               "않는다(공고문 III-1)."}],
         notes=NHTOWN_NOTES + ["안산시 거주자가 우선이며, 사전청약 당첨자(입주예약자)가 먼저 주택형을 배정받는다(p.15)."]),
    # G4 공공임대(10년·분양전환·50년) 예비입주자 — 개발용
    dict(nid="N37", key="LH37", title="파주운정3 A12BL 분양전환 공공임대주택(리츠) 예비입주자", ann="2026-05-28",
         program="공공임대주택", template="public_rental",
         params={"eligibility_quote": "현재수도권에거주(주민등록표등본기준)하는무주택세대구성원", "residence": CAPITAL,
                 "account": None, "account_quote": None, "adult_quote": None,
                 "rewin_quote": "재당첨제한자추후계약체결불가"},
         notes=PUBLIC_RENTAL_NOTES + ["청약저축 가입 여부, 소득·자산 기준과 상관없이 신청할 수 있다(p.1)."]),
    dict(nid="N38", key="LH38", title="양주옥정 10년 공공임대주택(리츠) 예비입주자", ann="2026-06-24",
         program="공공임대주택", template="public_rental",
         params={"eligibility_quote": "현재서울특별시,인천광역시및경기도지역에거주(주민등록표등본기준)하는성년자(19세이상)인무주택세대구성원",
                 "residence": CAPITAL, "account": None, "account_quote": None, "adult_quote": None,
                 "rewin_quote": "재당첨제한기간중에있는경우청약및계약할수없으며"},
         notes=PUBLIC_RENTAL_NOTES + ["A-20(2)·A-20(3)·A-21(1)·A-21(2)BL 4개 단지 — 인터넷·모바일 청약만(현장 접수 없음, p.1)."]),
    dict(nid="N39", key="LH39", title="오산운암6단지 50년 공공임대주택 예비입주자", ann="2026-06-10",
         program="공공임대주택", template="public_rental",
         params={"eligibility_quote": "현재주택건설지역(경기도,서울특별시,인천광역시)에거주하는무주택세대구성원", "residence": CAPITAL,
                 "account": "가입", "account_quote": "2순위예비입주자모집공고일(2026.06.10)현재주택청약종합저축(청약저축포함)에가입되어있고",
                 "adult_quote": "「민법」상미성년자(만19세미만)는공급신청할수없습니다", "rewin_quote": None},
         notes=PUBLIC_RENTAL_NOTES[:1] + PUBLIC_RENTAL_NOTES[2:3] + [
             "동일 순위에서는 오산시 거주자가 먼저이고, 1순위(가입 1년·12회 이상) 접수에서 모집 수를 넘으면 2순위는 받지 않는다(p.5~6)."]),
    # G4 처음 보는 공고 검증 — 판정 틀을 만든 뒤 등록 전에 초안을 얼림(docs/draft-checks/Y-*.g4.draft.json, 구리는 X-…g4)
    dict(nid="N40", key="LH40", title="김포한강 Ac-01a블록 10년 공공임대주택(리츠) 예비입주자", ann="2026-06-19",
         program="공공임대주택", template="public_rental",
         params={"eligibility_quote": "현재수도권(서울특별시,인천광역시,경기도)에거주(주민등록표등본기준)하는무주택세대구성원",
                 "residence": CAPITAL, "account": None, "account_quote": None, "adult_quote": None,
                 "rewin_quote": "재당첨제한기간중에해당할경우계약불가"},
         notes=PUBLIC_RENTAL_NOTES + ["청약저축 가입 여부·과거 당첨 사실·소득·자산과 상관없이 신청할 수 있으나, 계약일이 재당첨 제한 "
                                      "기간 중이면 계약할 수 없다(p.1)."]),
    dict(nid="N41", key="LH41", title="대전천동 35BL 10년 분양전환 공공임대주택 예비입주자", ann="2026-09-29",
         program="공공임대주택", template="public_rental",
         params={"eligibility_quote": "현재국내에거주하는성년자인무주택세대구성원", "residence": None, "account": None,
                 "account_quote": None, "adult_quote": None, "rewin_quote": None},
         notes=PUBLIC_RENTAL_NOTES + ["청약저축 가입 여부·과거 당첨 사실·소득·자산 요건을 불문한다(p.1). 계약하면 계약자와 세대원은 "
                                      "3년 동안 다른 분양주택에 당첨될 수 없다(재당첨 제한 3년, p.1)."]),
    dict(nid="N42", key="LH42", title="김포한강 센트럴블루힐 10년 공공임대주택(리츠) 예비입주자", ann="2025-10-28",
         program="공공임대주택", template="public_rental",
         params={"eligibility_quote": "현재수도권(서울특별시,인천광역시,경기도)에거주(주민등록표등본기준)하는성년자(만19세이상)인무주택세대구성원",
                 "residence": CAPITAL, "account": None, "account_quote": None, "adult_quote": None,
                 "rewin_quote": "재당첨제한기간중에해당할경우계약불가"},
         notes=PUBLIC_RENTAL_NOTES + ["예비입주자 순번은 무작위 추첨으로 정한다(p.9)."]),
    dict(nid="N43", key="LH43", title="구리갈매 S1블록 10년 공공임대주택 예비입주자", ann="2026-10-22",
         program="공공임대주택", template="public_rental",
         params={"eligibility_quote": "현재수도권(서울특별시,경기도,인천광역시)에거주(주민등록표등본기준)하는성년자(만19세이상)인무주택세대구성원",
                 "residence": CAPITAL, "account": {"months": 6, "count": 6},
                 "account_quote": "2순위입주자저축(주택청약종합저축,청약저축)에가입하여6월이경과된분으로서매월약정납입일에월납입금을6회이상",
                 "adult_quote": None, "rewin_quote": "재당첨제한기간내에있는분"},
         notes=PUBLIC_RENTAL_NOTES[:1] + PUBLIC_RENTAL_NOTES[2:] + [
             "1순위는 입주자저축 가입 2년·24회 이상, 2순위는 6개월·6회 이상 — 선순위 접수에서 모집 호수를 넘으면 후순위는 받지 않는다(p.6·p.9).",
             "부적격 당첨 후 입주자로 선정될 수 없는 기간 중인 사람도 신청할 수 없다(p.5) — 이 판정은 묻지 않는다."]),
    dict(nid="N44", key="LH44", title="동해천곡5 50년 공공임대주택 예비입주자", ann="2026-06-09",
         program="공공임대주택", template="public_rental",
         params={"eligibility_quote": "현재무주택세대구성원", "residence": None, "account": "가입",
                 "account_quote": "2순위예비입주자모집공고일(2026.06.09)현재주택청약종합저축(청약저축포함)에가입되어있고",
                 "adult_quote": "「민법」상미성년자(만19세미만)는공급신청할수없습니다", "rewin_quote": None},
         notes=PUBLIC_RENTAL_NOTES[:1] + PUBLIC_RENTAL_NOTES[2:3] + [
             "1순위(가입 6개월·6회 이상) 접수에서 모집 수를 넘으면 2순위는 받지 않는다(p.5~6)."]),
    # G2 처음 보는 공고 검증 — 초안은 등록 전에 docs/draft-checks/X-integrated-gangseo.g2.draft.json에 얼림
    dict(nid="N36", key="LH36", title="강서염창 통합공공임대주택(정정)", ann="2026-09-17",
         program="통합공공임대주택", template="integrated_rental", params={},
         notes=INTEGRATED_NOTES + [
             "이 공고의 우선공급은 덕수연립 가로주택정비사업 기존 거주자(철거민 등) 중 조합이 선정해 LH에 통보한 사람만 신청할 "
             "수 있다(별도 안내, 현장 접수) — 판정 대상 아님(p.4·p.15).",
             "일반공급은 59A형 10호다(p.4). 준공이 끝난 단지로 2027년 2월 입주 예정이다."]),
]

ANCHORS = {"일반": ("신청자격", 5), "일반(고령자 주택형)": ("신청자격", 5), "일반(주거약자용)": ("신청자격", 5)}
# 통합공공임대는 계층 이름(일반 등)이 다른 사업과 겹치고, 같은 문구가 우선공급(p.15~16)·일반공급(p.16~18)에 다 있어
# 일반공급 쪽을 가리키는 기준점을 템플릿별로 둔다(인용문·기준표 모두).
TEMPLATE_ANCHOR = {"integrated_rental": ("신혼부부,한부모가족을제외한모든계층", 17), "public_rental": ("무주택세대구성원", 1),
                   "newlywed_town_sale": ("신혼부부신청자격", 11)}


def pdf_for(key):
    index = json.loads((ROOT / "docs" / "notice-analysis" / "index.json").read_text(encoding="utf-8"))
    return ROOT / next(x["file"] for x in index if x["key"] == key)


def walk(conditions):
    for c in conditions:
        yield c
        for t in c.get("tracks", []):
            yield from walk(t["conditions"])


# 템플릿(사업별 규칙 생성 함수) — 공고별 값은 PLAN의 params(파라미터 시트, P1 docs/09 §5)
BUILDERS = {"national_rental": national_rental, "permanent_rental": permanent_rental, "integrated_rental": integrated_rental,
            "public_rental": public_rental, "newlywed_town_sale": newlywed_town_sale}
ISSUER = {"national_rental": "LH", "permanent_rental": "LH", "integrated_rental": "LH", "public_rental": "LH",
          "newlywed_town_sale": "LH"}


def make_doc(plan, pdf, pages):
    """PLAN 항목(또는 같은 모양의 파라미터 시트) + 원문 쪽 텍스트 → 공고 규칙 문서. 인용문 쪽은 원문에서 찾고,
    찾지 못한 인용문은 missing으로 돌려준다(새 공고에서 문구가 달라진 조건을 드러낸다)."""
    layers, tables = BUILDERS[plan["template"]](plan["nid"], **plan["params"])
    missing = []
    own = TEMPLATE_ANCHOR.get(plan["template"])
    for layer, ldoc in layers.items():
        text, hint = own or ANCHORS[layer]
        anchor = locate(pages, text, hint) or hint
        for c in walk(ldoc["conditions"]):
            place_quotes(c["source"], pages, anchor, f"{layer}/{c['id']}", missing)
    for name, t in tables.items():
        anchor = (locate(pages, *own) or own[1]) if own else (locate(pages, "소득및자산보유기준", 6) or 6)
        place_quotes(t["source"], pages, anchor, f"table:{name}", missing)
    doc = {
        "notice_id": plan["nid"], "title": plan["title"], "announcement_date": plan["ann"],
        "issuer": ISSUER[plan["template"]], "program": plan["program"],
        "version": 1, "valid_from": plan["ann"], "supersedes": None,
        "source": {"document": pdf.name, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "pages": len(pages)},
        "review": {"status": "DRAFT", "note": "G2 생성(tools/gen_c6_public.py). 원문 표 수치는 손으로 옮김. 독립 검토 전.",
                   "log": []},
        "notes": plan["notes"], "unsupported_layers": plan.get("unsupported", []), "tables": tables, "layers": layers,
    }
    return doc, missing


def main():
    import logging
    logging.disable(logging.CRITICAL)
    for plan in PLAN:
        pdf = pdf_for(plan["key"])
        doc, missing = make_doc(plan, pdf, sv.extract_pages(pdf))
        out = ROOT / "rules" / "notices" / f"{plan['nid']}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(plan["nid"], plan["title"], list(doc["layers"]), "MISSING", len(missing))
        for m in missing:
            print("   -", m)


if __name__ == "__main__":
    main()
