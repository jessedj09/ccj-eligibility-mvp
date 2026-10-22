# 주거·복지 Eligibility 플랫폼 — 프로젝트 메모리

> 이 파일은 Claude Code가 세션 시작 시 자동으로 읽는다. 상세 내용은 각 링크된 문서에
> 있으니, 여기서는 "무엇이 어디 있는지"와 "절대 어기면 안 되는 원칙"만 적는다.

## 한 줄 요약

정부 주거·복지 혜택(LH 행복주택 등)을 사용자 프로필과 대조해 "신청 가능/불가능/추가확인
필요"를 근거와 함께 자동 판정하는 서비스. 핵심 자산은 LLM이 아니라 **결정론적 Rule
Engine**이다.

## 지금 어디까지 왔나

- MVP0 단계: LH 공식 공고문 3건(서울공릉/서울관악봉천/서울번동3)을 실제로 구조화하고,
  Python Rule Engine을 짜서 사람이 손으로 만든 정답지(12개 프로필 × 3개 공고 = 36건)와
  100% 일치하는 것까지 검증 완료.
- Explainability 레이어(`src/explainability.py`) 구현 완료, Streamlit 데모 UI(`app.py`)
  1차 배포 완료(GitHub public repo + Streamlit Community Cloud).
- **MVP0.1(2026-09-19)**: ChatGPT Codex의 MVP0 리뷰를 원문 PDF와 대조해 재현·수정.
  대학생 재학요건, 청년 연령/사회초년생/무주택, 신혼부부 혼인기간, 한부모 자녀연령,
  대학생·청년 자녀가산이 전부 미구현이었던 것을 확인하고 추가했다. 세대주 정보 미상 시
  세대주로 추정하던 버그, 소득/자산 `None`(미입력)을 0으로 취급하며 예외까지 발생시키던
  버그도 수정했다. 상세 내용은 반드시 **[docs/rule-coverage-matrix.md](docs/rule-coverage-matrix.md)**
  를 읽을 것 — 이번 개정으로 확인이 필요한(원문 자체가 모호한) 쟁점들도 함께 정리되어 있다.
- **MVP0.2(2026-09-30, 브랜치 `mvp0.2-manual-review`)**: 설계문서 v0.1의 `MANUAL_REVIEW`를
  구현(대학생·청년 2인+자녀, 청년 세대원+자녀, 사회초년생 자기신고 → 수동 확인). 자녀 "없음"과
  "모름"을 구분하는 `has_children` 추가. **MVP0.1의 N3 자녀 컷오프 1일 오류 수정**(만 7세를
  6세 이하로 통과시키던 버그) — "6세 이하" 컷오프는 공고일 7년 전의 다음 날이라는 공식이 N1
  리터럴을 정확히 재현한다. 독립 검증용 `docs/independent-validation-worksheet.md`,
  LH 질의서 `docs/lh-inquiry-questions.md` 작성. 화면은 Streamlit `AppTest`로 28개
  공고×계층×샘플 조합을 실제 실행해 예외 없음을 확인했다.
- **MVP0.3(브랜치 `mvp0.3-child-count`)**: 출생자녀 가산 대상 자녀 수를 엔진이 직접 계산
  (`children_birth_dates` → `bonus_child_count`). 화면은 자녀별 생년월일만 입력받는다. 입력 폼
  (`st.form`)을 제거해 자녀/혼인 조건부 입력칸이 즉시 나타나도록 고쳤다(폼 안에서는 제출 전까지
  조건부 위젯이 갱신되지 않던 MVP0.1 UX 결함). 자녀 생년월일 검증이 태아(출산예정일)를 오류로
  막던 버그도 수정.
- **B단계(P1~P3 완료)**: 규칙이 `rules/*.json` 데이터가 됐다(설계 `docs/06-rule-data-design.md`). **규칙을 고칠 때는
  파이썬이 아니라 JSON을 고친다.** `src/notices_data.py`는 31줄 호환 계층일 뿐이다. 변경 흐름: JSON 수정 →
  `pytest`(골든 `tests/test_rules_golden.py`가 바뀐 결과를 입력과 함께 보여 줌) → 의도한 변화면
  `python tools/regen_golden.py`로 갱신하고 이유를 커밋에 남긴다. 원문 근거(쪽수·인용문·수치)는 `python tools/verify_sources.py`(pytest `test_source_verify.py`에도 포함)가 공고문 PDF와 자동 대조한다 — 근거를 고치면 이 도구가 통과해야 한다. `source.derivation`(공고문에 없는 지침)은 대조 제외.
  legacy 파이썬 규칙은 P3에서 삭제됐다. 모든 공고는 JSON이 유일한 기준이다.
