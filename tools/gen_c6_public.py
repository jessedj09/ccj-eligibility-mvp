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
import copy
import hashlib
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import source_verify as sv  # noqa: E402
from rule_engine import years_before  # noqa: E402

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
# 자산·자동차 한도 표기: 표준 공고는 백만원·만원 단위("(345)백만원", "0명(기준) 34,500 4,542"), 인제서화(N58 p.5)는 원 단위 한 표
# ("…소득50%초과소득70%이하1인0인90%345,000,00045,420,000…") — 금액은 같다
NATIONAL_MONEY = {
    "million": dict(assets=["총자산가액 합산기준 (345)백만원 이하"], car=["개별자동차가액 (4,542)만원 이하"],
                    table=["0명(기준) 34,500 4,542", "1명 37,900 4,996", "2명 41,300 5,451"]),
    "won": dict(assets=["적용자산기준금액총자산가액(원)자동차가액(원)", "소득50%초과소득70%이하1인0인90%345,000,00045,420,000"],
                car=["적용자산기준금액총자산가액(원)자동차가액(원)", "소득50%초과소득70%이하1인0인90%345,000,00045,420,000"],
                table=["소득50%초과소득70%이하1인0인90%345,000,00045,420,000", "1인90%379,000,00049,960,000",
                       "2인이상90%413,000,00054,510,000"]),
}


