# 공고문 분석 공통 기준서 (서브에이전트용)

## 프로젝트
주거·복지 Eligibility 플랫폼. 사용자의 가구 프로필을 받아 특정 공고·계층(공급유형)의 **신청 자격**을
결정론적 Rule Engine으로 판정한다. LLM은 판정에 쓰지 않는다. 현재 LH 행복주택 공고 3건
(서울공릉=N1, 서울관악봉천=N2, 서울번동3=N3; 계층: 대학생·청년·신혼부부·한부모)이 JSON 규칙 데이터로 구현돼 있다.
이번에 실제 공고문 23건이 추가됐고, **현재 구조로 일반화되는지**를 판단하려 한다.

## 판정 모델 (바꾸지 않는 원칙)
- 판정 5종: ELIGIBLE / INELIGIBLE / NEEDS_INFO(정보 부족) / MANUAL_REVIEW(원문 해석 미확정·자기신고·입력 모순) / NOT_OFFERED(그 공고에 해당 계층 없음)
- 미입력(None) ≠ 0. 날짜 컷오프는 정확한 날짜 비교(공고일 기준 N년 이내 등).
- 판정 범위는 **신청 자격(필수요건)** 까지. 순위·배점·추첨·당첨은 범위 밖(단, 구조는 파악해 보고).

## 현재 규칙 데이터 구조 (rules/notices/*.json)
- 공고: notice_id, title, announcement_date, source{document, sha256, pages}, review{status}, tables{}, layers{계층: {conditions: [...]}}
- 계층(layer)은 현재 대학생/청년/신혼부부/한부모 4개만 허용(로더가 그 외 거부).
- 조건: {id, field, required, source{page, clause, quote[원문 그대로]}, note, check(조건식), table?(결정표 이름), timing? NOW|BEFORE_MOVE_IN}
- 조건식 연산자(닫힌 집합): var(프로필 필드), ctx(announcement_date), date(리터럴), fn(허용 함수: child_bonus_count, years_before, marriage_cutoff, young_child_cutoff),
  lookup(기준값 표: income_standard = 도시근로자 가구원수별 월평균소득 100~140%), term(결정표 출력), eq/ne/lte/gte/in/between, all/any, is, if, review_if_true
- 결정표: columns/inputs/outputs/rows(when→out | result NO_ROW)/readings(해석 후보 여러 개면 결과가 갈릴 때 MANUAL_REVIEW)
- 프로필 필드(현재): age, marital_status(미혼/혼인중/예비신혼/한부모), home_ownership(무주택/주택보유), house_head_status(세대주/세대원),
  household_size, monthly_income, total_assets, car_value, has_subscription_account, subscription_months, subscription_payment_count,
  dual_income, residence_region, residence_years, is_social_rookie, student_status, grad_or_dropout_date, marriage_date, has_children,
  children_birth_dates, youngest_child_birth_date
- 소득기준표: 2025년 도시근로자 가구원수별 월평균소득 (예: 3인 100% = 8,168,429원, 1인 120% = 4,576,036원)

## 분석 방법
텍스트 파일 경로: 이 폴더의 `<KEY>.txt` (`===== PAGE n =====` 표시로 쪽 구분, PDF 텍스트 추출이라 글자 사이 공백·표 깨짐이 있을 수 있음).
원문은 실제 공고문이다. **추측하지 말고 원문에 있는 것만** 적고, 쪽수를 붙여라. 불확실하면 "불확실"이라고 적어라.
텍스트가 깨져 판단이 어려운 부분은 그 사실을 적어라(원본 PDF 경로는 index.json 참고, 필요하면 pypdf로 해당 쪽만 다시 볼 수 있음).

## 산출물 (공고마다 `analysis/<KEY>.md` 파일 하나, 한국어)
1. **기본정보**: 발행기관(LH/SH), 사업유형(행복주택/매입임대/전세임대/장기전세/미리내집 등), 공고명, 입주자모집공고일, 지역, 쪽수, 정정공고 여부
2. **공급 대상 계층(유형) 목록**: 계층별로 무엇이 다른지 한 줄씩
3. **계층별 신청자격 조건표**: | 계층 | 조건 | 원문 요지(짧게 인용) | 쪽 | 수치(한도·비율·연령·기간) |
   - 무주택 기준(본인/세대 전원/혼인으로 구성될 세대), 연령, 혼인·자녀, 소득(기준표·비율·가구원수 산정·맞벌이·자녀가산), 자산·자동차, 청약통장, 거주지/근무지, 기타(재학·소득활동기간·장애·수급자 등)
4. **기준값 표**: 공고에 실린 소득·자산 표의 수치(사용된 연도 기준, 비율 열). 기존 2025년 도시근로자 표(3인 100%=8,168,429)와 같은지 다른지 명시. 다른 기준(예: 기준중위소득, 전년도 도시근로자 70%·50%)이면 수치를 옮겨 적기
5. **현재 구조로 표현 가능 여부**(가장 중요): 조건마다 ✅ 그대로 가능 / 🟡 새 프로필 필드·새 함수·새 기준표만 추가하면 가능 / 🔴 새 구조 필요(예: 순위별 다른 요건, 우선순위 단계, 지역 조건, 기간 계산 등) — 각각 무엇이 필요한지 구체적으로
6. **순위·배점·우선공급 구조**(범위 밖이지만 요약): 1·2·3순위 기준, 배점 항목
7. **모호하거나 해석이 갈리는 지점**(MANUAL_REVIEW 후보): 원문 인용과 쪽수
8. **같은 그룹의 다른 공고와 비교**(그룹 내 공고가 여럿이면): 차이 나는 조건·수치·날짜만 (회차만 다른 거의 동일 공고인지)

마지막으로 그룹 전체 요약을 `analysis/GROUP_<n>.md`에 쓰고, 최종 응답으로 그 요약을 그대로 반환하라
(핵심: 공통 조건 패턴, 새로 필요한 필드/함수/기준표/구조 목록, 🔴 항목, 텍스트 추출 문제).