- **C0(2026-10-15)**: 실제 공고 26건(LH 17·SH 9, `sample_lh/`·`sample_sh/`)을 분석해 일반화 가능성을 정리했다 —
  **[docs/07-notice-generalization.md](docs/07-notice-generalization.md)**(공고별 분석 `docs/notice-analysis/`).
  새 사업유형(매입임대·든든전세·장기전세·미리내집 등)을 넣기 전에 반드시 읽을 것.
- **C1**: LH 행복주택 5건 추가(N4 하남감일·위례, N5 부천영상, N6 서울금천, N7 서울대방, N8 의왕청계2 — 기존 4계층만).
  `tools/gen_c1_notices.py`가 N1/N3 템플릿에서 생성하고 인용문 쪽을 자동 탐색한다. 템플릿과의 판정 동등성은
  `tests/test_c1_notices.py`가 확인한다. 공고에 있지만 아직 구현하지 않은 계층은 `unsupported_layers`로 적고
  화면에 "아직 지원 안 함"으로 보인다(판정하지 않음).
- **C2**: 지역 모델. 1순위 지역만 모집하는 N9 서울가좌(대학생)·N10 서울오류(4계층) 추가. 프로필 지역 필드 5개
  (`residence_area`·`school_area`·`income_base_area`·`spouse_residence_area`·`spouse_income_base_area`), 값은
  `rules/reference/regions.json` 표준 이름(서울·인천 광역, 경기 시·군, 그 밖 시도) 또는 "해당없음", 모름은 None.
  지역 `in` 목록의 오타는 로드 시 거부. 조건이 읽는 필드는 `RuleCondition.inputs`/`LayerRuleSet.inputs`에 기록되고,
  화면은 그 계층이 쓰는 지역 질문만 묻는다. 검증 `tests/test_c2_region.py`(같은 날 같은 템플릿인 N6과 판정 동등).
- **C3**: 행복주택 새 계층 4개 — 고령자(N6·N9·N10), 산업단지근로자(N6), 주거급여수급자(N10), 지역전략산업종사자(N5).
  `tools/gen_c3_layers.py`가 원문 결합표를 행 단위로 옮겨 추가한다. 프로필 필드 `industrial_workplace`·`workplace_area`·
  `industrial_affiliation`·`housing_benefit_status`·`regional_industry_type`. 부천시가 신청 후 확인하는 자격(콘텐츠산업·
  부천시 추천자)은 `SELF_REPORT_UNVERIFIED`, 부천 지역전략 계층의 출생자녀 가산은 원문에 없어 두 해석(readings)으로 계산.
  주거급여수급자는 원문에 소득·자산 조항이 없으므로 만들지 않았다. 검증 `tests/test_c3_layers.py`.
- **C3.1 점검·보강(2026-10-20)**: ① `tools/gen_c1_notices.py` 재실행 시 다른 단계가 추가한 계층이 지워지던 문제 수정
  (`preserve_later_additions`, `tests/test_generators.py`가 재실행 = 커밋 파일 동일을 확인) ② `requirements.txt`에 pypdf
  ③ 화면: 입력란 아래 "이 계층 기준"(규칙 note에서 자동 — 주택 소유·소득·자산·나이의 계층별 뜻), 나이는 생년월일 입력 →
  공고일 기준 만 나이 ④ GitHub Actions(`.github/workflows/tests.yml`: 원문 대조 + pytest + 화면 점검) ⑤ 소득 기준표 공고별 대조.
- **C4a(2026-10-20)**: 순위·유형 트랙 + LH 매입임대·든든전세 7건(N11·N12 청년매입임대, N13·N14 신혼·신생아Ⅰ, N15 Ⅱ 전세형,
  N16·N17 든든전세). 조건에 `"tracks"`를 두면 "트랙 중 하나 이상 충족"(`rule_engine.combine_tracks`, 결과는
  `EvaluationResult.tracks`/`eligible_tracks`, 화면 "순위·유형별 결과"). `tools/gen_c4_lh.py`, 검증 `tests/test_c4_lh.py`.
  **소득 기준표는 사업별 파일로 나눈다**(`income_standard`=행복주택, `income_standard_rental`=매입임대) — 한 표에 합쳤다가
  행복주택 한부모 1인 110% 칸이 매입임대 금액으로 채워지는 누수를 골든이 잡았다. 7인 이상 가산은 `adder_ratios`에만 적용.
  화면 질문은 계층 이름이 아니라 그 계층 조건이 읽는 필드(`LayerRuleSet.inputs`)로 정한다.
