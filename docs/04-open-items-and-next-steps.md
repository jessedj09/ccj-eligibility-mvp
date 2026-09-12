# 04. 열린 항목 및 다음 단계

## 진행 중이던 작업 (이 리포지토리를 넘겨받는 시점 기준)

✅ **Explainability 레이어** — `EvaluationResult`를 사용자에게 보여줄 자연어 근거
문구로 변환하는 계층. `src/explainability.py`의 `explain()`으로 구현 완료
(테스트: `tests/test_explainability.py`, 5개, 전체 87개 통과).
- `notices_data.py`의 모든 `RuleCondition`에 `note`(사람이 읽을 한 줄 설명)를 채움.
- `explain(result, notice) -> Explanation` — verdict를 재계산하지 않고 이미 나온
  matched/failed/unknown rule_id를 note+source_ref로 옮기기만 하는 순수 템플릿.
- 다음 단계 후보: 이 `Explanation`을 실제 사용자 화면(UI) 또는 API 응답으로
  렌더링하는 부분은 아직 없음 — 지금은 구조화된 dataclass까지만.

## 사람 검증 없이 진행 가능하다고 합의했던 순서 (일부만 완료)

1. ✅ 경계값(boundary) 자동 테스트 — 완료 (`tests/test_boundaries.py`)
2. LH 공식 자가진단 도구와 대조 (외부 독립 검증) — **미착수**, 접근 가능 여부(로그인/
   공인인증 필요 여부)부터 확인 필요
3. ✅ 미구현 영역 채우기(자녀가산, 우선공급 배점) — 완료 (`test_child_bonus.py`,
   `priority_scoring.py`)
4. 이상치(adversarial) 입력 테스트 — **미착수** (음수 소득, 모순된 입력 등)
5. ✅ 자동 회귀테스트로 전환 — 완료 (pytest 82개)

## 그 다음 예정이었던 것

- Explainability 레이어 (진행 예정)
- 나머지 17건 공고로 스키마 확장 (v0.1 문서의 MVP0 목표: 총 20건)
- N3 우선배정/우선공급 배점표 관련 잔여 불확실성(`docs/01-decisions-log.md` 7번)을
  LH 청약플러스 또는 고객센터로 재확인

## 이 리포지토리 밖의 더 큰 그림 (v0.1 기획 문서 기준, 아직 착수 안 함)

- Progressive Profiling UI (Level 1/2/3 단계적 입력)
- 관리자 검수 화면 (Rule 상태: DRAFT → REVIEWED → PUBLISHED → RETIRED)
- 데이터 자동수집 파이프라인 (지금은 공고 3건 전부 사람이 PDF를 읽고 수동 구조화함)
- B2B API (Eligibility Engine을 은행/카드/통신사에 공급하는 모델)
