# 02. 데이터 스키마 개요

> 전체 원본은 `data/MVP0_v2_LH공식원문3건_Rule스키마_대조표.xlsx`에 있다. 이 문서는
> 그 워크북의 시트 구조와, 코드(`src/`)가 그중 무엇을 실제로 구현했는지를 매핑한다.

## 워크북 시트 구성

| 시트 | 내용 | 코드 매핑 |
|---|---|---|
| README | 설계 결정 요약 | → `docs/01-decisions-log.md`로 이관·확장됨 |
| programs | 상위 정책(예: 행복주택) | `src/notices_data.py` 상단 주석 |
| notices | 공고 3건(N1/N2/N3) 메타데이터 | `src/notices_data.py`의 `N1/N2/N3` 객체 |
| rules | 공고별 조건(계층별, source_ref 포함) | `src/notices_data.py`의 각 `*_conditions` 리스트 |
| reference_values | 도시근로자 가구원수별 소득기준표 | `src/rule_engine.py`의 `INCOME_TABLE` |
| income_basis | 계층별 가구원수 산정 방식 정리 | `src/notices_data.py`의 `spouse_terms_*`, `_youth_income_ok` |
| profiles | 테스트용 프로필 12개 | `src/profiles_data.py`의 `PROFILES` |
| match_matrix | 프로필×공고 수기 판정표(정답지) | `src/profiles_data.py`의 `EXPECTED` |

## 핵심 데이터 모델 (코드 기준)

```
HouseholdProfile          # 사용자 입력 (등본 기반 사실값 포함)
├── age, marital_status, home_ownership
├── house_head_status     # "세대주" / "세대원" / None — 등본 사실값, 추론 금지
├── household_size        # 판정 목적에 따라 이미 계산된 값을 받음(계층별로 산정법 다름)
├── monthly_income, total_assets, car_value
├── has_subscription_account, subscription_months, subscription_payment_count
├── has_child_under_2      # 우선공급(2세미만) 자격용 — young_child_count와 다른 개념
├── young_child_count       # 2023.3.28 이후 출생 자녀 수 — 소득·자산 가산기준용
├── dual_income
└── residence_region, residence_years   # 우선공급 배점용

RuleCondition              # rules 시트 한 행
├── rule_id, field, required, source_ref, note
└── check: profile -> True/False/None(확인불가)

NoticeRuleSet
└── layers: {계층명: LayerRuleSet(conditions=[RuleCondition, ...])}

evaluate(profile, notice, layer) -> EvaluationResult
├── layer가 notice에 없으면 → NOT_OFFERED
├── required 조건 중 하나라도 False → INELIGIBLE
├── False는 없고 None(확인불가)이 있으면 → NEEDS_INFO
└── 전부 True → ELIGIBLE, score = 충족수/전체수 * 100
```

## 계층별 가구원수 산정 요약 (income_basis 핵심)

| 계층 | 소득 판정 대상 | 가구원수 산정 |
|---|---|---|
| 신혼부부·한부모 | 세대 전체 | 실제 무주택세대구성원 전원 |
| 청년 — 세대주 | 세대 전체 | 실제 세대원 전체 |
| 청년 — 세대원 | 본인만 | **항상 1로 고정** (자산은 실제 인원 사용 — 비대칭) |
| 대학생 | 본인 + 부모 | 통상 2~3인. "1인가구"는 등본상 본인 단독 등재(가족관계 단절 등) 시에만 |

## 아직 코드에 없는 것 (rules 시트엔 있지만 미구현)

- N1/N3 신혼부부·한부모의 세부 서류조건(혼인관계증명서 등) — verdict에 영향 없어 낮은 우선순위
- 예비신혼부부의 "혼인으로 구성될 세대 전원 무주택" 검증은 `home_ownership` 단일 필드로
  단순화되어 있음 — 실제로는 배우자 예정자 쪽 세대도 별도로 조회해야 함
- N2(관악봉천) 주거약자용 서브타입, N1 주거약자용 서브타입 — 별도 물량이라는 사실만
  문서화했고 별도 조건 리스트로 코드화하지 않음