- **C4b(2026-10-21)**: SH 5건(N18·N19 신혼·신생아 매입임대Ⅰ·Ⅱ, N20·N21 일반주택형 미리내집, N22 장기미임대). SH 기준일은
  원문 리터럴(공고일−N년 **다음 날**). SH 소득표는 2~5인만 있고 6인 이상은 "5인 + 1인당 가산액" → 공유 기준표 대신 결정표에
  상한 금액을 직접 적는다(1인은 원문에 없어 MANUAL_REVIEW). 장기미임대는 소득이 순위 전용이라 소득 조건을 두지 않는다.
  일부 PDF는 공백 자리에 NUL 문자를 넣는다 — `source_verify.normalize`가 제어문자를 지운다. `tools/gen_c4_sh.py`, `tests/test_c4_sh.py`.
- **C5a(2026-10-21)**: 주거약자용 주택형. 변형 계층 "기본계층(주택형)" — N4·N7·N8 `신혼부부(주거약자용)`·`한부모(주거약자용)`
  = 기본 계층 조건 그대로 + 주거약자 조건(65세 이상 또는 장애인·상이 국가유공자 등), N5 `주거약자(26A1/B1형)` = 트랙(지역전략·
  청년·대학생 중 하나) + 주거약자(고령자 제외). N6·N10의 주거약자용 주택은 고령자 배정 주택형이라 고령자 판정과 같다(유의사항).
  `tools/gen_c5_housing_weak.py`는 변형 계층만 소유하고, 기본 계층을 고치면 다시 돌려 복사본을 맞춘다(`tests/test_c5_housing_weak.py`).
  생성 스크립트 담당: gen_c1 = 템플릿 계층·유의사항·미지원 목록, gen_c3 = 새 계층, gen_c5 = 주거약자용 변형 계층.
- **C5b(2026-10-22)**: SH 장기전세2 미리내집 7·8차(N23·N24), 장기전세 49·50차(N25·N26). 신청 주택 면적에 따라 소득 기준이 달라
  변형 계층 `신혼부부(전용 60㎡ 이하/초과)`, `일반(전용 60㎡ 이하/초과)`, 주거약자형 `…(주거약자형·전용 60㎡ 이하)`로 나눈다.
  장기전세의 여러 순위는 자격이 아니라 접수 순서라 **면적별 최대 상한**(60㎡ 이하 105%·맞벌이 140%, 초과 150%·200%, 출생자녀
  +10/+20%p — 맞벌이와 중복 없음)만 판정. 49차는 이전 연도 소득표·자산 6.40억 — 원문 금액을 결정표에 직접 적었다.
  장기전세2는 5년 계속 무소유(`owned_home_in_5y`). `tools/gen_c5_jeonse.py`, `tests/test_c5_jeonse.py`.
- **C5c(2026-10-22)**: 장기전세 우선공급(서울시 매입형 60㎡ 이하) — `일반(우선공급·고령자/장애인/노부모부양/2자녀이상/국가유공자)`
  = `일반(전용 60㎡ 이하)` 조건 + 유형 조건(49차는 고령자 없음). 2자녀는 자녀 생년월일로 계산(허용 함수 `children_on_or_after`,
  원문 미성년 기준일 리터럴), 국가유공자는 보훈부 통보를 확인할 수 없어 항상 MANUAL_REVIEW, 고령자 2인 세대가 배우자가 아니면
  MANUAL_REVIEW. 새 필드 `disabled_spouse_qualifies`·`supports_elderly_parent_1y`·`veteran_priority_notified`. `tests/test_c5c_priority.py`.
  **이로써 화면에 "아직 지원 안 함"으로 남은 계층이 없다.**
- **D1(2026-10-22)**: 한 번 입력해 전 공고·계층을 판정하는 `src/matcher.py` + 화면 `pages/1_내_조건으로_공고_찾기.py`.
  같은 질문의 계층별 뜻(주택 소유·소득·자산이 본인/세대/본인+부모/세대주 여부에 따라)은 `rules/reference/input_scope.json`이
  정하고, 매처가 계층마다 `HouseholdProfile`을 만들어 기존 `evaluate`로 판정한다(엔진·규칙 불변). 생년월일 → 공고별 만 나이.
  트랙이 다른 계층 이름인 계층(부천 주거약자)은 트랙마다 그 계층의 범위로 판정해 합친다. 검증 `tests/test_matcher.py`
  (본인=세대 입력이면 공고별 직접 판정과 같음, 범위가 갈리는 손 사례).
