# 주거·복지 Eligibility 플랫폼 — MVP0.1

정부 주거·복지 혜택(LH 행복주택 등)을 사용자 프로필과 대조해 "신청 가능/불가능/추가확인
필요"를 근거와 함께 자동 판정하는 서비스. 핵심 자산은 LLM이 아니라 **결정론적 Rule
Engine**이다. 전체 설계 배경과 원칙은 [CLAUDE.md](CLAUDE.md)를 먼저 읽을 것.

## 설치

```bash
pip install -r requirements.txt
```

의존성 재현 버전(로컬 검증 환경 기준):
- Python 3.13.5
- pytest >= 8.0
- streamlit >= 1.38

## 앱 실행 (Streamlit 데모 UI)

```bash
streamlit run app.py
```

`app.py`는 순수 렌더링 레이어다 — 판정 로직은 전혀 갖지 않고 `src/rule_engine.py`
(`evaluate`, `validate_profile`)와 `src/explainability.py`(`explain`)를 그대로 호출한다.

## 테스트 실행

```bash
cd tests
python -m pytest -q
```

- 회귀(match_matrix 대조) 36 + 경계값 32 + 자녀가산 9 + 우선공급배점 5 + explainability 6 +
  MVP0.1 재현/수정 28 + MVP0.2 수동검토 34 + MVP0.3 자녀 수 계산 22 = **총 172개**, 모두 통과해야 한다.
- 테스트가 검증하는 것과 검증하지 못하는 것의 차이는
  [docs/03-validation-methodology.md](docs/03-validation-methodology.md)를 반드시 읽을 것.

## 실행 기준: `src/` vs `mvp0/`

- **`src/` + `tests/`가 유일한 실행 기준이다.** `app.py`와 모든 테스트는 `src/`만 import한다.
- `mvp0/`는 초기 검증 단계의 스냅샷으로, MVP0.1 개정을 반영하지 않은 옛 코드다. 참고용으로만
  남겨두었으며 실행/수정 대상이 아니다(`mvp0/README.md` 참조).

## 지원 범위

- 3개 LH 행복주택 공고(N1 서울공릉/N2 서울관악봉천/N3 서울번동3), 4개 계층(대학생/청년/
  신혼부부/한부모)의 **필수조건** 충족 여부를 5상태(`ELIGIBLE`/`INELIGIBLE`/`NEEDS_INFO`/
  `MANUAL_REVIEW`/`NOT_OFFERED`)로 판정한다. `NEEDS_INFO`는 정보를 더 입력하면 해결되고,
  `MANUAL_REVIEW`는 원문 해석이 갈리거나 자기신고로만 처리하는 항목이라 정보를 더 입력해도
  해결되지 않는다(LH 재확인·사람 검토 필요).
- 판정 근거(원문 페이지, 조건 설명)를 계층별로 보여주는 Explainability 레이어와 Streamlit
  데모 화면을 제공한다.
- 미입력(모름)과 실제 0원/0건을 구분하고, 자료형·범위·모순 입력은 `validate_profile()`로
  사전 검증한다(예외 없이 사용자에게 오류 메시지로 반환).

## 지원하지 않는 범위 / 알려진 한계

자세한 표는 [docs/rule-coverage-matrix.md](docs/rule-coverage-matrix.md)를 참조. 요약:

- **서류심사·경쟁 시 선정(순위·추첨·배점)·최종 당첨 여부는 계산하지 않는다.** 우선공급
  배점(`src/priority_scoring.py`)은 verdict와 분리된 별도 점수로만 제공된다.
- **청년계층 "사회초년생" 세부요건**(소득활동기간 5년 이내 등 3가지 경로의 서류 증빙)은
  자기신고 사실로만 처리하며 세부 증빙을 검증하지 않는다.
- **원문 표에 없는 조합**(대학생·청년 2인 가구 + 출생자녀 등)은 임의로 통과/탈락시키지 않고
  `MANUAL_REVIEW`로 표시한다(원문 대조표 §3, LH 질의서 `docs/lh-inquiry-questions.md`).
- **출생자녀 가산 대상 자녀 수**는 자녀별 생년월일로 엔진이 계산한다(기준일 이후 출생 시 기존
  미성년 자녀 합산, 최대 2명). 단 "세대별 주민등록표에 등재된 자녀만 입력"은 사용자 책임이다.
- **사람(도메인 전문가)이나 LH 공식 자가진단 도구를 통한 독립 검증은 아직 수행하지 않았다.**
  이 저장소의 테스트가 보장하는 것은 "손으로 계산한 정답지와 코드가 일치하는지"뿐이며, 공고문
  규칙 자체를 잘못 이해했을 가능성은 이 테스트로 잡아낼 수 없다
  ([docs/03-validation-methodology.md](docs/03-validation-methodology.md) 참조).
- 그 외 세부 스코프 제한(예비신혼부부 세대 무주택 단순화, 주거약자용 서브타입 미코드화 등)은
  [docs/rule-coverage-matrix.md](docs/rule-coverage-matrix.md) §4에 전부 나열되어 있다.

## 회귀 테스트 자동 실행

이 저장소에는 CI 설정이 없다(로컬 실행만 지원). 커밋 전 최소한
`cd tests && python -m pytest -q`를 직접 실행해 전체 통과를 확인할 것.

## 문서 구조

- [CLAUDE.md](CLAUDE.md) — 프로젝트 메모리(무엇이 어디 있는지, 절대 어기면 안 되는 원칙)
- [docs/00-project-overview.md](docs/00-project-overview.md) — 사업 배경, MVP 범위
- [docs/01-decisions-log.md](docs/01-decisions-log.md) — 설계 결정 로그
- [docs/02-data-schema.md](docs/02-data-schema.md) — 데이터 스키마
- [docs/03-validation-methodology.md](docs/03-validation-methodology.md) — 검증 방법론과 한계
- [docs/04-open-items-and-next-steps.md](docs/04-open-items-and-next-steps.md) — 다음 단계
- [docs/rule-coverage-matrix.md](docs/rule-coverage-matrix.md) — 원문·구현 대조표(MANUAL_REVIEW 쟁점 포함)
- [docs/lh-inquiry-questions.md](docs/lh-inquiry-questions.md) — LH 재확인 질의 목록과 답변 기록
- [docs/independent-validation-worksheet.md](docs/independent-validation-worksheet.md) — 독립 검증 워크시트