def national_rental(nid, elderly_quote=None, money="million"):
    """elderly_quote: 고령자 전용 주택형 문구(예: 부천 p.3 '범박1단지46형고령자임대주택은(공고일현재65세이상만신청)가능') —
    있으면 같은 자격에 '공고일 현재 65세 이상'을 더한 계층을 만든다. money: 자산·자동차 한도 표기(NATIONAL_MONEY)."""
    p = f"{nid}-G"
    terms = "national_terms"
    mq = NATIONAL_MONEY[money]
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
        cond(f"{p}-assets", "total_assets", mq["assets"],
             "세대 전원의 총자산이 3억4,500만원(출산자녀 1명 3억7,900만원·2명 이상 4억1,300만원) 이하인지",
             {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table=terms),
        cond(f"{p}-car", "car_value", mq["car"],
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
        "source": {"quote": list(mq["table"])},
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
# SH 국민임대 (SH 2026년 국민임대주택 입주자모집 — p.22~25 신청자격·소득·자산, p.29 주거약자)
# ------------------------------------------------------------------------------------------------
# 자격은 LH 국민임대와 같은 법령 기준(소득 70% + 1인 +20%p·2인 +10%p·출생자녀 가산, 총자산 3억4,500만·자동차 4,542만)에
# 서울 거주가 더해진다. 전용 50㎡ 미만의 '50% 이하 먼저'와 59㎡의 청약저축 회차·해당구/연접구 거주는 경쟁 시 순서(순위)라 판정하지 않는다.
# 소득 기준표는 원문 표가 1~6인만 적으므로 LH 표(1~8인)와 섞지 않고 income_standard_sh_public을 따로 둔다.
SH_NEAR = ["의정부시", "남양주시", "양주시", "포천시"]      # 상계장암지구 1·2단지(의정부시는 3·4단지도)만 서울 밖 거주자 신청 가능


# 공고 해마다 바뀌는 값: 소득 기준표(전년도 도시근로자 월평균소득)와 총자산·자동차 한도. 원문 자산 표 리터럴(단위 만원)로 판을 고른다.
# '2026': N53(2026.08.20.) p.25 2025년도 소득, 기본 34,500·4,542 / '2025': N60(2025.08.20.) p.24 2024년도 소득, 기본 33,700·3,803
SH_NATIONAL_EDITION = {
    "2026": dict(ref="income_standard_sh_public", limits=(B1, B2, B3),
                 quotes=["기본34,5004,542", "10%p가산37,9004,996", "20%p가산41,3005,451"],
                 assets="3억4,500만원(출생자녀 1명 3억7,900만원·2명 이상 4억1,300만원)",
                 car="4,542만원(출생자녀 1명 4,996만원·2명 이상 5,451만원)"),
    "2025": dict(ref="income_standard_sh_public_2024",
                 limits=([337000000, 38030000], [371000000, 41830000], [405000000, 45630000]),
                 quotes=["기본33,7003,803", "10%p가산37,1004,183", "20%p가산40,5004,563"],
                 assets="3억3,700만원(출생자녀 1명 3억7,100만원·2명 이상 4억500만원)",
                 car="3,803만원(출생자녀 1명 4,183만원·2명 이상 4,563만원)"),
}


def sh_national_rental(nid, eligibility_quote, adult_quote, income_quote, near_quote=None, weak_quote=None, edition="2026"):
    """near_quote: 서울 밖 일부 시 거주자도 받는 단지 문구(상계장암) — 있으면 그 시 거주자는 확인 필요로 둔다.
    weak_quote: 일반공급(주거약자) 자격 문구 — 있으면 같은 자격 + 주거약자 본인 계층.
    edition: 소득 기준표·자산 한도 판(SH_NATIONAL_EDITION)."""
    p = f"{nid}-S"
    terms = "sh_national_terms"
    ed = SH_NATIONAL_EDITION[edition]
    b1, b2, b3 = ed["limits"]
    region = {"in": [{"var": "residence_area"}, ["서울특별시"]]}
    if near_quote:
        region = {"any": [region, {"in": [{"var": "residence_area"}, SH_NEAR],
                                   "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                                      "detail": "서울 밖(의정부·남양주·양주·포천시) 거주자는 상계장암지구 1·2단지"
                                                                "(의정부시는 3·4단지도)에만 신청할 수 있습니다. 신청할 단지를 확인하세요."}}]}
    conditions = [
        cond(f"{p}-home", "home_ownership", [eligibility_quote], "무주택세대구성원인지(세대 전원 무주택, 분양권 등 포함)", HOME),
        cond(f"{p}-region", "residence_area", [eligibility_quote] + ([near_quote] if near_quote else []),
             "공고일 현재 서울특별시에 주민등록이 되어 있는지" + ("(상계장암지구는 일부 경기 시도)" if near_quote else ""), region),
        cond(f"{p}-adult", "age", [adult_quote],
             "성년(만 19세 이상)인지 — 미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청 가능",
             {"any": [{"gte": [{"var": "age"}, 19]},
                      {"lte": [{"var": "age"}, 18],
                       "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                          "detail": "미성년자는 자녀가 있는 미성년 세대주·형제자매를 부양하는 미성년 세대주 등 "
                                                    "예외에 해당할 때만 신청할 수 있습니다. 예외 해당 여부는 이 화면이 묻지 않습니다."}}]}),
        cond(f"{p}-income", "monthly_income", [income_quote, "소득기준가산요건", "가구원수에따른가산항목및비율"],
             "세대 전원의 월평균소득 합계가 70%(1인 +20%p·2인 +10%p, 2023.3.28. 이후 출생자녀 1명 +10%p·2명 이상 +20%p) 기준 이내인지",
             {"lte": [{"var": "monthly_income"},
                      {"lookup": [ed["ref"], {"var": "household_size"}, {"term": "ratio"}]}]},
             table=terms),
        cond(f"{p}-assets", "total_assets", ["부동산,자동차,금융자산,기타자산을합산한금액에서부채를차감하여", ed["quotes"][0]],
             f"세대 전원의 총자산이 {ed['assets']} 이하인지",
             {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table=terms),
        cond(f"{p}-car", "car_value", [ed["quotes"][0]],
             f"자동차가액(여러 대면 가장 높은 차량가액)이 {ed['car']} 이하인지",
             {"lte": [CAR, {"term": "car_limit"}]}, table=terms),
    ]
    tables = {terms: {
        "label": "SH 국민임대 소득 비율·자산·자동차 한도: 가구원수 × 출생자녀수(가구원수 가산과 출생자녀 가산을 더함)",
        "columns": ["size", "child"],
        "inputs": {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"}},
        "outputs": ["ratio", "asset_limit", "car_limit"],
        "rows": [
            r({"size": 1, "child": 0}, [90] + b1),
            r({"size": 1, "child": "1+"}, **no_row(C3.D_ALONE_CHILD)),
            r({"size": 2, "child": 0}, [80] + b1),
            r({"size": 2, "child": 1}, [90] + b2),
            r({"size": 2, "child": "2+"}, **no_row(C3.D_TWO_KIDS)),
            r({"size": "3+", "child": 0}, [70] + b1),
            r({"size": "3+", "child": 1}, [80] + b2),
            r({"size": "3+", "child": "2+"}, [90] + b3),
        ],
        "source": {"quote": list(ed["quotes"])},
    }}
    layers = {"일반": {"conditions": conditions}}
    if weak_quote:
        weak = json.loads(json.dumps(conditions, ensure_ascii=False).replace(f'"{p}-', f'"{nid}-SW-'))
        weak.append(cond(f"{nid}-SW-weak", "age/housing_weak_type", [weak_quote],
                         "공급신청자 본인이 주거약자(만 65세 이상, 장애인, 상이 1~7급 국가유공자·보훈보상대상자, 5·18 부상자, "
                         "고엽제후유의증환자, 국가유공자에 준하는 군경)인지",
                         {"any": [{"gte": [{"var": "age"}, 65]}, {"in": [{"var": "housing_weak_type"}, WEAK_TYPES]}]}))
        layers["일반(주거약자용)"] = {"conditions": weak}
    return layers, tables


# ------------------------------------------------------------------------------------------------
# SH 영구임대 (SH 2025년 영구임대주택 예비입주자 모집공고 — p.7 신청자격, p.8 성년, p.9~10 소득·자산)
# ------------------------------------------------------------------------------------------------
# 「공공주택 특별법 시행규칙」 별표3 일반공급 1순위(가~자)만 받는다(LH 영구임대의 2순위 차·타 없음). 서울 거주.
# 기준표 금액·자산 한도가 LH 영구임대(2025년 9월 공고)와 다르다 — 표(income_standard_sh_permanent)·한도를 따로 둔다.
SHP_B1, SHP_B2, SHP_B3 = [237000000, 45630000], [261000000, 50200000], [285000000, 54760000]


def _sh_money(prefix, income_quote, asset_quote, car_quote):
    return [
        cond(f"{prefix}-income", "monthly_income", [income_quote],
             "세대 월평균소득이 70%(1인 90%·2인 80%, 출생자녀 1명 +10%p·2명 이상 +20%p) 이하인지",
             {"lte": [{"var": "monthly_income"},
                      {"lookup": ["income_standard_sh_permanent", {"var": "household_size"}, {"term": "ratio70"}]}]},
             table="sh_permanent_terms"),
        cond(f"{prefix}-assets", "total_assets", [asset_quote],
             "세대 총자산이 2억3,700만원(출생자녀 1명 2억6,100만·2명 이상 2억8,500만) 이하인지",
             {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table="sh_permanent_terms"),
        cond(f"{prefix}-car", "car_value", [car_quote],
             "자동차가액(가장 높은 차량가액)이 4,563만원(출생자녀 1명 5,020만·2명 이상 5,476만) 이하인지",
             {"lte": [CAR, {"term": "car_limit"}]}, table="sh_permanent_terms"),
    ]


def sh_permanent_rental(nid, eligibility_quote, adult_quote, income_quote, asset_quote, car_quote):
    p = f"{nid}-SP"

    def m(pre):
        return _sh_money(pre, income_quote, asset_quote, car_quote)
    disabled = {"any": [{"eq": [{"var": "housing_weak_type"}, "장애인"]},
                        {"eq": [{"var": "disabled_spouse_qualifies"}, True]}]}
    tracks = [
        {"id": "가", "label": "생계급여 또는 의료급여 수급자(소득·자산 검증 없음)", "conditions": [
            cond(f"{p}-Ta", "livelihood_medical_recipient", ["제7조제1항제1호에따른생계급여수급자또는같은항제3호에따른의료급여수급자"],
                 "생계급여 또는 의료급여 수급자인지(주거·교육급여만 받는 경우는 아님)",
                 {"eq": [{"var": "livelihood_medical_recipient"}, True]})]},
        {"id": "나", "label": "국가유공자·보훈보상대상자·5·18·특수임무·참전유공자(유족 포함), 소득 70%", "conditions": [
            cond(f"{p}-Tb", "merit_person", ["「국가유공자등예우및지원에관한법률」에따른국가유공자또는그유족"],
                 "국가유공자·보훈보상대상자·5·18민주유공자·특수임무유공자(또는 그 유족)·참전유공자인지",
                 {"eq": [{"var": "merit_person"}, True]})] + m(f"{p}-Tb")},
        {"id": "라", "label": "지원대상 한부모가족(소득·자산 검증 없음)", "conditions": [
            cond(f"{p}-Td", "is_supported_single_parent", ["여성가족부장관이정하는기준에해당하는지원대상한부모가족"],
                 "지원대상 한부모가족(한부모가족 증명서 발급 대상)인지", {"eq": [{"var": "is_supported_single_parent"}, True]})]},
        {"id": "마", "label": "북한이탈주민, 소득 70%", "conditions": [
            cond(f"{p}-Te", "north_korean_defector", ["「북한이탈주민의보호및정착지원에관한법률」제2조제1호에따른북한이탈주민으로서"],
                 "북한이탈주민인지", {"eq": [{"var": "north_korean_defector"}, True]})] + m(f"{p}-Te")},
        {"id": "바", "label": "장애인(지적·정신·중증 뇌병변장애인은 그 배우자 포함), 소득 70%", "conditions": [
            cond(f"{p}-Tf", "housing_weak_type/disabled_spouse_qualifies", ["「장애인복지법」제32조에따라장애인등록증이교부된사람"],
                 "장애인등록증이 교부된 장애인이거나, 지적·정신·중증 뇌병변장애인의 배우자인지", disabled)] + m(f"{p}-Tf")},
        {"id": "사", "label": "65세 이상 직계존속 부양자로서 수급자 선정기준 소득인정액 이하", "conditions": [
            cond(f"{p}-Tg", "supports_elderly_parent", ["65세이상의직계존속(배우자의직계존속을포함한다)을부양"],
                 "만 65세 이상 직계존속(배우자 부모 포함)을 같은 등본에서 부양하는지 — 소득인정액은 이 화면이 계산하지 않는다",
                 {"eq": [{"var": "supports_elderly_parent"}, True],
                  "review_if_true": {"code": "SELF_REPORT_UNVERIFIED",
                                     "detail": "65세 이상 직계존속 부양자는 생계·의료급여 수급자 선정기준의 '소득인정액' 이하여야 "
                                               "합니다. 소득인정액(소득+재산 환산액)은 이 화면이 계산하지 않으니 주민센터에 확인하세요."}})]},
        {"id": "아", "label": "아동복지시설 퇴소자(시설장 추천), 소득 70%", "conditions": [
            cond(f"{p}-Th", "child_facility_leaver", ["아동복지시설에서퇴소하는사람중아동복지시설의장이추천하는사람"],
                 "아동복지시설에서 퇴소하며 시설장의 추천을 받았는지", {"eq": [{"var": "child_facility_leaver"}, True]})] + m(f"{p}-Th")},
        {"id": "자", "label": "65세 이상 수급권자 또는 차상위계층", "conditions": [
            cond(f"{p}-Ti", "age/welfare_status", ["65세이상인사람으로서「국민기초생활보장법」제2조제1호에따른수급권자"],
                 "만 65세 이상이고 기초생활 수급권자(급여 종류 무관) 또는 차상위계층인지",
                 {"all": [{"gte": [{"var": "age"}, 65]}, {"in": [{"var": "welfare_status"}, WELFARE_ANY]}]})]},
    ]
    common = [
        cond(f"{p}-home", "home_ownership", [eligibility_quote], "무주택세대구성원인지(세대 전원 무주택, 분양권 등 포함)", HOME),
        cond(f"{p}-region", "residence_area", [eligibility_quote], "공고일 현재 서울특별시에 주민등록이 되어 있는지",
             {"in": [{"var": "residence_area"}, ["서울특별시"]]}),
        cond(f"{p}-adult", "age", [adult_quote],
             "성년(만 19세 이상)인지 — 미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청 가능",
             {"any": [{"gte": [{"var": "age"}, 19]},
                      {"lte": [{"var": "age"}, 18],
                       "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                          "detail": "미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청할 수 있습니다. "
                                                    "예외 해당 여부는 이 화면이 묻지 않습니다."}}]}),
        {"id": f"{p}-rank", "field": "입주자격", "required": True,
         "source": {"quote": ["제7조제1항제1호에따른생계급여수급자또는같은항제3호에따른의료급여수급자"]},
         "note": "「공공주택 특별법 시행규칙」 별표3 영구임대 일반공급 1순위(가~자) 중 하나 이상에 해당하는지 "
                 "(신분마다 소득 기준이 다름 — 수급자·한부모 등 없음 / 70%). 다목(일본군위안부 피해자)은 이 판정이 묻지 않는다.",
         "tracks": tracks},
    ]
    tables = {"sh_permanent_terms": {
        "label": "SH 영구임대 소득 비율(70% 기준)·자산·자동차 한도: 가구원수 × 출생자녀수",
        "columns": ["size", "child"],
        "inputs": {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"}},
        "outputs": ["ratio70", "asset_limit", "car_limit"],
        "rows": [
            r({"size": 1, "child": 0}, [90] + SHP_B1),
            r({"size": 1, "child": "1+"}, **no_row(C3.D_ALONE_CHILD)),
            r({"size": 2, "child": 0}, [80] + SHP_B1),
            r({"size": 2, "child": 1}, [90] + SHP_B2),
            r({"size": 2, "child": "2+"}, **no_row(C3.D_TWO_KIDS)),
            r({"size": "3+", "child": 0}, [70] + SHP_B1),
            r({"size": "3+", "child": 1}, [80] + SHP_B2),
            r({"size": "3+", "child": "2+"}, [90] + SHP_B3),
        ],
        "source": {"quote": ["1인0인90%237,000,00045,630,000", "1인90%261,000,00050,200,000", "2인이상90%285,000,00054,760,000"]},
    }}
    return {"일반": {"conditions": common}}, tables


# ------------------------------------------------------------------------------------------------
# LH 고령자복지주택(영구임대형) (평택고덕 A-58 — p.5 신청자격, p.6 순위·소득, p.7 자산)
# ------------------------------------------------------------------------------------------------
# 「공공주택 특별법 시행규칙」 별표6의4 제1호 특례: 만 65세 이상 무주택세대구성원 + 1순위 가(생계·의료급여) / 2순위 나(국가유공자 등,
# 소득 70%) / 3순위 차(소득 50%). 나·차는 영구임대 자산(총자산 24,500만·자동차 4,542만). 원문에 출생자녀 가산이 없다 — 넣지 않는다.
# 소득표는 원문이 50%·70% 열(1~7인)만 적어 income_standard_elderly로 따로 둔다. 거주 지역 요건 없음.
ELD_ASSETS, ELD_CAR = 245000000, 45420000


# ------------------------------------------------------------------------------------------------
# SH 다자녀 매입임대 (2026.5.29. — p.3 요약, p.6 신청자격·순위, p.9~10 소득·자산)
# ------------------------------------------------------------------------------------------------
# 공통: 미성년 직계비속(태아 포함) 2명 이상을 양육하는 무주택세대구성원(서울 거주 요건 없음 — 타지역 거주자도 신청 가능).
# 1순위(신생아가구)·2순위: 수급자(생계·주거·의료·교육급여)·차상위계층·지원대상 한부모가족 — 소득·자산 검증 없음.
# 3순위: 월평균소득 70%(2025년도 표, 국민임대와 같은 금액) + 총자산 34,500만·자동차 4,542만(출생자녀 가산 37,900·41,300 / 4,996·5,451).
# 1순위와 2순위의 차이(신생아가구)는 선정 순서라 하나의 갈래로 판정한다. 금액 문구는 이 공고의 리터럴(다른 해 금액이면 추출기가 보류).
MULTI_B = ([345000000, 45420000], [379000000, 49960000], [413000000, 54510000])


def sh_multichild_rental(nid, eligibility_quote, income_quote, asset_quote, car_quote):
    p = f"{nid}-M"
    terms = "multichild_terms"
    tracks = [
        {"id": "수급자등", "label": "1·2순위 — 수급자(생계·주거·의료·교육급여)·차상위계층·지원대상 한부모가족(소득·자산 검증 없음)",
         "conditions": [
             cond(f"{p}-Twelfare", "welfare_status/is_supported_single_parent",
                  ["생계·주거·의료·교육급여중어느하나에해당하는급여를받는수급자가구", "제2조제10호에해당하는차상위계층가구",
                   "제3조에따라여성가족부장관이정하는기준에해당하는한부모가족"],
                  "수급자(생계·주거·의료·교육급여)·차상위계층 가구이거나 지원대상 한부모가족(증명서 발급 가능)인지",
                  {"any": [{"in": [{"var": "welfare_status"}, WELFARE_ANY]},
                           {"eq": [{"var": "is_supported_single_parent"}, True]}]})]},
        {"id": "일반", "label": "3순위 — 그 밖의 다자녀가구(월평균소득 70% 이하 + 국민임대 자산 기준)", "conditions": [
            cond(f"{p}-income", "monthly_income", [income_quote],
                 "세대 월평균소득이 전년도(2025) 도시근로자 가구원수별 월평균소득의 70% 이하인지",
                 {"lte": [{"var": "monthly_income"}, {"lookup": ["income_standard_public", {"var": "household_size"}, 70]}]}),
            cond(f"{p}-assets", "total_assets", [asset_quote],
                 "세대 총자산이 3억4,500만원(출생자녀 1명 3억7,900만원·2명 이상 4억1,300만원) 이하인지",
                 {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table=terms),
            cond(f"{p}-car", "car_value", [car_quote],
                 "자동차가액이 4,542만원(출생자녀 1명 4,996만원·2명 이상 5,451만원) 이하인지",
                 {"lte": [CAR, {"term": "car_limit"}]}, table=terms)]},
    ]
    conditions = [
        cond(f"{p}-home", "home_ownership", [eligibility_quote], "무주택세대구성원인지(세대 전원 무주택, 분양권 등 포함)", HOME),
        cond(f"{p}-kids", "children_birth_dates", [eligibility_quote],
             "미성년 자녀(태아 포함, 조손가정은 같은 등본의 미성년 손자녀)가 2명 이상인지", {"gte": [MINORS, 2]}),
        cond(f"{p}-adult", "age", ["민법상미성년자(19세미만)는공급신청이불가하나"],
             "성년(만 19세 이상)인지 — 미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청 가능",
             {"any": [{"gte": [{"var": "age"}, 19]},
                      {"lte": [{"var": "age"}, 18],
                       "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                          "detail": "미성년자는 자녀가 있는 미성년 세대주 등 예외에 해당할 때만 신청할 수 있습니다. "
                                                    "예외 해당 여부는 이 화면이 묻지 않습니다."}}]}),
        {"id": f"{p}-rank", "field": "입주자격", "required": True,
         "source": {"quote": ["1·2순위(수급자,차상위계층,보호대상한부모가족)는소득및자산검증대상에서제외"]},
         "note": "신청 순위(1·2순위 수급자·차상위·지원대상 한부모 / 3순위 소득 70%·자산) 중 하나인지", "tracks": tracks},
    ]
    tables = {terms: {
        "label": "SH 다자녀 매입임대 3순위 총자산·자동차 한도: 출생자녀수('23.3.28. 이후 출생 자녀 — 1명 / 1명+이전 자녀·2명 이상)",
        "columns": ["child"], "inputs": {"child": {"fn": "child_bonus_count"}},
        "outputs": ["asset_limit", "car_limit"],
        "rows": [r({"child": 0}, MULTI_B[0]), r({"child": 1}, MULTI_B[1]), r({"child": "2+"}, MULTI_B[2])],
        "source": {"quote": ["총자산가액379,000,000원이하413,000,000원이하413,000,000원이하",
                             "자동차가액49,960,000원이하54,510,000원이하54,510,000원이하"]},
    }}
    return {"다자녀가구": {"conditions": conditions}}, tables


def elderly_welfare(nid, eligibility_quote, merit_quote, general_quote, kind="영구임대",
                    asset_quote="가액합산기준24,500만원이하", car_quote="개별자동차가액4,542만원이하"):
    """kind: 공고가 영구임대형인지(추출기가 확인 — 아니면 자동 판정하지 않는다). 한도 문구는 리터럴과 같은 공고에서만 찾아진다."""
    p = f"{nid}-EW"
    lim = "elderly_terms"

    def money(pre, term, quote, pct):
        return [
            cond(f"{pre}-income", "monthly_income", [quote], f"세대 월평균소득이 {pct} 이하인지(가구원수 가산만, 출생자녀 가산 없음)",
                 {"lte": [{"var": "monthly_income"},
                          {"lookup": ["income_standard_elderly", {"var": "household_size"}, {"term": term}]}]}, table=lim),
            cond(f"{pre}-assets", "total_assets", [asset_quote], "세대 총자산이 2억4,500만원 이하인지",
                 {"lte": [{"var": "total_assets"}, ELD_ASSETS]}),
            cond(f"{pre}-car", "car_value", [car_quote], "자동차가액(가장 높은 차량가액)이 4,542만원 이하인지",
                 {"lte": [CAR, ELD_CAR]}),
        ]
    tracks = [
        {"id": "가", "label": "1순위 — 생계급여 또는 의료급여 수급자(소득·자산 검증 없음)", "conditions": [
            cond(f"{p}-Ta", "livelihood_medical_recipient", ["가.국민기초생활보장법상의생계급여수급자또는의료급여수급자"],
                 "생계급여 또는 의료급여 수급자인지", {"eq": [{"var": "livelihood_medical_recipient"}, True]})]},
        {"id": "나", "label": "2순위 — 국가유공자·보훈보상대상자·5·18·특수임무·참전유공자(유족 포함), 소득 70%", "conditions": [
            cond(f"{p}-Tb", "merit_person", ["국가유공자등예우및지원에관한법률에따른국가유공자또는그유족"],
                 "국가유공자·보훈보상대상자·5·18민주유공자·특수임무유공자(또는 그 유족)·참전유공자인지",
                 {"eq": [{"var": "merit_person"}, True]})] + money(f"{p}-Tb", "ratio70", merit_quote, "70%(1인 90%·2인 80%)")},
        {"id": "차", "label": "3순위 — 일반(소득 50%)", "conditions": money(f"{p}-Tc", "ratio50", general_quote, "50%(1인 70%·2인 60%)")},
    ]
    common = [
        cond(f"{p}-age", "age", [eligibility_quote], "공고일 현재 만 65세 이상인지", {"gte": [{"var": "age"}, 65]}),
        cond(f"{p}-home", "home_ownership", [eligibility_quote], "무주택세대구성원인지(세대 전원 무주택, 분양권 등 포함)", HOME),
        {"id": f"{p}-rank", "field": "입주자격", "required": True,
         "source": {"quote": ["가.국민기초생활보장법상의생계급여수급자또는의료급여수급자"]},
         "note": "고령자복지주택 공급 신청자격 순위(1순위 가 생계·의료급여 / 2순위 나 국가유공자 등 70% / 3순위 차 일반 50%) 중 하나인지",
         "tracks": tracks},
    ]
    tables = {lim: {
        "label": "고령자복지주택 소득 비율(가구원수 가산만): 2순위 70%(1인 90%·2인 80%), 3순위 50%(1인 70%·2인 60%)",
        "columns": ["size"],
        "inputs": {"size": {"var": "household_size"}},
        "outputs": ["ratio70", "ratio50"],
        "rows": [r({"size": 1}, [90, 70]), r({"size": 2}, [80, 60]), r({"size": "3+"}, [70, 50])],
        "source": {"quote": ["1인가구2,669,354원이하3,432,027원이하"]},
    }}
    return {"고령자": {"conditions": common}}, tables


# ------------------------------------------------------------------------------------------------
# LH 나눔형(이익공유형) 공공분양 (뉴홈 4차 사전청약 2024.01.03. — p.1 <표1>, p.7 <표3>, p.9~13 유형별 신청자격)
# ------------------------------------------------------------------------------------------------
# 2024.3. 규칙 개정 전 공고다 — 신생아 특별공급이 없고, 신혼부부 맞벌이 140%, 출생자녀 가산 없음, 자동차 한도 없음(총자산에 포함).
# 소득은 2023년도 도시근로자 표(income_standard_share_sale, 3인 이하는 3인 기준), 청년은 본인 1인 140%. 금액·비율 문구는 이 공고의
# 리터럴이라 다른 해 공고(맞벌이 200% 등)에서는 추출기가 필수 값을 보류해 자동 판정하지 않는다. 사전청약 당첨자 유형은 없다.
SHARE_SECTION = {"청년": "1.청년특별공급■신청자격", "신혼부부": "2.신혼부부특별공급■신청자격", "생애최초": "3.생애최초특별공급■신청자격",
                 "일반공급": "4.일반공급■신청자격"}
SHARE_ASSET, SHARE_YOUTH_ASSET, SHARE_PARENTS = 379000000, 289000000, 1083000000
SHARE_SIZE = {"fn": "max", "args": [{"var": "household_size"}, 3]}


def _share_income(p, ratio, quote, note):
    return cond(f"{p}-income", "monthly_income", [quote], note,
                {"lte": [{"var": "monthly_income"}, {"lookup": ["income_standard_share_sale", SHARE_SIZE, ratio]}]})


# 2026 판(2024.3. 개정 뒤 본청약 — 고양창릉 S-3 2026.06.30.): 신생아 특별공급, 맞벌이 200%, 출산가구 소득·자산 +10/+20%p,
# 2025년도 소득표, 세대 총자산 362백만·청년 본인 276백만·부모 1,035백만. 자격 기준이 SH 토지임대부(N51·N52, 같은 해 같은 법령)와
# 같아 그 판정 틀(sh_land_sale, 투기과열 아님)을 쓰고 인용문만 LH 공고 표현으로 바꾼다. 유형별 우선·일반·추첨공급 중 가장 넓은 단계
# (추첨공급)의 소득 기준이 신청 자격이다 — 더 낮은 단계 비율은 선정 순서.
SHARE_2026_QUOTES = {
    "로혼인중이아니며,과거주택을소유한사실이없는무주택자": "로혼인중이아니며,과거주택을소유한사실이없는사람으로한정)인분",
    "19세이상~39세이하": "청년(19세이상39세이하로혼인중이아니며",
    "(청년계층은신청자본인276백만원이하": "(청년특별공급은신청자본인276,000천원이하",
    "부모1,035백만원이하": "및부모1,035,000천원이하",
    "혼인기간이7년이내이거나": "혼인중인사람으로서혼인기간이7년이내",
    "예비신혼부부[혼인을계획중이고": "예비신혼부부[혼인을계획중이며",
    "한부모가족[6세이하의자녀": "한부모가족[6세이하(만7세미만을말함)자녀",
    "의130%(단,본인및배우자가모두소득이있는경우에는200%)이하인분": "의130%(본인및배우자가모두소득이있는경우200%)이하인분",
    "의140%(단,본인및배우자가모두소득이있는경우에는200%)이하인분": "의140%(본인및배우자가모두소득이있는경우200%)이하인분",
    "의100%이하인분(단,본인및배우자가모두소득이있는경우에는200%)": "의100%(본인및배우자가모두소득이있는경우200%)이하인분",
    "합계액에서5를차감한금액이362백만원이하": "합계액에서5를차감한금액이362,000천원이하",
    "무주택세대구성원으로입주자저축": "무주택세대구성원(3페이지참조)으로서입주자저축에가입한분",
    "(신청자본인)311백만원이하": "본인311,000천원이하",
    "(신청자본인)345백만원이하": "본인345,000천원이하",
    "397백만원이하": "397,000천원이하",
    "431백만원이하": "431,000천원이하",
}
SHARE_2026_LABEL = {"SH 토지임대부": "LH 나눔형(2026 판)"}


def _share_sale_2026(nid, residence, youth_income_quote, asset_quote, youth_asset_quote, parents_quote, dual_quote):
    layers, tables = sh_land_sale(nid, residence, overheated=False)
    extra = {"income": None}

    def fix(source):
        source["quote"] = [SHARE_2026_QUOTES.get(q, q) for q in source.get("quote", [])]

    for layer, ld in layers.items():
        for c in walk(ld["conditions"]):
            fix(c["source"])
            suffix = c["id"].rsplit("-", 1)[-1]
            add = {("청년", "income"): youth_income_quote, ("청년", "assets"): youth_asset_quote,
                   ("청년", "parents"): parents_quote}.get((layer, suffix))
            if add is None and layer != "청년":
                add = {"assets": asset_quote, "income": dual_quote}.get(suffix)
            if add and add not in c["source"]["quote"]:
                c["source"]["quote"].append(add)
    for t in tables.values():
        fix(t["source"])
        for a, b in SHARE_2026_LABEL.items():
            t["label"] = t["label"].replace(a, b)
    return layers, tables


def lh_share_sale(nid, residence="수도권", youth_income_quote="청년도시근로자가구원수별가구당월평균소득액의140%4,695,438원",
                  asset_quote="379,000천원이하", youth_asset_quote="289백만원이하", parents_quote="(부모)1,083백만원이하",
                  dual_quote="맞벌이도시근로자가구당월평균소득액의140%9,113,233원", edition="2024"):
    """residence: '수도권' 또는 None. *_quote: 이 공고의 금액·비율 문구(추출기가 같은 문구일 때만 채운다).
    edition: '2024'(2024.1. 사전청약 — 개정 전) / '2026'(개정 뒤 본청약 — SHARE_2026_QUOTES)."""
    if edition == "2026":
        return _share_sale_2026(nid, residence, youth_income_quote, asset_quote, youth_asset_quote, parents_quote, dual_quote)
    layers = {}
    for i, layer in enumerate(["청년", "신혼부부", "생애최초", "일반공급"]):
        p = f"{nid}-N{i}"
        head = SHARE_SECTION[layer]
        if layer == "청년":
            conds = [cond(f"{p}-home", "home_ownership/self_ever_owned_home",
                          ["만19세이상~만39세이하로혼인중이아니며,과거주택을소유한사실이없는무주택자"],
                          "본인이 무주택이고 과거에도 주택을 소유한 적이 없는지",
                          {"all": [HOME, {"eq": [{"var": "self_ever_owned_home"}, False]}]}),
                     cond(f"{p}-age", "age", ["만19세이상~만39세이하로혼인중이아니며"], "만 19세 이상 39세 이하인지",
                          {"between": [{"var": "age"}, 19, 39]}),
                     cond(f"{p}-marital", "marital_status", ["만19세이상~만39세이하로혼인중이아니며"], "혼인 중이 아닌지",
                          {"in": [{"var": "marital_status"}, ["미혼", "예비신혼", "한부모"]]})]
        else:
            conds = [cond(f"{p}-home", "home_ownership", [head], "무주택세대구성원인지(예비신혼부부는 혼인으로 구성될 세대 전원)", HOME)]
        if residence == CAPITAL:
            conds.append(cond(f"{p}-region", "residence_area", ["에거주하면서아래조건"] if layer != "청년" else
                              ["[서울특별시,경기도,인천광역시](공급규칙제4조제3항에따른지역을말함)에거주"],
                              "공고일 현재 서울특별시·인천광역시·경기도에 주민등록이 되어 있는지",
                              {"in": [{"var": "residence_area"}, capital_areas()]}))
        conds.append(cond(f"{p}-rewin", "rewin_restricted", ["재당첨제한기간내에있는"],
                          "본인·세대원이 재당첨 제한 기간 중이 아닌지(부적격 당첨 후 1년 이내도 신청 불가)",
                          {"eq": [{"var": "rewin_restricted"}, False]}))
        if layer != "일반공급":
            conds.append(cond(f"{p}-special", "past_special_supply", ["특별공급은1회에한하여공급함"],
                              "본인·세대원이 과거에 특별공급을 받은 적이 없는지",
                              {"eq": [{"var": "past_special_supply"}, False]}))
        if layer in ("청년", "신혼부부"):
            conds.append(_sale_account(p, 6, "에가입하여6개월이경과되고,매월약정납입일에월납입금을6회이상납입한분",
                                       "입주자저축에 가입해 6개월이 지났고 월납입금을 6회 이상 냈는지"))
        if layer == "청년":
            conds += [cond(f"{p}-income", "monthly_income", [youth_income_quote],
                           "본인 월평균소득이 전년도(2023) 도시근로자 1인 가구 월평균소득의 140%(4,695,438원) 이하인지",
                           {"lte": [{"var": "monthly_income"}, {"lookup": ["income_standard_share_sale", 1, 140]}]}),
                      cond(f"{p}-assets", "total_assets", [youth_asset_quote], "본인 총자산이 2억8,900만원 이하인지",
                           {"lte": [{"var": "total_assets"}, SHARE_YOUTH_ASSET]}),
                      cond(f"{p}-parents", "parents_total_assets", [parents_quote], "부모 총자산이 10억8,300만원 이하인지",
                           {"lte": [{"var": "parents_total_assets"}, SHARE_PARENTS]})]
        elif layer == "신혼부부":
            conds += [cond(f"{p}-type", "marital_status/marriage_date/children_birth_dates",
                           ["혼인기간이7년이내"],
                           "혼인 7년 이내이거나 6세 이하 자녀를 둔 신혼부부, 예비신혼부부, 또는 6세 이하 자녀를 둔 한부모가족인지",
                           {"any": [{"all": [{"in": [{"var": "marital_status"}, ["혼인중"]]}, NH_DURATION]},
                                    {"in": [{"var": "marital_status"}, ["예비신혼"]]},
                                    {"all": [{"in": [{"var": "marital_status"}, ["한부모"]]}, NH_CHILD6]}]}),
                      cond(f"{p}-income", "monthly_income/dual_income",
                           ["외벌이도시근로자가구당월평균소득액의130%8,462,288원", dual_quote],
                           "세대 월평균소득이 2023년 도시근로자 월평균소득의 130%(맞벌이 140%) 이하인지 — 3인 이하는 3인 기준",
                           {"lte": [{"var": "monthly_income"},
                                    {"if": [{"eq": [{"var": "dual_income"}, True]},
                                            {"lookup": ["income_standard_share_sale", SHARE_SIZE, 140]},
                                            {"lookup": ["income_standard_share_sale", SHARE_SIZE, 130]}]}]})]
        elif layer == "생애최초":
            conds += [cond(f"{p}-first", "household_ever_owned_home", ["세대에속한모든분이과거주택소유사실이없어야"],
                           "세대 전원이 과거에 주택을 소유한 적이 없는지",
                           {"eq": [{"var": "household_ever_owned_home"}, False]}),
                      _sale_account(p, 12, "월납입금을12회이상납입한자)에해당하는무주택세대구성원으로서저축액이선납금을포함하여600만원이상",
                                    "입주자저축 1순위(가입 1년·월납입금 12회 이상)인지"),
                      cond(f"{p}-deposit", "subscription_deposit",
                           ["월납입금을12회이상납입한자)에해당하는무주택세대구성원으로서저축액이선납금을포함하여600만원이상"],
                           "청약 저축액(선납금 포함)이 600만원 이상인지", {"gte": [{"var": "subscription_deposit"}, 6000000]}),
                      cond(f"{p}-family", "marital_status/children_birth_dates", ["혼인(재혼포함)중이거나미혼인자녀"],
                           "혼인 중이거나 미혼 자녀(같은 등본, 입양 포함)가 있는지",
                           {"any": [{"in": [{"var": "marital_status"}, ["혼인중"]]}, {"gte": [MINORS, 1]},
                                    {"in": [{"var": "marital_status"}, ["미혼", "예비신혼", "한부모"]],
                                     "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                                        "detail": "성년이어도 미혼 자녀가 같은 등본에 있으면 신청할 수 있습니다. 이 화면은 "
                                                                  "미성년 자녀만 묻습니다."}}]}),
                      cond(f"{p}-tax", "income_tax_5y", ["신청자본인이5년이상소득세"],
                           "신청자 본인이 5년 이상 소득세(근로·사업소득)를 냈고 현재 근로자·자영업자이거나 과거 1년 안에 냈는지",
                           {"eq": [{"var": "income_tax_5y"}, True]}),
                      _share_income(p, 130, "130%이하인분",
                                    "세대 월평균소득이 2023년 도시근로자 월평균소득의 130% 이하인지 — 3인 이하는 3인 기준")]
        else:
            conds += [cond(f"{p}-account", "has_subscription_account", ["무주택세대구성원으로입주자저축"],
                           "입주자저축(청약통장)에 가입했는지", {"eq": [{"var": "has_subscription_account"}, True]}),
                      _share_income(p, 100, "일반공급도시근로자가구당월평균소득액의100%6,509,452원",
                                    "세대 월평균소득이 2023년 도시근로자 월평균소득의 100% 이하인지 — 3인 이하는 3인 기준")]
        if layer != "청년":
            conds.append(cond(f"{p}-assets", "total_assets", [asset_quote], "세대 총자산이 3억7,900만원 이하인지(자동차 포함)",
                              {"lte": [{"var": "total_assets"}, SHARE_ASSET]}))
        layers[layer] = {"conditions": conds}
    return layers, {}


# ------------------------------------------------------------------------------------------------
# LH 선택형 공공임대 (뉴홈 4차 사전청약 2024.01.04. — p.1 <표1>, p.9~10 <표3>·<표4>, p.11~17 유형별 신청자격)
# ------------------------------------------------------------------------------------------------
# 6년 임대 뒤 분양 전환을 선택하는 분양전환공공임대. 2024.3. 규칙 개정 전 공고(신생아 특별공급 없음, 다자녀 3명, 출생자녀 가산 없음).
# 소득은 가구원수별(1인·2인 완화) 2023년도 표(income_standard_select_rental) — 유형별 실효 비율을 결정표로 둔다(우선공급의 더 낮은
# 비율은 선정 순서라 판정하지 않고 잔여공급 기준으로 판정). 기관추천 특별공급은 미지원 계층.
SELECT_SECTION = {"청년": "2.청년특별공급■신청자격", "다자녀가구": "3.다자녀가구특별공급■신청자격",
                  "노부모부양": "4.노부모부양특별공급■신청자격", "생애최초": "5.생애최초특별공급■신청자격",
                  "신혼부부": "6.신혼부부특별공급■신청자격", "일반공급": "7.일반공급■신청자격"}
# 유형별 소득 비율(가구원수 1·2·3+). None = 그 가구원수로는 신청할 수 없는 조합(입력 확인)
SELECT_RATIO = {"다자녀가구": (None, None, 120), "노부모부양": (None, 130, 120), "생애최초": (None, 140, 130),
                "일반공급": (120, 110, 100)}
SELECT_DUAL = {False: (None, 140, 130), True: (None, 150, 140)}      # 신혼부부 외벌이·맞벌이
D_SELECT_SIZE = "이 유형은 이 가구원수로 신청할 수 없습니다(다자녀는 자녀 3명 이상, 노부모부양·생애최초·신혼부부는 2인 이상). 입력을 확인해 주세요."


def _select_terms(layer):
    sizes = (1, 2, "3+")
    if layer == "신혼부부":
        rows = [r({"size": s, "dual": d}, [SELECT_DUAL[d][i]]) if SELECT_DUAL[d][i] else
                r({"size": s, "dual": d}, **no_row(D_SELECT_SIZE)) for d in (False, True) for i, s in enumerate(sizes)]
        return {"label": "선택형 신혼부부 소득 비율: 가구원수 × 맞벌이(2인 140·150%, 3인 이상 130·140%)", "columns": ["size", "dual"],
                "inputs": {"size": {"var": "household_size"}, "dual": {"var": "dual_income"}}, "outputs": ["ratio"], "rows": rows,
                "source": {"quote": ["130%(단,맞벌이인경우에는140%)이하[가구원수가2명인경우140%(가구원수가2명이면서맞벌이인경우에는150%)]"]}}
    ratio = SELECT_RATIO[layer]
    rows = [r({"size": s}, [ratio[i]]) if ratio[i] else r({"size": s}, **no_row(D_SELECT_SIZE)) for i, s in enumerate(sizes)]
    quote = {"다자녀가구": "다자녀가구특별공급소득기준3인4인5인6인7인8인", "노부모부양": "노부모부양도시근로자가구원수별가구당월평균소득액의130%6,506,989",
             "생애최초": "의130%이하(가구원수가2명인경우140%)인분", "일반공급": "일반공급도시근로자가구원수별가구당월평균소득액의120%4,024,661"}[layer]
    return {"label": f"선택형 {layer} 소득 비율: 가구원수({'·'.join(str(x) + '%' for x in ratio if x)})", "columns": ["size"],
            "inputs": {"size": {"var": "household_size"}}, "outputs": ["ratio"], "rows": rows, "source": {"quote": [quote]}}


# 2026 판(2024.3. 개정 뒤 본청약 — 6년 분양전환 공공임대 최초 모집, 군포대야미 A-1 2026.06.30. p.9~22): 유형 조건은 LH 공공분양(N49·N50)과
# 같고 자산은 세대 총자산 362백만(출산 397·431), 청년 특별공급(본인 140%·본인 276백만·부모 1,035백만)은 SH 토지임대부와 같다. 소득은
# **가구원수별** 2025년도 표(income_standard_select_rental_2025 — 3인 이하 3인 기준이 아님)에 유형별 실효 비율(가장 넓은 추첨공급 단계):
# 일반 1인 120·2인 110·3인+ 100, 다자녀 3인+ 120, 노부모 2인 130·3인+ 120, 생애최초·신혼 2인 140·3인+ 130, 신생아 2인 150·3인+ 140,
# 맞벌이 200, 출산자녀 1명 +10%p·2명 이상 +20%p. 원문 표에 220%(맞벌이 + 출산자녀 2명 이상) 금액이 없어 그 조합은 확인 필요.
SELECT26_RATIO = {"일반공급": {1: 120, 2: 110, 3: 100}, "다자녀가구": {3: 120}, "노부모부양": {2: 130, 3: 120},
                  "생애최초": {2: 140, 3: 130}, "신혼부부": {2: 140, 3: 130}, "신생아": {2: 150, 3: 140}}
SELECT26_INCOME_Q = {
    "일반공급": "의100%[본인및배우자가모두소득이있는경우200%,가구원수가1명인경우에는120%,가구원수가2명인경우에는110%"
                "(본인및배우자가모두소득이있는경우에는200%)]이하인분",
    "다자녀가구": "의120%(본인및배우자가모두소득이있는경우200%)이하인분",
    "노부모부양": "의120%[본인및배우자가모두소득이있는경우200%,가구원수가2명인경우에는130%(본인및배우자가모두소득이있는경우에는200%)]이하인분",
    "생애최초": "의130%[본인및배우자가모두소득이있는경우200%,가구원수가2명인경우에는140%(본인및배우자가모두소득이있는경우에는200%)]이하인분",
    "신혼부부": "의130%[본인및배우자가모두소득이있는경우200%,가구원수가2명인경우에는140%(본인및배우자가모두소득이있는경우에는200%)]이하인분",
    "신생아": "의140%[본인및배우자가모두소득이있는경우200%,가구원수가2명인경우에는150%(본인및배우자가모두소득이있는경우에는200%)]이하인분",
}
SELECT_2026_QUOTES = {
    "로혼인중이아니며,과거주택을소유한사실이없는무주택자": "로혼인중이아니며,과거주택을소유한사실이없는사람으로한정)",
    "19세이상~39세이하": "청년(19세이상39세이하로혼인중이아니며",
    "신청자본인의월평균소득이": "본인의월평균소득이\"<표4>전년도도시근로자가구원수별가구당월평균소득\"의140%이하인분",
    "(청년계층은신청자본인276백만원이하": "(청년특별공급은신청자본인276,000천원이하",
    "부모1,035백만원이하": "및부모1,035,000천원이하",
    "(신청자본인)311백만원이하": "본인311,000천원이하",
    "(신청자본인)345백만원이하": "본인345,000천원이하",
    "2세미만의자녀(2세가되는날을포함)": "2세미만의자녀(2세가되는날을포함,태아포함)",
    "무주택세대구성원으로서입주자저축에가입한분": "으로서입주자저축에가입한분",
}
SELECT_2026_ORDER = ["청년", "다자녀가구", "노부모부양", "생애최초", "신혼부부", "신생아", "일반공급"]
D_SELECT26_SIZE = "이 유형은 이 가구원수로 신청할 수 없는 조합입니다(예: 다자녀가구 2인 이하, 맞벌이 1인). 가구원수·자녀·맞벌이 입력을 확인해 주세요."
D_SELECT26_220 = "원문 출산가구 소득 완화 표에 맞벌이 + 출산자녀 2명 이상(220%) 금액이 없습니다 — 공고 기관에 소득 기준을 확인하세요."


def _select26_table(layer):
    ratio = SELECT26_RATIO[layer]
    rows = []
    for size in (1, 2, "3+"):
        base = ratio.get(3 if size == "3+" else size)
        for dual in (False, True):
            for k, child in enumerate((0, 1, "2+")):
                when = {"size": size, "child": child, "dual": dual}
                if base is None or (dual and size == 1) or (size == 1 and k):
                    rows.append(r(when, **no_row(D_SELECT26_SIZE)))
                    continue
                pct = (200 if dual else base) + 10 * k
                if pct == 220:
                    rows.append(r(when, result="NO_ROW", no_row={"code": "AMBIGUOUS_SOURCE", "detail": D_SELECT26_220}))
                else:
                    rows.append(r(when, [pct, SH_ASSET[k]]))
    return {"label": f"선택형(2026 판) {layer} 소득 비율·총자산 한도: 가구원수(1·2·3인 이상) × 출산자녀수 × 맞벌이",
            "columns": ["size", "child", "dual"],
            "inputs": {"size": {"var": "household_size"}, "child": {"fn": "child_bonus_count"}, "dual": {"var": "dual_income"}},
            "outputs": ["ratio", "asset_limit"], "rows": rows,
            "source": {"quote": ["397,000천원이하", "431,000천원이하"]}}


def _select_rental_2026(nid, residence, youth_income_quote, asset_quote, youth_asset_quote, parents_quote, dual_quote):
    youth_layers, youth_tables = sh_land_sale(nid, residence, overheated=False)
    sale_layers, _ = public_sale(nid, residence, small=True, large=False)
    sale_layers["일반공급"] = sale_layers.pop("일반공급(전용 60㎡ 이하)")
    layers, tables = {"청년": youth_layers["청년"]}, {"sh_youth_terms": youth_tables["sh_youth_terms"]}
    for layer in SELECT_2026_ORDER[1:]:
        table = f"select26_{SELECT_2026_ORDER.index(layer)}"
        tables[table] = _select26_table(layer)
        conds = []
        for c in sale_layers[layer]["conditions"]:
            if c["id"].endswith(("-realestate", "-car")):
                continue
            if c["id"].endswith("-income"):
                c = cond(c["id"], "monthly_income/dual_income", [SELECT26_INCOME_Q[layer]],
                         f"세대 월평균소득이 2025년도 도시근로자 가구원수별 월평균소득의 {layer} 기준 비율(가구원수·맞벌이·출산자녀 가산) "
                         "이하인지",
                         {"lte": [{"var": "monthly_income"},
                                  {"lookup": ["income_standard_select_rental_2025", {"var": "household_size"}, {"term": "ratio"}]}]},
                         table=table)
            conds.append(c)
        prefix = conds[0]["id"].rsplit("-", 1)[0]
        conds.append(cond(f"{prefix}-assets", "total_assets", ["합계액에서5를차감한금액이362,000천원이하", asset_quote],
                          "세대 총자산이 3억6,200만원(출산자녀 1명 3억9,700만원·2명 이상 4억3,100만원) 이하인지",
                          {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table=table))
        layers[layer] = {"conditions": conds}
    for ld in layers.values():
        for c in walk(ld["conditions"]):
            c["source"]["quote"] = [SELECT_2026_QUOTES.get(q, q) for q in c["source"].get("quote", [])]
    for t in tables.values():
        t["source"]["quote"] = [SELECT_2026_QUOTES.get(q, q) for q in t["source"].get("quote", [])]
    for c in walk(layers["청년"]["conditions"]):
        add = {"income": youth_income_quote, "assets": youth_asset_quote, "parents": parents_quote}.get(c["id"].rsplit("-", 1)[-1])
        if add and add not in c["source"]["quote"]:
            c["source"]["quote"].append(add)
        if c["id"].endswith("-income"):     # 청년 소득표도 가구원수별 표의 1인 칸
            c["check"] = {"lte": [{"var": "monthly_income"},
                                  {"lookup": ["income_standard_select_rental_2025", 1, {"term": "ratio"}]}]}
    tables["sh_youth_terms"]["label"] = "선택형(2026 판) 청년 본인 소득 비율·본인 총자산 한도: 출산자녀수"
    if dual_quote:
        for layer in SELECT_2026_ORDER[1:]:
            for c in layers[layer]["conditions"]:
                if c["id"].endswith("-income") and dual_quote not in c["source"]["quote"] and dual_quote in SELECT26_INCOME_Q[layer]:
                    c["source"]["quote"].append(dual_quote)
    return layers, tables


def lh_select_rental(nid, residence="수도권", youth_income_quote="청년특별공급도시근로자가구원수별가구당월평균소득액의140%4,695,438",
                     asset_quote="379,000천원이하", youth_asset_quote="289,000천원이하", parents_quote="1,083,000천원",
                     dual_quote="맞벌이도시근로자가구원수별가구당월평균소득액의140%9,405,477원", edition="2024"):
    """residence: '수도권' 또는 None. *_quote: 이 공고의 금액 문구(추출기가 같은 문구일 때만 채운다).
    edition: '2024'(2024.1. 사전청약 — 개정 전) / '2026'(개정 뒤 6년 분양전환 공공임대 최초 모집 — _select_rental_2026)."""
    if edition == "2026":
        return _select_rental_2026(nid, residence, youth_income_quote, asset_quote, youth_asset_quote, parents_quote, dual_quote)
    layers, tables = {}, {}
    for i, layer in enumerate(["청년", "다자녀가구", "노부모부양", "생애최초", "신혼부부", "일반공급"]):
        p = f"{nid}-L{i}"
        head = SELECT_SECTION[layer]
        if layer == "청년":
            conds = [cond(f"{p}-home", "home_ownership/self_ever_owned_home",
                          ["만19세이상~만39세이하로혼인중이아니며,과거주택을소유한사실이없는무주택자"],
                          "본인이 무주택이고 과거에도 주택을 소유한 적이 없는지",
                          {"all": [HOME, {"eq": [{"var": "self_ever_owned_home"}, False]}]}),
                     cond(f"{p}-age", "age", ["만19세이상~만39세이하로혼인중이아니며"], "만 19세 이상 39세 이하인지",
                          {"between": [{"var": "age"}, 19, 39]}),
                     cond(f"{p}-marital", "marital_status", ["만19세이상~만39세이하로혼인중이아니며"], "혼인 중이 아닌지",
                          {"in": [{"var": "marital_status"}, ["미혼", "예비신혼", "한부모"]]})]
        else:
            conds = [cond(f"{p}-home", "home_ownership", [head], "무주택세대구성원인지(예비신혼부부는 혼인으로 구성될 세대 전원)", HOME)]
        if residence == "수도권":
            conds.append(cond(f"{p}-region", "residence_area", ["에거주하면서아래조건"] if layer not in ("청년", "일반공급") else
                              ["[서울특별시,경기도,인천광역시](공급규칙제4조제3항에따른지역을말함)에거"] if layer == "청년" else [head],
                              "공고일 현재 서울특별시·인천광역시·경기도에 주민등록이 되어 있는지",
                              {"in": [{"var": "residence_area"}, capital_areas()]}))
        conds.append(cond(f"{p}-rewin", "rewin_restricted", ["재당첨제한기간내에있는"],
                          "본인·세대원이 재당첨 제한 기간 중이 아닌지(부적격 당첨 후 1년 이내도 신청 불가)",
                          {"eq": [{"var": "rewin_restricted"}, False]}))
        if layer != "일반공급":
            conds.append(cond(f"{p}-special", "past_special_supply", ["특별공급은1회에한하여공급함"],
                              "본인·세대원이 과거에 특별공급을 받은 적이 없는지",
                              {"eq": [{"var": "past_special_supply"}, False]}))
        if layer in ("청년", "다자녀가구", "신혼부부"):
            conds.append(_sale_account(p, 6, "에가입하여6개월이경과되고",
                                       "입주자저축에 가입해 6개월이 지났고 월납입금을 6회 이상 냈는지"))
        if layer == "청년":
            conds += [cond(f"{p}-income", "monthly_income", [youth_income_quote],
                           "본인 월평균소득이 전년도(2023) 도시근로자 1인 가구 월평균소득의 140%(4,695,438원) 이하인지",
                           {"lte": [{"var": "monthly_income"}, {"lookup": ["income_standard_select_rental", 1, 140]}]}),
                      cond(f"{p}-assets", "total_assets", [youth_asset_quote], "본인 총자산이 2억8,900만원 이하인지",
                           {"lte": [{"var": "total_assets"}, 289000000]}),
                      cond(f"{p}-parents", "parents_total_assets", [parents_quote], "부모 총자산이 10억8,300만원 이하인지",
                           {"lte": [{"var": "parents_total_assets"}, 1083000000]})]
            layers[layer] = {"conditions": conds}
            continue
        if layer == "다자녀가구":
            conds.append(cond(f"{p}-kids", "children_birth_dates", ["인자녀(태아나입양아포함)3명이상을둔무주택세대"],
                              "19세 미만 자녀(태아·입양 포함)가 3명 이상인지", {"gte": [MINORS, 3]}))
        elif layer == "노부모부양":
            conds += [cond(f"{p}-parent", "supports_elderly_parent_3y", ["을3년이상계속하여부양"],
                           "만 65세 이상 직계존속(배우자 직계존속 포함)을 같은 등본에서 3년 이상 계속 부양하는지",
                           {"eq": [{"var": "supports_elderly_parent_3y"}, True]}),
                      cond(f"{p}-head", "house_head_status", ["무주택세대구성원중세대주"], "세대주인지",
                           {"eq": [{"var": "house_head_status"}, "세대주"]}),
                      _sale_account(p, 12, "월납입금을12회이상납입한분)", "입주자저축 1순위(가입 1년·월납입금 12회 이상)인지")]
        elif layer == "생애최초":
            conds += [cond(f"{p}-first", "household_ever_owned_home", ["세대에속한모든분이과거주택소유사실이없어야"],
                           "세대 전원이 과거에 주택을 소유한 적이 없는지",
                           {"eq": [{"var": "household_ever_owned_home"}, False]}),
                      _sale_account(p, 12, "저축액이선납금을포함하여600만원이상", "입주자저축 1순위(가입 1년·월납입금 12회 이상)인지"),
                      cond(f"{p}-deposit", "subscription_deposit", ["저축액이선납금을포함하여600만원이상"],
                           "청약 저축액(선납금 포함)이 600만원 이상인지", {"gte": [{"var": "subscription_deposit"}, 6000000]}),
                      cond(f"{p}-family", "marital_status/children_birth_dates", ["혼인(재혼포함)중이거나미혼인자녀"],
                           "혼인 중이거나 미혼 자녀(같은 등본, 입양 포함)가 있는지",
                           {"any": [{"in": [{"var": "marital_status"}, ["혼인중"]]}, {"gte": [MINORS, 1]},
                                    {"in": [{"var": "marital_status"}, ["미혼", "예비신혼", "한부모"]],
                                     "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                                        "detail": "성년이어도 미혼 자녀가 같은 등본에 있으면 신청할 수 있습니다. 이 화면은 "
                                                                  "미성년 자녀만 묻습니다."}}]}),
                      cond(f"{p}-tax", "income_tax_5y", ["5년이상소득세"],
                           "신청자 본인이 5년 이상 소득세(근로·사업소득)를 냈고 현재 근로자·자영업자이거나 과거 1년 안에 냈는지",
                           {"eq": [{"var": "income_tax_5y"}, True]})]
        elif layer == "신혼부부":
            conds.append(cond(f"{p}-type", "marital_status/marriage_date/children_birth_dates", ["혼인기간이7년이내"],
                              "혼인 7년 이내이거나 6세 이하 자녀를 둔 신혼부부, 예비신혼부부, 또는 6세 이하 자녀를 둔 한부모가족인지",
                              {"any": [{"all": [{"in": [{"var": "marital_status"}, ["혼인중"]]}, NH_DURATION]},
                                       {"in": [{"var": "marital_status"}, ["예비신혼"]]},
                                       {"all": [{"in": [{"var": "marital_status"}, ["한부모"]]}, NH_CHILD6]}]}))
        else:
            conds.append(cond(f"{p}-account", "has_subscription_account", ["무주택세대구성원으로입주자저축"],
                              "입주자저축(청약통장)에 가입했는지", {"eq": [{"var": "has_subscription_account"}, True]}))
        table = f"select_terms_{i}"
        tables[table] = _select_terms(layer)
        iq = dual_quote if layer == "신혼부부" else tables[table]["source"]["quote"][0]
        conds += [cond(f"{p}-income", "monthly_income", [iq],
                       f"세대 월평균소득이 2023년 도시근로자 가구원수별 월평균소득의 {tables[table]['label'].split(': ')[1]} 이하인지",
                       {"lte": [{"var": "monthly_income"},
                                {"lookup": ["income_standard_select_rental", {"var": "household_size"}, {"term": "ratio"}]}]},
                       table=table),
                  cond(f"{p}-assets", "total_assets", [asset_quote], "세대 총자산이 3억7,900만원 이하인지(자동차 포함)",
                       {"lte": [{"var": "total_assets"}, 379000000]})]
        layers[layer] = {"conditions": conds}
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



# ------------------------------------------------------------------------------------------------
# 통합공공임대 일자리연계형 지원주택 (2026-11-09 — 전주동서학 2026.09.14. p.9~12, 담양삼만 2026.10.29. p.9~11)
# ------------------------------------------------------------------------------------------------
# 일반형과 같은 신분(청년·신혼부부·한부모)·소득(기준중위소득 150%, 1인 170·2인 160, 출산 가산, 신혼 맞벌이 +30%p)·자산(34,500만·4,542만)
# 기준에 **직업기준**이 더해진다. 직업기준은 공고마다 다르다 — 'regional'(지역전략산업 종사자: 지자체·기관이 심사해 인정, 전주) /
# 'earner'(사업·근로소득자, 담양). 장기종사자(중소기업 근속 등)와 주거약자용 주택은 미지원 계층. 고령자·일반 계층은 없다.
JOB_LAYERS = ["청년", "신혼부부", "한부모"]
JOB_KIND_NOTE = {"regional": "이 공고의 직업기준(지자체·기관이 인정하는 지역전략산업 종사자)을 충족하는지 — 심사는 지자체·기관이 한다",
                 "earner": "근로소득 또는 사업소득이 있는 사람인지(직업기준 '사업·근로소득자')"}
JOB_KIND_FIELD = {"regional": "job_criterion_met", "earner": "has_earned_income"}


# 일자리연계형 공고는 신분·소득·자산을 표로 적는다 — 일반형 인용문을 이 표현으로(전주·담양 같은 문구)
JOB_QUOTES = {
    "무주택자로서다음의요건을모두갖춘사람": "❶청년19세이상39세이하이면서혼인중이아닌사람",
    "18세이상39세이하일것": "❶청년19세이상39세이하이면서혼인중이아닌사람",
    "혼인중이아닐것": "❶청년19세이상39세이하이면서혼인중이아닌사람",
    "기준중위소득의150퍼센트(1~2인가구및출산가구의경우에는우대비율을가산)이하일것": "신분기준중청년의소득금액은신청자본인에한하여검증",
    "총자산345,000,000원및자동차45,420,000원이하": "총자산가액345,000,000원이하379,000,000원이하413,000,000원이하",
    "예비신혼부부(혼인을계획중이며해당주택의입주전까지혼인사실을증명할수있는사람)":
        "예비신혼부부혼인을계획중이며해당주택의입주전까지혼인사실을증명할수있는사람",
    "무주택세대구성원(예비신혼부부의경우혼인으로구성될세대의세대구성원모두무주택자인경우)일것":
        "성년자인무주택세대구성원(청년은입주자본인,예비신혼부부는혼인으로구성될세대원)",
    "기준중위소득의150퍼센트(맞벌이,2인가구및출산가구의경우에는우대비율을가산)이하일것": "기준중위소득대비아래의기준비율이하",
    "신혼부부맞벌이우대비율:30%p가산": "모두가소득(사업소득또는근로소득)이있는경우에는상기비율에30%p를추가우대",
    "를둔한부모가족(자녀가신청자와동일한세대별주민등록표에등재된경우에한함)": "한부모가족(모자가족또는부자가족)으로서6세이하의자녀가있는사람",
    "무주택세대구성원으로서해당세대의월평균소득이기준중위소득의150퍼센트": "기준중위소득대비아래의기준비율이하",
    "신혼부부,한부모가족을제외한모든계층×1인0인170%": "3인이상(+0%p)150%160%170%",
    "○2인0인190%": "모두가소득(사업소득또는근로소득)이있는경우에는상기비율에30%p를추가우대",
    "청년계층의소득및자산은신청자본인에한하여검증": "신분기준중청년의소득금액은신청자본인에한하여검증",
}
JOB_CAR_QUOTE = "자동차가액45,420,000원이하49,960,000원이하54,510,000원이하"


def integrated_job_rental(nid, job_kind, job_quote):
    layers, tables = integrated_rental(nid)
    layers = {k: layers[k] for k in JOB_LAYERS}
    field = JOB_KIND_FIELD[job_kind]
    for layer, ld in layers.items():
        for c in walk(ld["conditions"]):
            c["source"]["quote"] = [JOB_QUOTES.get(q, q) for q in c["source"].get("quote", [])]
            if c["id"].endswith("-car"):
                c["source"]["quote"] = [JOB_CAR_QUOTE]
            if c["id"].endswith("-age"):              # 일자리연계형 청년은 19세 이상(일반형 18세 이상과 다름 — 전주 p.11·담양 p.9)
                c["note"] = "공고일 현재 만 19세 이상 39세 이하인지"
                c["check"] = {"between": [{"var": "age"}, 19, 39]}
        prefix = ld["conditions"][0]["id"].rsplit("-", 1)[0]
        ld["conditions"].insert(0, cond(f"{prefix}-job", field, [job_quote], JOB_KIND_NOTE[job_kind],
                                        {"eq": [{"var": field}, True]}))
    for t in tables.values():
        t["source"]["quote"] = [JOB_QUOTES.get(q, q) for q in t["source"].get("quote", [])]
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


# ------------------------------------------------------------------------------------------------
# LH 공공분양 (G3 — 양주회천 A-26 p.15~28)
# ------------------------------------------------------------------------------------------------
# 판정하는 유형: 다자녀가구·노부모부양·생애최초·신혼부부·신생아 특별공급, 일반공급(전용 60㎡ 이하/초과). 기관추천·지역균형발전·
# 철거주택소유자 특별공급은 기관이 대상자를 정해 통보하므로 미지원 계층. 소득은 유형별 '신청할 수 있는' 상한 — 우선공급(낮은 비율)
# 낙첨자도 추첨공급(맞벌이 200%)에 들어가므로 추첨 기준. 전용 60㎡ 초과 일반공급은 소득·자산 기준이 없다.
SALE_RE = [215500000, 237050000, 258600000]          # 부동산(건물+토지) 215,500천원(출산 1명 237,050·2명 이상 258,600)
SALE_CAR = [45420000, 49960000, 54510000]
SALE_BASE = {"다자녀가구": 120, "노부모부양": 120, "생애최초": 130, "신혼부부": 130, "신생아": 140, "일반공급(전용 60㎡ 이하)": 100}
SALE_INCOME_Q = "의{}%(본인및배우자가모두소득이있는경우200%)이하인분"
SALE_SECTION = {"다자녀가구": "다자녀가구특별공급■신청자격", "노부모부양": "노부모부양특별공급■신청자격",
                "생애최초": "생애최초특별공급■신청자격", "신혼부부": "신혼부부특별공급■신청자격", "신생아": "신생아특별공급■신청자격",
                "일반공급(전용 60㎡ 이하)": "일반공급■신청자격", "일반공급(전용 60㎡ 초과)": "일반공급■신청자격"}
ACCOUNT_6 = "입주자저축에가입하여6개월이경과되고매월약정납입일에월납입금을6회이상납입한분"
ACCOUNT_12 = "1년이경과한자로서매월약정납입일에월납입금을12회이상납입한"
MINORS = {"fn": "children_on_or_after", "args": [{"fn": "minor_cutoff"}]}


def _sale_account(p, months, quote, note):
    return cond(f"{p}-account", "has_subscription_account/subscription_months/subscription_payment_count", [quote], note,
                {"all": [{"eq": [{"var": "has_subscription_account"}, True]},
                         {"gte": [{"var": "subscription_months"}, months]},
                         {"gte": [{"var": "subscription_payment_count"}, months]}]})


def public_sale(nid, residence=None, small=True, large=True):
    """residence: '수도권' 또는 None. small/large: 전용 60㎡ 이하/초과 주택형이 있는지(일반공급 계층)."""
    layers, tables = {}, {}
    names = ["다자녀가구", "노부모부양", "생애최초", "신혼부부", "신생아"] + \
        (["일반공급(전용 60㎡ 이하)"] if small else []) + (["일반공급(전용 60㎡ 초과)"] if large else [])
    for i, layer in enumerate(names):
        p = f"{nid}-S{i}"
        head = SALE_SECTION[layer]
        conds = [cond(f"{p}-home", "home_ownership", [head], "무주택세대구성원인지(예비신혼부부는 혼인으로 구성될 세대 전원)", HOME)]
        if residence == CAPITAL:
            conds.append(cond(f"{p}-region", "residence_area", ["에거주하면서아래조건"],
                              "공고일 현재 수도권(서울특별시·경기도·인천광역시)에 주민등록이 되어 있는지",
                              {"in": [{"var": "residence_area"}, capital_areas()]}))
        conds.append(cond(f"{p}-rewin", "rewin_restricted", ["재당첨제한기간내에있는분및그세대에속한분"],
                          "본인·세대원이 재당첨 제한 기간 중이 아닌지(부적격 당첨 후 1년 이내도 신청 불가)",
                          {"eq": [{"var": "rewin_restricted"}, False]}))
        special = not layer.startswith("일반공급")
        if special:
            conds.append(cond(f"{p}-special", "past_special_supply", ["특별공급은1회에한하여공급함"],
                              "본인·세대원이 과거에 특별공급을 받은 적이 없는지(출산 특례는 수동 확인)",
                              {"any": [{"eq": [{"var": "past_special_supply"}, False]},
                                       {"eq": [{"var": "past_special_supply"}, True],
                                        "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                                           "detail": "특별공급은 1회 한정이지만 「주택공급에 관한 규칙」 제55조의3 출산 "
                                                                     "특례에 해당하면 다시 신청할 수 있습니다. 해당 여부는 공고문 출산특례를 "
                                                                     "확인하세요."}}]}))
        if layer == "다자녀가구":
            conds += [cond(f"{p}-kids", "children_birth_dates", ["인자녀(태아나입양아포함)2명이상을둔무주택세대구성원"],
                           "19세 미만 자녀(태아·입양 포함)가 2명 이상인지", {"gte": [MINORS, 2]}),
                      _sale_account(p, 6, ACCOUNT_6, "입주자저축에 가입해 6개월이 지났고 월납입금을 6회 이상 냈는지")]
        elif layer == "노부모부양":
            conds += [cond(f"{p}-parent", "supports_elderly_parent_3y", ["을3년이상계속하여부양"],
                           "만 65세 이상 직계존속(배우자 직계존속 포함)을 같은 등본에서 3년 이상 계속 부양하는지",
                           {"eq": [{"var": "supports_elderly_parent_3y"}, True]}),
                      cond(f"{p}-head", "house_head_status", ["하고있는무주택세대구성원중세대주"], "세대주인지",
                           {"eq": [{"var": "house_head_status"}, "세대주"]}),
                      _sale_account(p, 12, ACCOUNT_12, "입주자저축 1순위(가입 1년·월납입금 12회 이상)인지")]
        elif layer == "생애최초":
            conds += [cond(f"{p}-first", "household_ever_owned_home", ["세대에속한모든분이과거주택소유사실이없는경우"],
                           "세대 전원이 과거에 주택을 소유한 적이 없는지(배우자의 혼인 전 소유·처분 포함)",
                           {"eq": [{"var": "household_ever_owned_home"}, False]}),
                      _sale_account(p, 12, ACCOUNT_12, "입주자저축 1순위(가입 1년·월납입금 12회 이상)인지"),
                      cond(f"{p}-deposit", "subscription_deposit", ["저축액이선납금을포함하여600만원이상인분"],
                           "청약 저축액(선납금 포함)이 600만원 이상인지", {"gte": [{"var": "subscription_deposit"}, 6000000]}),
                      cond(f"{p}-family", "marital_status/children_birth_dates", ["현재혼인(재혼포함)중이거나미혼인자녀"],
                           "혼인 중이거나 미혼 자녀(같은 등본, 태아 포함)가 있는지",
                           {"any": [{"in": [{"var": "marital_status"}, ["혼인중"]]}, {"gte": [MINORS, 1]},
                                    {"in": [{"var": "marital_status"}, ["미혼", "예비신혼", "한부모"]],
                                     "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                                        "detail": "성년이어도 미혼 자녀가 같은 등본에 있으면 신청할 수 있습니다. 이 화면은 "
                                                                  "미성년 자녀만 묻습니다."}}]}),
                      cond(f"{p}-tax", "income_tax_5y", ["신청자본인이5년이상소득세를납부한분"],
                           "신청자 본인이 5년 이상 소득세(근로·사업소득)를 냈고 현재 근로자·자영업자이거나 과거 1년 안에 냈는지",
                           {"eq": [{"var": "income_tax_5y"}, True]})]
        elif layer == "신혼부부":
            conds += [cond(f"{p}-type", "marital_status/marriage_date/children_birth_dates",
                           ["혼인기간이7년이내", "예비신혼부부[혼인을계획중이며", "한부모가족[6세이하"],
                           "혼인 7년 이내이거나 6세 이하 자녀를 둔 신혼부부, 예비신혼부부, 또는 6세 이하 자녀를 둔 한부모가족인지",
                           {"any": [{"all": [{"in": [{"var": "marital_status"}, ["혼인중"]]}, NH_DURATION]},
                                    {"in": [{"var": "marital_status"}, ["예비신혼"]]},
                                    {"all": [{"in": [{"var": "marital_status"}, ["한부모"]]}, NH_CHILD6]}]}),
                      _sale_account(p, 6, ACCOUNT_6, "입주자저축에 가입해 6개월이 지났고 월납입금을 6회 이상 냈는지")]
        elif layer == "신생아":
            conds += [cond(f"{p}-newborn", "children_birth_dates", ["2세미만의자녀(2세가되는날을포함)"],
                           "2세 미만 자녀(2세가 되는 날 포함, 태아·입양 포함)가 있는지",
                           {"gte": [{"fn": "children_on_or_after", "args": [{"fn": "newborn_cutoff"}]}, 1]}),
                      _sale_account(p, 6, ACCOUNT_6, "입주자저축에 가입해 6개월이 지났고 월납입금을 6회 이상 냈는지")]
        else:
            conds.append(cond(f"{p}-account", "has_subscription_account", ["무주택세대구성원으로서입주자저축에가입한분"],
                              "입주자저축(청약통장)에 가입했는지", {"eq": [{"var": "has_subscription_account"}, True]}))
        base = SALE_BASE.get(layer)
        if base:
            table = f"sale_terms_{base}"
            conds += [
                cond(f"{p}-income", "monthly_income", [SALE_INCOME_Q.format(base)],
                     f"세대 월평균소득이 전년도 도시근로자 월평균소득의 {base}%(본인·배우자 모두 소득이 있으면 200%, 출산자녀 1명 "
                     "+10%p·2명 이상 +20%p) 이하인지 — 3인 이하는 3인 기준",
                     {"lte": [{"var": "monthly_income"},
                              {"lookup": ["income_standard_sale", {"fn": "max", "args": [{"var": "household_size"}, 3]},
                                          {"term": "ratio"}]}]}, table=table),
                cond(f"{p}-realestate", "real_estate_value", ["부동산(건물+토지)215,500천원이하"],
                     "세대 부동산(건물+토지) 가액이 2억1,550만원(출산자녀 1명 2억3,705만원·2명 이상 2억5,860만원) 이하인지",
                     {"lte": [{"var": "real_estate_value"}, {"term": "re_limit"}]}, table=table),
                cond(f"{p}-car", "car_value", ["자동차45,420천원이하"],
                     "자동차가액이 4,542만원(출산자녀 1명 4,996만원·2명 이상 5,451만원) 이하인지",
                     {"lte": [CAR, {"term": "car_limit"}]}, table=table),
            ]
            if table not in tables:
                rows = []
                for dual, add in ((False, base), (True, 200)):
                    for c, child in enumerate((0, 1, "2+")):
                        rows.append(r({"child": child, "dual": dual}, [add + 10 * c, SALE_RE[c], SALE_CAR[c]]))
                tables[table] = {
                    "label": f"LH 공공분양 소득 비율({base}%, 맞벌이 200%)·부동산·자동차 한도: 출산자녀수 × 맞벌이",
                    "columns": ["child", "dual"], "inputs": {"child": {"fn": "child_bonus_count"}, "dual": {"var": "dual_income"}},
                    "outputs": ["ratio", "re_limit", "car_limit"], "rows": rows,
                    "source": {"quote": ["237,050천원이하258,600천원이하"]}}
        layers[layer] = {"conditions": conds}
    return layers, tables


