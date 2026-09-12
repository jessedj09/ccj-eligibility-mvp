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
- pytest 회귀·경계값·자녀가산·우선공급배점 테스트까지 작성 완료 (82개 테스트, 전부 통과).
- Explainability 레이어(`src/explainability.py`) 구현 완료 — 판정 결과를 근거(note+
  source_ref)와 함께 보여주는 `Explanation` dataclass 생성 (테스트 5개 추가, 총 87개
  전부 통과).
- 다음 단계: `Explanation`을 실제 화면/API로 렌더링하는 부분, 그리고
  docs/04-open-items-and-next-steps.md의 나머지 항목(외부 독립 검증, 이상치 테스트 등).

## 반드시 지켜야 할 원칙 (요약 — 근거는 docs/01-decisions-log.md)

1. **LLM은 공고문 파싱에만 쓴다. 자격 판정(verdict)은 100% 결정론적 코드로만 한다.**
2. **verdict는 4상태다**: `ELIGIBLE` / `INELIGIBLE` / `NEEDS_INFO` / `NOT_OFFERED`.
   `NOT_OFFERED`(이 공고엔 해당 계층 자체가 없음)를 `INELIGIBLE`과 절대 섞지 말 것.
3. **score = 충족 필수조건 수 / 전체 필수조건 수.** "당첨 확률 예측"이 아니다 — ML로
   당첨 가능성을 추정하는 기능은 MVP 범위에서 명시적으로 제외되어 있다.
4. **등본에 이미 적힌 사실(세대주/세대원 여부, 1인가구 여부)은 Rule Engine이 추론하지
   않는다.** 프로필 입력값으로 그대로 받는다.
5. **소득과 자산은 "가구원수" 산정 기준이 계층마다, 심지어 같은 계층 안에서도 서로
   다르다.** 예: 청년(세대원)은 소득 판정 시 가구원수를 무조건 1로 고정하지만, 자산
   판정은 실제 가구원수를 그대로 쓴다 — 이 비대칭을 절대 하나로 합치지 말 것.
   (자세한 표는 docs/02-data-schema.md, 코드는 src/notices_data.py)

## 파일 구조

- `docs/00-project-overview.md` — 사업 배경, 시장조사 결론, MVP 타깃/범위
- `docs/01-decisions-log.md` — 설계 중 발견한 이슈와 해결 과정 전체 (가장 중요, 자주 참조)
- `docs/02-data-schema.md` — programs/notices/rules/reference_values/income_basis 스키마
- `docs/03-validation-methodology.md` — 테스트 프로필을 어떻게 설계했고 이 검증의 한계는
  무엇인지 (반드시 읽을 것 — "36/36 통과"가 의미하는 것과 의미하지 않는 것)
- `docs/04-open-items-and-next-steps.md` — 아직 안 끝난 것, 다음에 할 것
- `src/rule_engine.py` — 판정 엔진 본체 (HouseholdProfile, RuleCondition, evaluate())
- `src/notices_data.py` — 공고 3건의 실제 규칙 데이터
- `src/priority_scoring.py` — 우선공급 배점(verdict와 분리된 별도 점수)
- `src/profiles_data.py` — 테스트용 프로필 12개 + 수기 정답지
- `src/explainability.py` — EvaluationResult → 사용자용 근거 문구(Explanation) 변환
- `tests/` — pytest 스위트 (회귀 36 + 경계값 32 + 자녀가산 9 + 우선공급배점 5 +
  explainability 5 = 87개)
- `data/*.xlsx` — MVP0 설계 워크북 원본 (programs/notices/rules/reference_values/
  income_basis/profiles/match_matrix 시트 — 코드보다 사람이 보기 편한 원본)

## 테스트 실행

```bash
cd tests && python3 -m pytest -q
```

@docs/01-decisions-log.md
@docs/03-validation-methodology.md