- pytest: 총 **616개 전부 통과**(약 11분 — 원문 대조가 PDF 26건을 읽는다). 화면 점검: `python tools/ui_smoke.py`(4~6분, 12단계).
  **생성 스크립트(tools/gen_*.py)를 고친 뒤에는 반드시 다시 돌려 `git status rules/`가 의도한 변경만 보이는지 확인할 것.**
- **다음 과제 후보: D2**(프로필 저장·API, 공고 접수기간 표시) 또는 남은 미지원(장기전세 우선공급 5종). 상세는
  docs/04-open-items-and-next-steps.md 맨 위 "다음 과제". 사람이 할 일(독립 검증 워크시트, LH 질의)은 계속 보류 중.

## 반드시 지켜야 할 원칙 (요약 — 근거는 docs/01-decisions-log.md)

1. **LLM은 공고문 파싱에만 쓴다. 자격 판정(verdict)은 100% 결정론적 코드로만 한다.**
2. **verdict는 5상태다**: `ELIGIBLE` / `INELIGIBLE` / `NEEDS_INFO` / `MANUAL_REVIEW` /
   `NOT_OFFERED`. `NOT_OFFERED`(이 공고엔 해당 계층 자체가 없음)를 `INELIGIBLE`과 절대 섞지 말 것.
   **`NEEDS_INFO`(사용자가 정보를 더 넣으면 해결)와 `MANUAL_REVIEW`(정책 해석 미확정·자기신고
   의존 — 정보를 더 넣어도 해결 안 됨)를 섞지 말 것.** 우선순위: 확정 불충족 > MANUAL_REVIEW >
   NEEDS_INFO > ELIGIBLE. 원문 표에 없는 조합이나 해석이 갈리는 조건은 임의로 한쪽을 택해
   통과/탈락시키지 말고 `resolve_interpretations()`로 여러 해석을 계산해 갈릴 때만 MANUAL_REVIEW.
3. **score = 충족 필수조건 수 / 전체 필수조건 수.** "당첨 확률 예측"이 아니다 — ML로
   당첨 가능성을 추정하는 기능은 MVP 범위에서 명시적으로 제외되어 있다.
4. **등본에 이미 적힌 사실(세대주/세대원 여부, 1인가구 여부)은 Rule Engine이 추론하지
   않는다.** 프로필 입력값으로 그대로 받는다. **이 정보가 `None`(미확인)이면 절대 특정
   값(예: 세대주)으로 추정하지 말고 `NEEDS_INFO`로 처리한다** — MVP0.1에서 이 원칙이
   깨져 있던 버그를 수정했다(rule-coverage-matrix.md 버그 5번).
5. **소득과 자산은 "가구원수" 산정 기준이 계층마다, 심지어 같은 계층 안에서도 서로
   다르다.** 예: 청년(세대원)은 소득 판정 시 가구원수를 무조건 1로 고정하지만, 자산
   판정은 실제 가구원수를 그대로 쓴다 — 이 비대칭을 절대 하나로 합치지 말 것.
   (자세한 표는 docs/02-data-schema.md, 코드는 src/notices_data.py)
6. **미입력(모름)과 실제 0/False는 다르다.** `monthly_income`/`total_assets`는
   `Optional[int]`이고 `None`은 미확인, `0`은 실제 무소득/무자산이다. 새 필드를 추가할
   때도 이 구분을 유지할 것 — 엔진에 `None`이 들어와도 예외 없이 `NEEDS_INFO`로
   귀결되어야 한다(`validate_profile()`로 사전 검증).
7. **혼인기간/자녀연령처럼 날짜가 걸린 조건은 "만 나이 floor 공식"으로 계산하지 않는다.**
   `years_elapsed(start,on)<=N` 같은 floor 방식은 "N년 경과+1일"을 "N년 이내"로 잘못
   통과시키는 경계 버그가 있다(MVP0.1에서 실제로 잡음). 반드시 `rule_engine.is_within_years()`
   처럼 "정확한 컷오프 날짜와의 직접 비교"를 쓸 것. 원문에 리터럴 컷오프 날짜가 있으면
   그 값을 그대로 쓰고(N1), 없으면 근사치임을 명시할 것(N3, rule-coverage-matrix.md §3).
   **기준일 관행은 발행기관마다 다르다**: LH는 혼인 7년 = 공고일−7년 당일, SH는 공고일−7년의 **다음 날**
   (SH25 p.13 "2019.4.25. 이후, 당일포함" — 공고 4.24). `marriage_cutoff`는 LH 관행이다. SH 공고에는
   원문 날짜 리터럴을 쓸 것(docs/07 §3).