# ------------------------------------------------------------------------------------------------
# SH 토지임대부 분양 (G3-3 — 마곡17단지 p.22~40)
# ------------------------------------------------------------------------------------------------
# LH 공공분양과 다른 점: 청년 특별공급(19~39세 미혼·본인 과거 주택 소유 없음·본인 소득 1인 140%·본인 총자산 2억7,600만·부모 10억3,500만),
# 자산은 총자산(세대 3억6,200만, 출산 가산), 일반공급도 주택형과 관계없이 소득 100%(맞벌이 200%)·총자산, 투기과열지구면 생애최초의
# 1순위가 가입 2년·24회 + 세대주 + 세대 전원 5년 안 당첨 없음. 사전청약 당첨자는 미지원 계층.
SH_ASSET = [362000000, 397000000, 431000000]
SH_YOUTH_ASSET = [276000000, 311000000, 345000000]
SH_BASE = {"신혼부부": 130, "생애최초": 130, "신생아": 140, "일반공급": 100}
SH_SECTION = {"청년": "청년특별공급■신청자격", "신혼부부": "신혼부부특별공급■신청자격", "생애최초": "생애최초특별공급■신청자격",
              "신생아": "신생아특별공급■신청자격", "일반공급": "일반공급■신청자격"}
SH_ACCOUNT_6 = "에가입하여6개월이경과되고"


def sh_land_sale(nid, residence=None, overheated=True):
    """residence: '수도권' 또는 None. overheated: 투기과열지구(생애최초 1순위가 2년·24회 + 세대주 + 5년 내 당첨 없음)."""
    layers, tables = {}, {}
    for i, layer in enumerate(["청년", "신혼부부", "생애최초", "신생아", "일반공급"]):
        p = f"{nid}-H{i}"
        head = SH_SECTION[layer]
        if layer == "청년":
            conds = [cond(f"{p}-home", "home_ownership/self_ever_owned_home",
                          ["로혼인중이아니며,과거주택을소유한사실이없는무주택자"],
                          "본인이 무주택이고 과거에도 주택을 소유한 적이 없는지",
                          {"all": [HOME, {"eq": [{"var": "self_ever_owned_home"}, False]}]}),
                     cond(f"{p}-age", "age", ["19세이상~39세이하"], "만 19세 이상 39세 이하인지",
                          {"between": [{"var": "age"}, 19, 39]}),
                     cond(f"{p}-marital", "marital_status", ["로혼인중이아니며"], "혼인 중이 아닌지",
                          {"in": [{"var": "marital_status"}, ["미혼", "예비신혼", "한부모"]]})]
        else:
            conds = [cond(f"{p}-home", "home_ownership", [head], "무주택세대구성원인지(예비신혼부부는 혼인으로 구성될 세대 전원)", HOME)]
        if residence == CAPITAL:
            conds.append(cond(f"{p}-region", "residence_area", ["에거주하면서아래조건"],
                              "공고일 현재 서울특별시·인천광역시·경기도에 주민등록이 되어 있는지",
                              {"in": [{"var": "residence_area"}, capital_areas()]}))
        conds.append(cond(f"{p}-rewin", "rewin_restricted", ["재당첨제한기간내에있는분"],
                          "본인·세대원이 재당첨 제한 기간 중이 아닌지(부적격 당첨 후 1년 이내도 신청 불가)",
                          {"eq": [{"var": "rewin_restricted"}, False]}))
        if layer != "일반공급":
            conds.append(cond(f"{p}-special", "past_special_supply", ["특별공급은1회에한하여공급함"],
                              "본인·세대원이 과거에 특별공급을 받은 적이 없는지(혼인·출산 특례는 수동 확인)",
                              {"any": [{"eq": [{"var": "past_special_supply"}, False]},
                                       {"eq": [{"var": "past_special_supply"}, True],
                                        "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                                           "detail": "특별공급은 1회 한정이지만 「주택공급에 관한 규칙」 제55조의3 혼인·출산 "
                                                                     "특례에 해당하면 다시 신청할 수 있습니다. 공고문 특례 설명을 확인하세요."}}]}))
        if layer in ("청년", "신혼부부", "신생아"):
            conds.append(_sale_account(p, 6, SH_ACCOUNT_6, "입주자저축에 가입해 6개월이 지났고 월납입금을 6회 이상 냈는지"))
        if layer == "신혼부부":
            conds.append(cond(f"{p}-type", "marital_status/marriage_date/children_birth_dates",
                              ["혼인기간이7년이내이거나", "예비신혼부부[혼인을계획중이고", "한부모가족[6세이하의자녀"],
                              "혼인 7년 이내이거나 6세 이하 자녀를 둔 신혼부부, 예비신혼부부, 또는 6세 이하 자녀를 둔 한부모가족인지",
                              {"any": [{"all": [{"in": [{"var": "marital_status"}, ["혼인중"]]}, NH_DURATION]},
                                       {"in": [{"var": "marital_status"}, ["예비신혼"]]},
                                       {"all": [{"in": [{"var": "marital_status"}, ["한부모"]]}, NH_CHILD6]}]}))
        elif layer == "생애최초":
            months = 24 if overheated else 12
            conds += [cond(f"{p}-first", "household_ever_owned_home", ["세대에속한모든분이과거주택소유사실이없는경우"],
                           "세대 전원이 과거에 주택을 소유한 적이 없는지(배우자의 혼인 전 소유·처분은 예외)",
                           {"eq": [{"var": "household_ever_owned_home"}, False]}),
                      _sale_account(p, months, f"매월약정납입일에월납입금을{months}회이상납입",
                                    f"입주자저축 1순위(가입 {months // 12}년·월납입금 {months}회 이상)인지"),
                      cond(f"{p}-deposit", "subscription_deposit", ["저축액이선납금을포함하여600만원이상인분"],
                           "청약 저축액(선납금 포함)이 600만원 이상인지", {"gte": [{"var": "subscription_deposit"}, 6000000]}),
                      cond(f"{p}-family", "marital_status/children_birth_dates", ["혼인(재혼포함)중이거나미혼인자녀"],
                           "혼인 중이거나 미혼 자녀(같은 등본, 태아 포함)가 있는지(1인 가구는 신청 불가)",
                           {"any": [{"in": [{"var": "marital_status"}, ["혼인중"]]}, {"gte": [MINORS, 1]},
                                    {"in": [{"var": "marital_status"}, ["미혼", "예비신혼", "한부모"]],
                                     "review_if_true": {"code": "AMBIGUOUS_SOURCE",
                                                        "detail": "성년이어도 미혼 자녀가 같은 등본에 있으면 신청할 수 있습니다. 이 화면은 "
                                                                  "미성년 자녀만 묻습니다."}}]}),
                      cond(f"{p}-tax", "income_tax_5y", ["신청자본인이5년이상소득세를납부한분"],
                           "신청자 본인이 5년 이상 소득세(근로·사업소득)를 냈고 현재 근로자·자영업자이거나 과거 1년 안에 냈는지",
                           {"eq": [{"var": "income_tax_5y"}, True]})]
            if overheated:
                conds += [cond(f"{p}-head", "house_head_status", ["2)세대주일것"], "세대주인지(투기과열지구 1순위)",
                               {"eq": [{"var": "house_head_status"}, "세대주"]}),
                          cond(f"{p}-won5", "household_won_5y", ["과거5년이내무주택세대구성원전원이다른주택의당첨자가되지아니하였을것"],
                               "세대 전원이 과거 5년 안에 다른 주택에 당첨된 적이 없는지(투기과열지구 1순위)",
                               {"eq": [{"var": "household_won_5y"}, False]})]
        elif layer == "신생아":
            conds.append(cond(f"{p}-newborn", "children_birth_dates", ["2세미만(2세가되는날을포함)의자녀"],
                              "2세 미만 자녀(2세가 되는 날 포함, 태아·입양 포함)가 있는지",
                              {"gte": [{"fn": "children_on_or_after", "args": [{"fn": "newborn_cutoff"}]}, 1]}))
        elif layer == "일반공급":
            conds.append(cond(f"{p}-account", "has_subscription_account", ["무주택세대구성원으로입주자저축"],
                              "입주자저축(청약통장)에 가입했는지", {"eq": [{"var": "has_subscription_account"}, True]}))
        if layer == "청년":
            table = "sh_youth_terms"
            conds += [cond(f"{p}-income", "monthly_income", ["신청자본인의월평균소득이"],
                           "본인 월평균소득이 전년도 도시근로자 1인 가구 월평균소득의 140%(출산자녀 1명 150%·2명 이상 160%) 이하인지",
                           {"lte": [{"var": "monthly_income"}, {"lookup": ["income_standard_youth_sale", 1, {"term": "ratio"}]}]},
                           table=table),
                      cond(f"{p}-assets", "total_assets", ["(청년계층은신청자본인276백만원이하"],
                           "본인 총자산이 2억7,600만원(출산자녀 1명 3억1,100만원·2명 이상 3억4,500만원) 이하인지",
                           {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table=table),
                      cond(f"{p}-parents", "parents_total_assets", ["부모1,035백만원이하"], "부모 총자산이 10억3,500만원 이하인지",
                           {"lte": [{"var": "parents_total_assets"}, 1035000000]})]
            tables[table] = {"label": "SH 토지임대부 청년 본인 소득 비율·본인 총자산 한도: 출산자녀수",
                             "columns": ["child"], "inputs": {"child": {"fn": "child_bonus_count"}},
                             "outputs": ["ratio", "asset_limit"],
                             "rows": [r({"child": 0}, [140, SH_YOUTH_ASSET[0]]), r({"child": 1}, [150, SH_YOUTH_ASSET[1]]),
                                      r({"child": "2+"}, [160, SH_YOUTH_ASSET[2]])],
                             "source": {"quote": ["(신청자본인)311백만원이하", "(신청자본인)345백만원이하"]}}
        else:
            base = SH_BASE[layer]
            table = f"sh_terms_{base}"
            iq = "의100%이하인분(단,본인및배우자가모두소득이있는경우에는200%)" if base == 100 else \
                f"의{base}%(단,본인및배우자가모두소득이있는경우에는200%)이하인분"
            conds += [cond(f"{p}-income", "monthly_income", [iq],
                           f"세대 월평균소득이 전년도 도시근로자 월평균소득의 {base}%(본인·배우자 모두 소득이 있으면 200%, 출산자녀 1명 "
                           "+10%p·2명 이상 +20%p) 이하인지 — 3인 이하는 3인 기준",
                           {"lte": [{"var": "monthly_income"},
                                    {"lookup": ["income_standard_sale", {"fn": "max", "args": [{"var": "household_size"}, 3]},
                                                {"term": "ratio"}]}]}, table=table),
                      cond(f"{p}-assets", "total_assets", ["합계액에서5를차감한금액이362백만원이하"],
                           "세대 총자산이 3억6,200만원(출산자녀 1명 3억9,700만원·2명 이상 4억3,100만원) 이하인지",
                           {"lte": [{"var": "total_assets"}, {"term": "asset_limit"}]}, table=table)]
            if table not in tables:
                rows = []
                for dual, add in ((False, base), (True, 200)):
                    for c, child in enumerate((0, 1, "2+")):
                        rows.append(r({"child": child, "dual": dual}, [add + 10 * c, SH_ASSET[c]]))
                tables[table] = {"label": f"SH 토지임대부 소득 비율({base}%, 맞벌이 200%)·총자산 한도: 출산자녀수 × 맞벌이",
                                 "columns": ["child", "dual"],
                                 "inputs": {"child": {"fn": "child_bonus_count"}, "dual": {"var": "dual_income"}},
                                 "outputs": ["ratio", "asset_limit"], "rows": rows,
                                 "source": {"quote": ["397백만원이하", "431백만원이하"]}}
        layers[layer] = {"conditions": conds}
    return layers, tables


SH_SALE_NOTES = [
    "우선공급·가점·지역 우선(서울 거주기간)·일반공급 순위(1순위: 가입 2년·24회, 세대주, 5년 내 당첨 없음)는 선정 순서다 — "
    "일반공급은 2순위(가입만)로도 신청할 수 있어 가입 여부만 판정한다.",
    "특별공급 1개와 일반공급 1개는 함께 신청할 수 있다(특별공급끼리는 하나만). 청년 특별공급은 본인·부모 모두 자산 확인 동의서를 낸다.",
    "토지임대부 분양주택은 토지를 빌려 쓰는 분양주택이라 토지 임대료가 따로 있다 — 공고문 공급 조건을 확인한다.",
]


SALE_NOTES = [
    "우선공급·배점·지역 우선(해당 시 거주기간)·일반공급 순위(납입 횟수·저축총액)는 선정 순서다 — 신청할 수 있는지만 판정한다.",
    "특별공급은 하나만 신청할 수 있고, 특별공급 1개와 일반공급 1개는 함께 신청할 수 있다(특별공급 당첨 시 일반공급 제외).",
    "부적격 당첨 후 1년이 지나지 않은 사람은 신청할 수 없다(재당첨 제한과 함께 묻는다).",
]


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

SH_NATIONAL_NOTES = [
    "전용 50㎡ 미만은 월평균소득 50% 이하(1인 70%·2인 60%) 세대에 먼저 공급하고 남으면 70% 이하에 공급한다 — 70% 이하면 신청 "
    "자격이 있고 50% 여부는 선정 순서라 판정하지 않는다(p.24·p.26).",
    "경쟁 시 순위(50㎡ 미만은 해당구·연접구 거주, 59㎡는 청약저축 24회·6회)와 미성년 자녀 3명 이상·배점은 선정 순서라 "
    "판정하지 않는다(p.26~28).",
    "주거약자 주택은 공급신청자 본인이 고령자(만 65세 이상)·장애인·상이 국가유공자 등일 때만 신청할 수 있다 — '일반(주거약자용)' "
    "계층으로 판정한다(p.29). 일반공급으로 신청한 주거약자는 주거약자 주택에 배정되지 않는다(p.16).",
    "과거 공공임대주택 임차권 양도·전대로 적발된 뒤 4년이 지나지 않은 세대구성원이 있으면 무효다 — 이 판정은 묻지 않는다(p.23).",
    "외국인은 신청할 수 없고, 1세대 1주택 신청 원칙(중복 신청은 모두 무효)이다(p.23).",
    "소득 기준표는 원문이 1~6인만 적는다 — 7인 이상 세대는 이 판정이 기준 금액을 모른다(표에 없음).",
]

SH_PERMANENT_NOTES = [
    "선정은 배점(서울 거주기간·연령·세대원수 등) 합산 순이고 같은 점수면 서울 전입일이 오래된 사람·연령이 높은 사람 순이다 — "
    "판정하지 않는다(p.13).",
    "다목(「일제하 일본군위안부 피해자…법률」에 따라 등록한 피해자)은 이 판정이 묻지 않는다 — 해당하면 원문을 확인한다(p.7).",
    "과거 공공임대주택 불법 양도·전대로 적발된 뒤 4년이 지나지 않은 세대구성원이 있으면 선정될 수 없다 — 이 판정은 묻지 않는다(p.7).",
    "금융정보 등 제공 동의서를 내지 않으면 신청할 수 없다(p.4). 외국인은 신청할 수 없다(p.8).",
    "LH·SH 영구임대 공고 중 1호에만 신청할 수 있고, 거주지 동 주민센터 현장 접수만 받는다(p.3).",
]

ELDERLY_NOTES = [
    "순위(1순위 생계·의료급여, 2순위 국가유공자 등, 3순위 일반)는 신청 자격의 갈래로 판정하고, 같은 순위 안의 배점·추첨은 판정하지 않는다(p.6).",
    "과거 공공임대주택 불법 양도·전대로 적발된 뒤 4년이 지나지 않은 세대구성원이 있으면 선정될 수 없다 — 이 판정은 묻지 않는다(p.5).",
    "금융정보 등 제공 동의서를 내지 않으면 신청할 수 없다(p.1). 외국인은 신청할 수 없다(p.6).",
    "생계·의료급여 수급자 등은 '가군' 임대조건이 따로 적용된다(p.3) — 임대료는 판정하지 않는다.",
]

SHARE_NOTES = [
    "2024.01.03. 사전청약 공고 — 2024.3. 규칙 개정(신생아 특별공급, 신혼부부 맞벌이 200%, 출생자녀 가산) 전 기준이다. "
    "같은 사업의 지금 공고는 금액·비율이 달라 자동 판정하지 않는다(새 기준표·규칙 확인 필요).",
    "우선공급·잔여공급(청년·신혼부부 가점, 생애최초 소득 100% 우선, 일반공급 1순위 우선)과 지역 우선(거주기간)은 선정 순서다 — "
    "판정하지 않는다. 일반공급은 잔여공급(가입자)으로도 신청할 수 있어 가입 여부만 본다(p.13).",
    "나눔형은 거주의무 5년이고, 5년 뒤 공사에 환매하면 처분손익의 70%를 받는다(p.3) — 판정하지 않는다.",
    "사전청약 당첨자는 본청약 공고일까지 자격(무주택·거주기간)을 유지해야 한다(p.1) — 이 판정은 사전청약 공고일 기준이다.",
]

SELECT_NOTES = [
    "2024.01.04. 사전청약 공고 — 2024.3. 규칙 개정(신생아 특별공급, 다자녀 2명, 맞벌이 완화, 출생자녀 가산) 전 기준이다. 같은 사업의 "
    "지금 공고는 금액·비율이 달라 자동 판정하지 않는다.",
    "선택형 공공임대는 6년 임대 뒤 분양 전환을 선택할 수 있는 분양전환공공임대다(p.4) — 임대조건·분양전환 가격은 판정하지 않는다.",
    "우선공급(70%)의 더 낮은 소득 비율(생애최초 100%, 신혼부부 100·120% 등)과 가점·지역 우선은 선정 순서다 — 잔여공급 기준(실효 자격)으로 "
    "판정한다(p.9~17).",
    "기관추천 특별공급(국가유공자·장애인·철거민 등)은 기관이 정한 대상이라 판정하지 않는다(미지원 계층).",
    "사전청약 당첨자는 본청약 공고일까지 자격(무주택·거주기간)을 유지해야 한다(p.1) — 이 판정은 사전청약 공고일 기준이다.",
]

SHARE_2026_NOTES = [
    "2024.3. 규칙 개정 뒤 본청약 공고 — 신생아 특별공급, 맞벌이 200%, '23.3.28. 이후 출생 자녀 1명 +10%p·2명 이상 +20%p 소득·자산 완화(p.19~21).",
    "유형마다 우선·일반·추첨 공급 단계의 소득 비율이 다르다(예: 신혼부부 우선 130%·추첨 130%/맞벌이 200%) — 가장 넓은 단계(추첨공급)가 신청 "
    "자격이고, 낮은 비율 단계는 선정 순서라 판정하지 않는다(p.20).",
    "일반공급은 1순위(가입 1년·12회)·2순위(가입) 모두 신청할 수 있어 가입 여부만 판정한다. 지역 우선(고양시 1년·경기도 6개월)·배점은 선정 순서다.",
    "이익공유형(나눔형)은 거주의무 5년이고, 처분하려면 LH에 환매해 처분손익의 70%를 받는다(p.1) — 판정하지 않는다.",
]

SELECT_2026_NOTES = [
    "2024.3. 규칙 개정 뒤 6년 분양전환 공공임대(선택형) 최초 모집 — 6년 임대 뒤 분양 전환을 선택한다(분양전환가격은 입주 시·분양 시 감정가 산술평균, "
    "p.3) — 임대조건·분양전환은 판정하지 않는다.",
    "소득은 가구원수별 2025년도 표(3인 이하를 3인으로 보지 않음)에 유형별 가장 넓은 단계(추첨공급) 비율로 판정한다 — 우선공급 등 낮은 비율 "
    "단계와 배점·지역 우선(군포시 1년)은 선정 순서다(p.10~11·p.14~25).",
    "원문 출산가구 소득 완화 표에 220%(맞벌이 + '23.3.28. 이후 출생 자녀 2명 이상) 금액이 없어 그 경우는 확인 필요로 둔다(p.11).",
    "일반공급은 1순위(가입 1년·12회)·2순위(가입) 모두 신청할 수 있어 가입 여부만 판정한다. 노부모부양 특별공급은 세대주만(p.17).",
    "입주 후 분양 전환 때까지 무주택세대구성원을 유지해야 하고, 분양전환 공공임대라 재당첨 제한 5년이 적용된다(p.2).",
]

# ------------------------------------------------------------------------------------------------
# SH 행복주택(2026년 1차 2026.5.28. 기준) — 계층 자격·결정표는 LH 행복주택 템플릿(N3)·C3 고령자/주거급여수급자와 같고
# (금액도 2025년도 기준으로 같다), 인용문만 SH 문구다. 서울·연접지역 1·2·3순위와 우선공급(자치구)은 선정 순서라 자격이 아니다.
# 소득표는 SH 표(income_standard_sh_happy — 5인까지, 6인 이상은 비율별 1인당 가산)로 조회한다. 금액 문구는 리터럴이라
# 기준 연도가 다른 공고에서는 인용문을 찾지 못해 초안이 보류된다.
# ------------------------------------------------------------------------------------------------
SH_HAPPY_QUOTES = {
    "R4": ["혼인 중이 아닐 것"],
    "R5": ["무주택자로서 아래의 요건", "세대 내 다른 구성원이 주택을 소유해도 신청 가능"],
    "R5c": ["대학에 재학중이거나 다음 학기에 입학 또는 복학 예정일 것", "대학 또는 고등학교를 졸업 또는 중퇴한 지 2년 이내일 것"],
    "R6": ["신청자 본인 및 부모의 월평균소득 합계가 전년도 도시근로자 가구원수별 가구당 월평균소득의 100퍼센트 이하일 것"],
    "R7": ["신청자 본인의 총 자산가액 합산기준이 10,800만원 이하"],
    "R8": ["자동차가액 산출대상 자동차를 소유하고 있지 않을 것"],
    "R5b": ["만 19세 이상 만 39세 이하인 자"],
    "R7/R7b": ["해당 세대의 월평균소득(신청자가 세대원인 경우 신청자의 월평균소득)이 전년도 도시근로자 가구원수별 가구당 월평균소득의"],
    "R8y": ["해당 세대가 보유하고 있는 총 자산가액 합산기준 25,100만 원 이하"],
    "R9": ["25,100만 원 이하이고 자동차가액이 4,542만 원 이하일 것"],
    "R10": ["본인 입주 전까지 주택청약종합저축(청약저축 포함) 가입사실을 증명할 수 있을 것"],
    "M-marital": ["(신혼부부) 혼인 중인 자", "(예비신혼부부) 혼인을 계획 중이며 해당 주택의 입주 전까지 혼인사실을 증명할 수 있는 자"],
    "M-home": ["무주택세대구성원(예비신혼부부의 경우 혼인으로 구성될 세대구성원 모두 무주택자)"],
    "M-income": ["해당세대(예비신혼부부의 경우 혼인으로 구성될 세대)의 월평균소득이 전년도 도시근로자 가구원수별 가구당 월평균소득의 "
                 "100퍼센트 이하일 것 (맞벌이 신혼부부의 경우 120퍼센트 이하)"],
    "M-assets": ["혼인으로 구성될 세대)가 보유하고 있는 총 자산가액 합산기준 34,500만원 이하"],
    "M-car": ["34,500만원 이하이고 자동차가액이 4,542만원 이하일 것"],
    "M-sub": ["본인 또는 배우자(예비신혼부부의 경우는 혼인 예정인 배우자) 중 1인이 입주 전까지 주택청약종합저축(청약저축 포함) "
              "가입사실을 증명할 수 있을 것"],
    "M-duration": ["해당 주택 공급신청자의 전체 혼인 합산 기간이 7년(2,555일) 이내이거나 만 6세 이하의 자녀(태아 포함)를 둔 자"],
    "S-marital": ["(한부모가족) 태아를 포함해 만 6세 이하의 자녀(태아 포함)를 둔 한부모인 자"],
    "S-sub": ["입주 전까지 주택청약종합저축(청약저축 포함) 가입사실을 증명할 수 있을 것 (단, 한부모가족의 경우 본인만 해당)"],
}
SH_HAPPY_SHARED = {"S-home": "M-home", "S-income": "M-income", "S-assets": "M-assets", "S-car": "M-car", "S-child6": "S-marital"}
SH_HAPPY_ELDERLY = dict(home_quote="무주택세대구성원으로서 아래의 요건을 모두 갖춘 만 65세 이상인 자",
                        income_quote="해당 세대의 월평균소득이 전년도 도시근로자 가구원수별 가구당 월평균소득의 100퍼센트 이하일 것",
                        asset_quote="해당 세대가 보유하고 있는 총 자산가액 합산기준 34,500만원 이하",
                        car_quote="34,500만원 이하이고 자동차가액이 4,542만원 이하일 것")
SH_HAPPY_BENEFIT = dict(home_quote="현재 무주택세대구성원인 주거급여수급자",
                        benefit_quote="「주거급여법」 제2조제2호 및 제3호에 따른 주거급여수급자 자격이 있을 것")
SPOUSE_MAN = ["34,500만원 이하", "37,900만원 이하", "41,300만원 이하", "4,542만원 이하", "4,996만원 이하", "5,451만원 이하"]
SH_HAPPY_TABLE_QUOTES = {
    "student_terms": ["10,800만원 이하", "11,900만원 이하", "13,000만원 이하"],
    "youth_income_terms": ["(청년계층은 세대원인 경우 본인만 해당)", "1인 가구 (+20%p)", "2인 가구 (+10%p)"],
    "youth_asset_car_terms": ["25,100만원 이하", "27,600만원 이하", "30,100만원 이하", "4,542만원 이하", "4,996만원 이하",
                              "5,451만원 이하"],
    "spouse_terms_married": SPOUSE_MAN, "spouse_terms_singleparent": SPOUSE_MAN, "elderly_terms": SPOUSE_MAN,
}
MARRIAGE_EDGE = ("혼인 기간 '7년(2,555일) 이내'의 경계입니다 — 공고일 7년 전 날부터 며칠은 날짜 셈법(첫날 포함 여부·윤년)에 따라 "
                 "7년 안팎이 갈립니다. 혼인신고일을 SH에 확인해 주세요.")
SH_INCOME_REF = ('"income_standard"', '"income_standard_sh_happy"')


def _sh_happy_duration(ann, child):
    """혼인 7년(2,555일): 공고일−7년(당일 포함)보다 앞이면 불가, 공고일−2,554일(첫날 포함 셈으로도 2,555일 이내) 이후면 가능,
    그 사이 며칠은 확인 필요. 6세 이하 자녀는 원문 리터럴 기준일 이후 출생."""
    a = date.fromisoformat(ann)
    loose, strict = years_before(a, 7), a - timedelta(days=2554)
    return {"any": [{"eq": [{"var": "marital_status"}, "예비신혼"]},
                    {"gte": [{"var": "marriage_date"}, {"date": strict.isoformat()}]},
                    {"gte": [{"var": "marriage_date"}, {"date": loose.isoformat()}],
                     "review_if_true": {"code": "AMBIGUOUS_SOURCE", "detail": MARRIAGE_EDGE}},
                    {"if": [{"is": [{"var": "has_children"}, False]}, False,
                            {"gte": [{"var": "youngest_child_birth_date"}, {"date": child}]}]}]}


def _sh_income(check):
    return json.loads(json.dumps(check, ensure_ascii=False).replace(*SH_INCOME_REF))


def sh_happy_housing(nid, ann, layers, extra_layers, child):
    """layers: N3 계층 중 이 공고에 있는 것(대학생·청년·신혼부부·한부모), extra_layers: 고령자·주거급여수급자 중 있는 것,
    child: 한부모·신혼부부 6세 이하 자녀 출생 기준일 리터럴(원문 '2019. 5. 29. 이후 출생')."""
    tpl = json.loads((ROOT / "rules" / "notices" / "N3.json").read_text(encoding="utf-8"))
    y, m, d = (int(x) for x in child.split("-"))
    child_quote = f"{y}. {m}. {d}. 이후 출생"
    out, tables, used = {}, {}, set()
    for layer in layers:
        conds = []
        for c in copy.deepcopy(tpl["layers"][layer]["conditions"]):
            suffix = c["id"].split("-", 1)[1]
            c["id"] = f"{nid}-{suffix}"
            # N3의 청년 R6(미혼)·R8(자산)은 대학생 R6(소득)·R8(자동차)과 접미사가 같다
            key = {"R6": "R4", "R8": "R8y"}.get(suffix) if layer == "청년" and suffix in ("R6", "R8") else                 SH_HAPPY_SHARED.get(suffix, suffix)
            quotes = list(SH_HAPPY_QUOTES[key]) + ([child_quote] if suffix in ("S-marital", "S-child6") else [])
            c["source"] = {"clause": c["source"]["clause"].split(",")[0].split("(")[0].strip() or c["source"]["clause"],
                           "quote": quotes}
            c["check"] = json.loads(json.dumps(_sh_income(c["check"]), ensure_ascii=False)
                                    .replace('{"fn": "young_child_cutoff"}', json.dumps({"date": child})))
            if suffix == "M-duration":
                c["check"] = _sh_happy_duration(ann, child)
                c["note"] = ("혼인기간 7년(2,555일) 이내이거나 6세 이하 자녀(태아포함)를 두었는지 (예비신혼부부는 이 요건이 적용되지 않음, "
                             "7년 경계 며칠은 확인 필요)")
            if suffix == "M-income":
                c["source"]["derivation"] = ("예비신혼부부의 가구원수는 신청자 본인과 예비배우자, 공고일 기준 동일 세대에 등재된 직계존속·비속을 "
                                             "포함해 산정한다(정부 지침 — 공고문은 '혼인으로 구성될 세대'만 명시). 따라서 신혼부부·예비신혼부부 "
                                             "모두 가구원수 1은 모순이다.")
            if "table" in c:
                used.add(c["table"])
            conds.append(c)
        out[layer] = {"conditions": conds}
    for name in sorted(used):
        t = copy.deepcopy(tpl["tables"][name])
        t["label"] = t["label"].split(" (")[0] if name == "student_terms" else t["label"]
        t["source"] = {"quote": list(SH_HAPPY_TABLE_QUOTES[name])}
        tables[name] = t
    for layer in extra_layers:
        if layer == "고령자":
            conds = C3.elderly(nid, **SH_HAPPY_ELDERLY)
            spec = C3.TABLE_SPECS["elderly_terms"]
            t = C3.table(spec["label"], spec["columns"], spec["rows"], None, quotes=SH_HAPPY_TABLE_QUOTES["elderly_terms"])
            t["source"].pop("page")
            tables["elderly_terms"] = t
        else:
            conds = C3.housing_benefit(nid, **SH_HAPPY_BENEFIT)
        for c in conds:
            c["check"] = _sh_income(c["check"])
        out[layer] = {"conditions": conds}
    return out, tables


SH_HAPPY_NOTES = [
    "일반공급 1·2·3순위(서울·연접지역 → 그 밖의 수도권 → 그 밖)와 우선공급(해당 자치구 → 서울)은 경쟁 시 선정 순서라 자격이 아니다 — "
    "다른 지역 거주자도 신청할 수 있다(p.24~32). 우선공급은 2세 미만 자녀가 있는 사람부터 순위·배점으로 뽑고, 배점은 판정하지 않는다.",
    "대학생·청년 계층의 무주택은 본인만 본다(세대 내 다른 구성원이 주택을 소유해도 신청 가능, p.25·27). 신혼부부·한부모·고령자·"
    "주거급여수급자는 무주택세대구성원이어야 한다.",
    "청년 계층의 소득·자산은 신청자가 세대주이면 세대 전체, 세대원이거나 단독세대주이면 본인만 본다(p.22·28).",
    "혼인 기간 '7년(2,555일) 이내'는 공고일 7년 전 날부터 며칠이 날짜 셈법에 따라 갈려 그 며칠은 확인 필요로 둔다(p.28).",
    "소득기준표는 5인까지 싣고 6인 이상은 비율별 1인당 금액(100% 579,278원 … 140% 810,989원)을 더한다(p.21).",
    "1세대 1주택만 신청할 수 있고 중복 신청은 모두 무효다. 이번 공고의 예비자가 되면 기존 행복주택 예비자 자격을 잃는다(p.23).",
]

MULTICHILD_NOTES = [
    "1순위(신생아가구 — '24.5.30. 이후 출생 자녀·태아)와 2순위는 같은 자격(수급자·차상위·지원대상 한부모)의 선정 순서라 한 갈래로 판정하고, "
    "배점(미성년 자녀 수·서울 거주기간·청약 회차 등)은 판정하지 않는다(p.6~7).",
    "서울 거주 요건은 없다 — 타지역 거주자도 신청할 수 있다(p.3).",
    "조손가정은 미성년 손자녀 2명 이상이 신청자와 같은 등본에 있어야 한다(p.3) — 이 화면의 '자녀'로 입력한다.",
    "과거 공공임대 불법 양도·전대로 적발된 뒤 4년이 지나지 않은 세대구성원이 있으면 선정될 수 없고, 외국인은 신청할 수 없다(p.9) — 묻지 않는다.",
    "1세대 1주택 신청 원칙 — 중복 신청은 모두 무효(p.9).",
]

JOB_NOTES = [
    "일자리연계형 지원주택은 직업기준과 신분기준(청년·신혼부부·한부모·장기종사자)을 모두 충족해야 한다 — 직업기준은 공고마다 다르다.",
    "장기종사자(미성년 자녀 포함 3인 이상 세대 + 중소기업·동일기업 근속, 동일사업 영위)와 주거약자용 주택은 판정하지 않는다(미지원 계층).",
    "청년은 19세 이상 39세 이하(일반형 통합공공임대의 18세와 다르다). 청년의 소득·자산은 본인만(세대원이 있는 세대주 청년은 세대 전체).",
    "소득은 기준중위소득 150%(1인 170·2인 160%, 출산자녀 1명 +10%p·2명 이상 +20%p, (예비)신혼부부 맞벌이 +30%p), 자산은 총자산 "
    "34,500만·자동차 4,542만(출산자녀 가산)이다 — 일반형과 같다.",
]

PLAN = [
    dict(nid="N30", key="LH30", title="남양주마석2단지 국민임대주택 예비입주자", ann="2026-09-07",
         program="국민임대주택", template="national_rental", params={"elderly_quote": None, "money": "million"},
         notes=NATIONAL_NOTES + ["입주자모집공고일 현재 2세 미만 자녀(태아 포함)가 있으면 모집호수의 30% 범위에서 우선 배정한다(p.3)."]),
    dict(nid="N31", key="LH31", title="김포시지역 국민임대주택 예비입주자(정정)", ann="2026-09-07",
         program="국민임대주택", template="national_rental", params={"elderly_quote": None, "money": "million"},
         notes=NATIONAL_NOTES),
    # G2 처음 보는 공고 검증 — 초안은 등록 전에 docs/draft-checks/X-national-bucheon.g2.draft.json에 얼림
    dict(nid="N32", key="LH32", title="부천시지역 국민임대주택 예비입주자", ann="2026-09-07",
         program="국민임대주택", template="national_rental",
         params={"elderly_quote": "범박1단지46형고령자임대주택은(공고일현재65세이상만신청)가능", "money": "million"},
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
    # G3 LH 공공분양 — 개발용
    dict(nid="N49", key="LH49", title="양주회천 A-26블록 공공분양주택(정정)", ann="2026-08-27",
         program="공공분양주택", template="public_sale", params={"residence": CAPITAL, "small": True, "large": True},
         unsupported=[{"name": "기관추천·국가유공자 특별공급", "page": 18,
                       "note": "기관(지자체·보훈청 등)이 대상자로 선정해 LH에 통보한 사람만 신청 — 해당 기관에 문의."},
                      {"name": "지역균형발전 특별공급", "page": 19, "note": "시·도지사가 대상자로 선정·통보한 사람만 신청."},
                      {"name": "철거주택소유자 특별공급", "page": 19, "note": "이 사업지구 철거주택소유자로 인정·통보받은 사람만 신청."}],
         notes=SALE_NOTES + ["전용 59㎡ 394세대·74㎡ 168세대·84㎡ 230세대 — 전용 60㎡ 이하 일반공급만 소득·자산 기준이 있다(p.1·p.26)."]),
    # G3-3 SH 토지임대부 분양 — 개발용
    dict(nid="N51", key="SH51", title="SH 마곡지구 17단지 토지임대부 분양주택(정정)", ann="2026-02-27",
         program="토지임대부 분양주택", template="sh_land_sale", params={"residence": CAPITAL, "overheated": True},
         unsupported=[{"name": "사전청약당첨자", "page": 1,
                       "note": "사전청약 당첨자의 본청약 — 3.10.~3.11. 따로 신청한다(사전청약 당시 자격 기준)."}],
         notes=SH_SALE_NOTES + ["마곡지구는 투기과열지구다 — 생애최초 특별공급도 일반공급 1순위 요건(가입 2년·24회, 세대주, 5년 내 당첨 없음)을 "
                                "갖춰야 한다(p.5·p.33)."]),
    # G3-3 처음 보는 공고 — 판정 틀을 만든 뒤 등록 전에 초안을 얼림(docs/draft-checks/Y-sh-sale-godeok3.g3.draft.json).
    # 결과를 본 뒤 인용문을 두 공고 공통 표현으로 보강(괄호 안 출생일·혼인일 범위 — 독립 검증 아님)
    dict(nid="N52", key="SH52", title="SH 고덕강일지구 3단지 토지임대부 분양주택", ann="2026-10-16",
         program="토지임대부 분양주택", template="sh_land_sale", params={"residence": CAPITAL, "overheated": True},
         unsupported=[{"name": "사전청약당첨자", "page": 1,
                       "note": "사전청약 당첨자의 본청약 — 10.26.~10.27. 따로 신청한다(사전청약 당시 자격 기준)."}],
         notes=SH_SALE_NOTES + ["고덕강일지구는 투기과열지구다 — 생애최초 특별공급도 일반공급 1순위 요건(가입 2년·24회, 세대주, 5년 내 당첨 "
                                "없음)을 갖춰야 한다(p.47·p.99)."]),
    # G3 LH 공공분양 처음 보는 공고 — 판정 틀을 만든 뒤 등록 전에 초안을 얼림(docs/draft-checks/Y-sale-ansan-b1.g3.draft.json)
    dict(nid="N50", key="LH50", title="안산신길2 B-1블록 공공분양주택", ann="2026-10-30",
         program="공공분양주택", template="public_sale", params={"residence": CAPITAL, "small": False, "large": True},
         unsupported=[{"name": "사전청약당첨자", "page": 2,
                       "note": "사전청약 당첨자(입주예약자)의 본청약 — 주택형 선호 순위 선택(11.9~11.10)으로 따로 신청한다."},
                      {"name": "기관추천·국가유공자 특별공급", "page": 26,
                       "note": "기관이 대상자로 선정해 LH에 통보한 사람만 신청 — 해당 기관에 문의."},
                      {"name": "지역균형발전 특별공급", "page": 27, "note": "시·도지사가 대상자로 선정·통보한 사람만 신청."}],
         notes=SALE_NOTES + ["전용 74㎡ 80세대·84㎡ 307세대 — 전용 60㎡ 이하가 없어 일반공급은 소득·자산 기준이 없다(p.1)."]),
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
    # G5 — SH 국민임대(서울 거주 + LH 국민임대와 같은 법령 기준, 일반공급 일반·주거약자). SH 국민임대 공고는 1건뿐이라
    # 처음 보는 공고 검증은 다음 공고가 오면(공개는 2026-11-02 사용자 결정 — 안전장치로 보류)
    dict(nid="N53", key="SH53", title="SH 2026년 국민임대주택 입주자모집", ann="2026-08-20",
         program="국민임대주택", template="sh_national_rental",
         params={"eligibility_quote": "현재서울특별시에거주하는성년자인무주택세대구성원으로서",
                 "adult_quote": "민법상미성년자(만19세미만)는공급신청할수없습니다",
                 "income_quote": "해당세대의월평균소득이전년도도시근로자가구원수별가구당월평균소득의70퍼센트이하인사람",
                 "near_quote": "상계장암지구1,2단지는서울특별시외의정부시,남양주시,양주시,포천시에거주하는사람도신청가능",
                 "weak_quote": "①~⑦중한개이상의자격을갖춘사람(공급신청자본인)만신청가능", "edition": "2026"},
         notes=SH_NATIONAL_NOTES),
    # G5 — SH 영구임대(서울 거주, 별표3 1순위 가~자). 공고 1건(2025.11.13.)으로 만든 틀
    dict(nid="N54", key="SH54", title="SH 2025년 영구임대주택 예비입주자 모집", ann="2025-11-13",
         program="영구임대주택", template="sh_permanent_rental",
         params={"eligibility_quote": "현재서울특별시에거주하는성년자인무주택세대구성원으로,영구임대주택입주자자격에해당되며",
                 "adult_quote": "「민법」상미성년자(만19세미만)는공급신청할수없습니다",
                 "income_quote": "월평균소득의70퍼센트이하(가구원수1명-90%,가구원수2명-80%)이고",
                 "asset_quote": "(23,700)만원이하", "car_quote": "개별자동차가액(4,563)만원이하"},
         notes=SH_PERMANENT_NOTES),
    # G5 — LH 고령자복지주택(영구임대형). 공고 1건(평택고덕 A-58, 정정)으로 만든 틀
    dict(nid="N55", key="LH55", title="평택고덕 A-58블록 고령자복지주택(영구임대) 예비입주자(정정)", ann="2026-08-20",
         program="고령자복지주택", template="elderly_welfare",
         params={"eligibility_quote": "현재만65세이상(1961.08.20.이전출생자)으로서무주택세대구성원요건을만족하고",
                 "merit_quote": "월평균소득70%(1인90%,2인80%)이하인", "general_quote": "50%(1인70%,2인60%)이하인자",
                 "kind": "영구임대", "asset_quote": "가액합산기준24,500만원이하", "car_quote": "개별자동차가액4,542만원이하"},
         notes=ELDERLY_NOTES),
    # G6 — LH 나눔형 공공분양(뉴홈 4차 사전청약, 2024.01.03.). 공고 1건(2024.3. 개정 전 기준)으로 만든 틀
    dict(nid="N56", key="LH56", title="뉴홈 4차 사전청약 나눔형(이익공유형) 공공분양주택", ann="2024-01-03",
         program="공공분양(나눔형)", template="lh_share_sale",
         params={"residence": CAPITAL, "youth_income_quote": "청년도시근로자가구원수별가구당월평균소득액의140%4,695,438원",
                 "asset_quote": "379,000천원이하", "youth_asset_quote": "289백만원이하", "parents_quote": "(부모)1,083백만원이하",
                 "dual_quote": "맞벌이도시근로자가구당월평균소득액의140%9,113,233원", "edition": "2024"},
         notes=SHARE_NOTES),
    # G7 — LH 선택형 공공임대(뉴홈 4차 사전청약, 2024.01.04.). 공고 1건(2024.3. 개정 전 기준)으로 만든 틀
    dict(nid="N57", key="LH57", title="뉴홈 4차 사전청약 선택형 공공임대주택", ann="2024-01-04",
         program="공공분양(선택형)", template="lh_select_rental",
         params={"residence": CAPITAL, "youth_income_quote": "청년특별공급도시근로자가구원수별가구당월평균소득액의140%4,695,438",
                 "asset_quote": "379,000천원이하", "youth_asset_quote": "289,000천원이하", "parents_quote": "1,083,000천원",
                 "dual_quote": "맞벌이도시근로자가구원수별가구당월평균소득액의140%9,405,477원", "edition": "2024"},
         unsupported=[{"name": "기관추천 특별공급(국가유공자 포함)", "page": 11,
                       "note": "기관이 추천한 대상(국가유공자·장애인·철거민 등)만 신청할 수 있다 — 판정하지 않는다."}],
         notes=SELECT_NOTES),
    # 처음 보는 실공고 검증(2026-11-08) — 초안은 등록 전에 docs/draft-checks/Z-lh-national-inje.draft.json에 얼림.
    # 자산·자동차 한도가 원 단위 한 표(p.5)라 money="won"(금액은 표준과 같음)
    dict(nid="N58", key="LH58", title="인제서화(고령자) 국민임대주택 입주자", ann="2026-06-08",
         program="국민임대주택", template="national_rental", params={"elderly_quote": None, "money": "won"},
         notes=NATIONAL_NOTES + [
             "전용 50㎡ 미만(44B형)은 월평균소득 50% 이하(1인 70%·2인 60%) 세대가 먼저이고, 50% 초과 70% 이하(1인 90%·2인 80%)도 "
             "신청할 수 있다(p.5) — 70% 기준(가산 포함)으로 판정한다.",
             "단지 이름의 '고령자'는 나이 요건이 아니다 — 65세 이상 고령자는 우선공급 대상 중 하나다(p.12)."]),
    # 처음 보는 실공고 검증(2026-11-08) — 초안은 등록 전에 docs/draft-checks/Z-lh-integrated-busan-mora.draft.json에 얼림
    dict(nid="N59", key="LH59", title="부산모라1블록 통합공공임대주택 입주자(최초 모집)", ann="2026-10-15",
         program="통합공공임대주택", template="integrated_rental", params={},
         unsupported=[{"name": "주거약자용주택(31AS형)", "page": 2,
                       "note": "편의시설을 설치한 주거약자용 주택(3층 이하)은 별도 신청 구분이다 — 판정하지 않는다. 신청자가 원하면 같은 "
                               "공급형 일반공급 '일반' 계층으로도 자동 신청된다(p.3)."}],
         notes=INTEGRATED_NOTES + [
             "공급형(31A·31AS·44A)과 입주자격 구분마다 우선·일반 배정 호수가 다르다(p.2~3) — 배정이 없는 구분·공급형은 신청할 수 없다.",
             "우선공급 중 철거민·국가유공자·장기복무제대군인·비주택거주자 등은 기관 요청에 따라 현장 접수만 받는다(p.5)."]),
    # 처음 보는 실공고 검증(2026-11-08) — SH 국민임대 두 번째 공고(한 해 앞, 2025.08.20.). 초안은 등록 전에
    # docs/draft-checks/Z-sh-national-2025-1.draft.json에 얼림. 2024년도 소득표·2025년 자산 한도 → edition="2025"
    dict(nid="N60", key="SH60", title="SH 2025년 제1차 국민임대주택 입주자모집", ann="2025-08-20",
         program="국민임대주택", template="sh_national_rental",
         params={"eligibility_quote": "현재서울특별시에거주하는성년자인무주택세대구성원으로서",
                 "adult_quote": "민법상미성년자(만19세미만)는공급신청할수없습니다",
                 "income_quote": "해당세대의월평균소득이전년도도시근로자가구원수별가구당월평균소득의70퍼센트이하인사람",
                 "near_quote": "상계장암지구1,2단지는서울특별시외의정부시,남양주시,양주시,포천시에거주하는사람도신청가능",
                 "weak_quote": "1~7중한개이상의자격을갖춘사람(공급신청자본인)만신청가능", "edition": "2025"},
         notes=[
             "2025년 공고다 — 소득은 2024년도 도시근로자 월평균소득, 총자산 3억3,700만원·자동차 3,803만원(출생자녀 가산) 기준이다(p.24).",
             "전용 50㎡ 이하는 월평균소득 50% 이하(1인 70%·2인 60%) 세대에 먼저 공급하고 남으면 70% 이하에 공급한다 — 70% 이하면 신청 "
             "자격이 있고 50% 여부는 선정 순서라 판정하지 않는다(p.23·p.27).",
             "경쟁 시 순위(50㎡ 이하는 해당구·연접구 거주, 59㎡는 청약저축 24회·6회)와 미성년 자녀 3명 이상·배점은 선정 순서라 "
             "판정하지 않는다(p.26~30).",
             "주거약자 주택은 공급신청자 본인이 고령자(만 65세 이상)·장애인·상이 국가유공자 등일 때만 신청할 수 있다 — '일반(주거약자용)' "
             "계층으로 판정한다(p.28).",
             "과거 공공임대주택 임차권 양도·전대로 적발된 뒤 4년이 지나지 않은 세대구성원이 있으면 신청할 수 없다 — 이 판정은 묻지 않는다(p.22).",
             "외국인은 신청할 수 없고, 1세대 1주택 신청 원칙(중복 신청은 모두 무효)이다(p.22).",
             "소득 기준표는 원문이 1~6인만 적는다 — 7인 이상 세대는 이 판정이 기준 금액을 모른다(표에 없음)."]),
    # 처음 보는 실공고 검증(2026-11-08) — LH 고령자복지주택 두·세 번째 공고. 초안은 등록 전에 docs/draft-checks/
    # Z-lh-elderly-inje·Z-lh-elderly-donghae.draft.json에 얼림(신청자격 문장에 출생일이 없고 2순위가 '소득70%…이하인자' — 초안 막힘)
    dict(nid="N61", key="LH61", title="인제서화 고령자복지주택(영구임대) 입주자", ann="2026-06-08",
         program="고령자복지주택", template="elderly_welfare",
         params={"eligibility_quote": "현재만65세이상으로서무주택세대구성원요건을만족하고",
                 "merit_quote": "소득70%(1인90%,2인80%)이하인자", "general_quote": "50%(1인70%,2인60%)이하인자",
                 "kind": "영구임대", "asset_quote": "가액합산기준24,500만원이하", "car_quote": "개별자동차가액4,542만원이하"},
         notes=[
             "순위(1순위 생계·의료급여, 2순위 국가유공자 등, 3순위 일반)는 신청 자격의 갈래로 판정하고, 같은 순위 안의 배점·추첨은 "
             "판정하지 않는다(p.5·p.8).",
             "과거 공공임대주택 불법 양도·전대로 적발된 뒤 4년이 지나지 않은 세대구성원이 있으면 선정될 수 없다 — 이 판정은 묻지 않는다(p.4).",
             "금융정보 등 제공 동의서를 내지 않으면 신청할 수 없다(p.3). 외국인은 신청할 수 없다(p.4).",
             "생계·의료급여 수급자 등은 '가군' 임대조건이 따로 적용된다(p.2) — 임대료는 판정하지 않는다."]),
    dict(nid="N62", key="LH62", title="동해천곡 고령자복지주택(영구임대) 입주자", ann="2026-08-24",
         program="고령자복지주택", template="elderly_welfare",
         params={"eligibility_quote": "현재만65세이상으로서무주택세대구성원요건을만족하고",
                 "merit_quote": "소득70%(1인90%,2인80%)이하인자", "general_quote": "50%(1인70%,2인60%)이하인자",
                 "kind": "영구임대", "asset_quote": "가액합산기준24,500만원이하", "car_quote": "개별자동차가액4,542만원이하"},
         notes=[
             "순위(1순위 생계·의료급여, 2순위 국가유공자 등, 3순위 일반)는 신청 자격의 갈래로 판정하고, 같은 순위 안의 배점·추첨은 "
             "판정하지 않는다(p.5·p.8).",
             "과거 공공임대주택 불법 양도·전대로 적발된 뒤 4년이 지나지 않은 세대구성원이 있으면 선정될 수 없다 — 이 판정은 묻지 않는다(p.4).",
             "금융정보 등 제공 동의서를 내지 않으면 신청할 수 없다(p.4). 외국인은 신청할 수 없다(p.5).",
             "생계·의료급여 수급자 등은 '가군' 임대조건이 따로 적용된다(p.3) — 임대료는 판정하지 않는다."]),
    # 2026 판 나눔형(이익공유형) 본청약 — 고양창릉 S-3. 초안은 등록 전에 docs/draft-checks/Z-lh-share-goyang-s3.draft.json에 얼림(막힘)
    dict(nid="N63", key="LH63", title="고양창릉 S-3블록 이익공유형(나눔형) 분양주택", ann="2026-06-30",
         program="공공분양(나눔형)", template="lh_share_sale",
         params={"residence": CAPITAL, "youth_income_quote": "청년특별공급도시근로자가구원수별가구당월평균소득액의140%5,338,708",
                 "asset_quote": "362,000천원이하", "youth_asset_quote": "276,000천원이하", "parents_quote": "1,035,000천원이하",
                 "dual_quote": "(본인및배우자가모두소득이있는경우200%)이하인분", "edition": "2026"},
         unsupported=[{"name": "사전청약 당첨자", "page": 2,
                       "note": "2024년 사전청약 당첨자(입주예약자)는 따로 신청한다(7.20.~7.21.) — 판정하지 않는다."}],
         notes=SHARE_2026_NOTES),
    # 2026 판 선택형 = 6년 분양전환 공공임대 최초 모집 — 군포대야미 A-1. 초안은 등록 전에 docs/draft-checks/Z-lh-select-gunpo-a1.draft.json(막힘)
    dict(nid="N64", key="LH64", title="군포대야미 A-1블록 6년 분양전환 공공임대주택(선택형)", ann="2026-06-30",
         program="공공분양(선택형)", template="lh_select_rental",
         params={"residence": CAPITAL, "youth_income_quote": "청년특별공급도시근로자가구원수별가구당월평균소득액의140%5,338,708",
                 "asset_quote": "362,000천원이하", "youth_asset_quote": "276,000천원이하", "parents_quote": "1,035,000천원이하",
                 "dual_quote": "가구원수가2명인경우에는140%(본인및배우자가모두소득이있는경우에는200%)", "edition": "2026"},
         unsupported=[{"name": "기관추천·국가유공자 특별공급", "page": 14,
                       "note": "국가유공자·장애인·철거민 등 기관이 추천해 통보한 대상자만 신청한다 — 판정하지 않는다."},
                      {"name": "사전청약 당첨자", "page": 13,
                       "note": "사전청약 당첨자(입주예약자)는 7.13.~7.14. 따로 신청한다 — 판정하지 않는다."}],
         notes=SELECT_2026_NOTES),
    # SH 다자녀 매입임대(2026.5.29.) — 판정 틀의 첫 공고. 초안은 등록 전에 docs/draft-checks/Z-sh-multichild-2026.draft.json(미지원 사업)
    dict(nid="N65", key="SH65", title="SH 2026년 다자녀 매입임대주택 입주자모집", ann="2026-05-29",
         program="다자녀 매입임대", template="sh_multichild_rental",
         params={"eligibility_quote": "두명이상의직계비속(태아를포함하며,「민법」상미성년자로한정함)을양육하고,무주택세대구성원으로서",
                 "income_quote": "70%이하5,717,9006,161,5416,528,8906,934,3847,339,8797,745,373",
                 "asset_quote": "총자산가액:34,500만원이하", "car_quote": "자동차가액(현재가치기준):4,542만원이하"},
         notes=MULTICHILD_NOTES),
    # 통합공공임대 일자리연계형 — 판정 틀의 첫 두 공고(전주는 지역전략산업 종사자, 담양은 사업·근로소득자). 초안은 등록 전에
    # docs/draft-checks/Z-lh-integrated-jeonju-job·Z-lh-integrated-damyang-job.draft.json(변형 공고라 막힘)
    dict(nid="N66", key="LH66", title="전주동서학 통합공공임대 일자리연계형 지원주택 입주자", ann="2026-09-14",
         program="통합공공임대(일자리연계형)", template="integrated_job_rental",
         params={"job_kind": "regional",
                 "job_quote": "지역전략산업에종사하는사람등전주시장이지역전략산업의육성을위해필요하다고인정한사람"},
         unsupported=[{"name": "장기종사자", "page": 11, "note": "미성년 자녀 포함 3인 이상 세대 + 중소기업·동일기업 근속 또는 동일사업 "
                                                                "영위 — 근속 기간을 묻지 않아 판정하지 않는다."},
                      {"name": "주거약자용주택(31AS형)", "page": 13, "note": "고령자·장애인 등 주거약자만 신청하는 별도 주택형 — 판정하지 않는다."}],
         notes=JOB_NOTES + ["직업기준은 전주시·국가유산청이 인정한 무형유산 종사자(전북 주민등록 + 국가·전북 무형유산 보유자·전승교육사·이수자) "
                            "또는 예술인 종사자(전주 주민등록 + 예술활동증명)다 — 사전 상담 필수, '직업기준 충족'을 묻는다(p.10)."]),
    dict(nid="N67", key="LH67", title="담양삼만 통합공공임대 일자리연계형 지원주택 추가 입주자", ann="2026-10-29",
         program="통합공공임대(일자리연계형)", template="integrated_job_rental",
         params={"job_kind": "earner", "job_quote": "「소득세법」제19조제1항또는제20조제1항에따른사업소득또는근로소득이있는사람"},
         unsupported=[{"name": "장기종사자", "page": 9, "note": "미성년 자녀 포함 3인 이상 세대 + 중소기업·동일기업 근속 또는 동일사업 "
                                                               "영위 — 근속 기간을 묻지 않아 판정하지 않는다."},
                      {"name": "주거약자용주택", "page": 1, "note": "고령자·장애인 등 주거약자만 신청하는 별도 주택형 — 판정하지 않는다."}],
         notes=JOB_NOTES + ["직업기준은 사업소득 또는 근로소득이 있는 사람이다(p.9)."]),
    # SH 행복주택 — 판정 틀의 첫 공고(2026년 1차). 같은 사업 2025년 1차·3차 공고는 처음 보는 공고 검증용으로 초안만 얼림
    # (docs/draft-checks/Z-sh-happy-2026-1·2025-1·2025-3.draft.json — 등록 전 미지원 사업)
    dict(nid="N68", key="SH68", title="SH 2026년 1차 행복주택 입주자모집", ann="2026-05-28",
         program="행복주택", template="sh_happy_housing",
         params={"ann": "2026-05-28", "layers": ["대학생", "청년", "신혼부부", "한부모"],
                 "extra_layers": ["고령자", "주거급여수급자"], "child": "2019-05-29"},
         notes=SH_HAPPY_NOTES),
]

ANCHORS = {"일반": ("신청자격", 5), "일반(고령자 주택형)": ("신청자격", 5), "일반(주거약자용)": ("신청자격", 5)}
# 통합공공임대는 계층 이름(일반 등)이 다른 사업과 겹치고, 같은 문구가 우선공급(p.15~16)·일반공급(p.16~18)에 다 있어
# 일반공급 쪽을 가리키는 기준점을 템플릿별로 둔다(인용문·기준표 모두).
TEMPLATE_ANCHOR = {"integrated_rental": ("신혼부부,한부모가족을제외한모든계층", 17), "public_rental": ("무주택세대구성원", 1),
                   "newlywed_town_sale": ("신혼부부신청자격", 11), "public_sale": ("다자녀가구특별공급■신청자격", 20),
                   "sh_land_sale": ("청년특별공급■신청자격", 28), "sh_national_rental": ("4.신청자격가.공통사항", 22),
                   "sh_permanent_rental": ("3신청자격", 7),
                   "elderly_welfare": ("4.신청자격", 5),
                   "sh_multichild_rental": ("2신청자격및신청순위■신청자격", 6),
                   "integrated_job_rental": ("신분기준", 11),
                   "lh_share_sale": ("1.청년특별공급■신청자격", 9),
                   "lh_select_rental": ("2.청년특별공급■신청자격", 11),
                   "sh_happy_housing": ("▶자산기준", 22)}
# 계층마다 자기 절을 가리키는 기준점(같은 문구 — '혼인 중이 아닐 것' 등 — 가 여러 계층 절에 다 있다)
LAYER_ANCHOR = {"sh_happy_housing": {"대학생": ("대학생계층○일반공급", 24), "청년": ("청년계층○일반공급", 26),
                                     "신혼부부": ("한부모가족계층○일반공급", 28), "한부모": ("한부모가족계층○일반공급", 28),
                                     "고령자": ("고령자○일반공급", 31), "주거급여수급자": ("주거급여수급자○일반공급", 32)}}


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
            "public_rental": public_rental, "newlywed_town_sale": newlywed_town_sale, "public_sale": public_sale,
            "sh_land_sale": sh_land_sale, "sh_national_rental": sh_national_rental,
            "sh_permanent_rental": sh_permanent_rental,
            "elderly_welfare": elderly_welfare, "sh_multichild_rental": sh_multichild_rental,
            "integrated_job_rental": integrated_job_rental,
            "lh_share_sale": lh_share_sale,
            "lh_select_rental": lh_select_rental, "sh_happy_housing": sh_happy_housing}
ISSUER = {"national_rental": "LH", "permanent_rental": "LH", "integrated_rental": "LH", "public_rental": "LH",
          "newlywed_town_sale": "LH", "public_sale": "LH", "sh_land_sale": "SH", "sh_national_rental": "SH", "sh_permanent_rental": "SH", "elderly_welfare": "LH", "lh_share_sale": "LH", "lh_select_rental": "LH",
          "sh_multichild_rental": "SH", "integrated_job_rental": "LH", "sh_happy_housing": "SH"}


def make_doc(plan, pdf, pages):
    """PLAN 항목(또는 같은 모양의 파라미터 시트) + 원문 쪽 텍스트 → 공고 규칙 문서. 인용문 쪽은 원문에서 찾고,
    찾지 못한 인용문은 missing으로 돌려준다(새 공고에서 문구가 달라진 조건을 드러낸다)."""
    layers, tables = BUILDERS[plan["template"]](plan["nid"], **plan["params"])
    missing = []
    own = TEMPLATE_ANCHOR.get(plan["template"])
    for layer, ldoc in layers.items():
        text, hint = LAYER_ANCHOR.get(plan["template"], {}).get(layer) or own or ANCHORS[layer]
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