## 파일 구조

- `docs/00-project-overview.md` — 사업 배경, 시장조사 결론, MVP 타깃/범위
- `docs/01-decisions-log.md` — 설계 중 발견한 이슈와 해결 과정 전체 (가장 중요, 자주 참조)
- `docs/02-data-schema.md` — programs/notices/rules/reference_values/income_basis 스키마
- `docs/03-validation-methodology.md` — 테스트 프로필을 어떻게 설계했고 이 검증의 한계는
  무엇인지 (반드시 읽을 것 — "36/36 통과"가 의미하는 것과 의미하지 않는 것)
- `docs/04-open-items-and-next-steps.md` — 아직 안 끝난 것, 다음에 할 것
- `docs/rule-coverage-matrix.md` — **MVP0.1 원문·구현 대조표** (재현한 버그, 확인이 필요한
  원문 해석 쟁점, 지원 범위 밖 항목 — 규칙을 고치기 전에 반드시 먼저 볼 것)
- `src/rule_engine.py` — 판정 엔진 본체 (HouseholdProfile, RuleCondition, evaluate(),
  validate_profile(), 날짜 컷오프 헬퍼)
- `src/notices_data.py` — `rules/`에서 로드한 N1/N2/N3·`ALL_NOTICES`를 내보내는 호환 계층(규칙 본체 아님)
- `src/rule_data.py` — JSON 규칙 로더·조건식 컴파일러(닫힌 연산자 집합, 로드 시 구조·참조 검증)
- `rules/` — **규칙의 원본**: `notices/N1~N26.json`(조건·결정표·출처·검수 상태·미지원 계층), `reference/income_standard*.json`·`regions.json`
- `sample_lh/`·`sample_sh/` — 공고문 PDF 원본(원문 대조 도구가 `source.document` 파일명으로 찾는다)
- `tests/golden/` + `tools/regen_golden.py` — 골든 스냅샷(고정 입력 152,747건의 결과 기록)과 재생성 도구
- `tools/verify_sources.py`(원문 대조), `tools/ui_smoke.py`(화면 헤드리스 점검), `tools/gen_c1_notices.py`(템플릿 기반 공고 생성), `tools/gen_c3_layers.py`(새 계층 추가), `tools/gen_c4_lh.py`(LH 매입임대·든든전세), `tools/gen_c4_sh.py`(SH 매입임대·장기미임대), `tools/gen_c5_housing_weak.py`(주거약자용), `tools/gen_c5_jeonse.py`(SH 장기전세·장기전세2)
- `src/priority_scoring.py` — 우선공급 배점(verdict와 분리된 별도 점수)
- `src/profiles_data.py` — 테스트용 프로필 12개 + 수기 정답지
- `src/explainability.py` — EvaluationResult → 사용자용 근거 문구(Explanation) 변환
- `app.py` — Streamlit 데모 UI: 공고 하나 판정 (판정 로직 없음, src/ 함수만 호출)
- `pages/1_내_조건으로_공고_찾기.py` — 전체 공고 판정 화면(src/matcher.py)
- `mvp0/` — **실행 대상 아님.** 초기 스냅샷(옛 버전), `mvp0/README.md` 참조
- `tests/` — pytest 스위트, **총 616개**(회귀 36 + 경계값 32 + 자녀가산 9 + 우선공급배점 5 +
  explainability 6 + MVP0.1 28 + MVP0.2 34 + MVP0.3 22 + 규칙 데이터화·골든·가구원수 모순 MVP0.6·원문 대조 P4·C1 공고 추가·C2 지역·C3 새 계층)
- `data/*.xlsx` — MVP0 설계 워크북 원본 (programs/notices/rules/reference_values/
  income_basis/profiles/match_matrix 시트 — 코드보다 사람이 보기 편한 원본)

## 실행 방법

설치·앱 실행·테스트 실행 방법은 [README.md](README.md)에 정리했다(중복 방지를 위해
여기서는 요약만): `pip install -r requirements.txt` → `streamlit run app.py` /
`cd tests && python -m pytest -q`.

@docs/01-decisions-log.md
@docs/03-validation-methodology.md
@docs/rule-coverage-matrix.md
@docs/lh-inquiry-questions.md
