# 08. 새 공고 등록 절차 (내부 운영용)

새 LH·SH 공고문을 서비스에 등록하는 절차다. 판정은 지금처럼 **검증을 마친 규칙 데이터로만** 한다 —
도구(`tools/notice_intake.py`)는 규칙을 만드는 사람(또는 Claude)이 원문에서 찾을 것을 쪽 번호와 함께 모아 줄 뿐이고,
판정을 하거나 규칙을 자동으로 확정하지 않는다.

## 1. 공고문 넣기

- LH 공고 → `sample_lh/`, SH 공고 → `sample_sh/`. 파일 이름은 바꾸지 않아도 된다(데이터는 sha256으로 원문을 묶는다).
- 정정 공고가 있으면 정정본을 쓴다(원문 대조 기준이 된다).

## 2. 후보 보고서 만들기

```bash
python tools/notice_intake.py "sample_lh/새공고.pdf" --out docs/notice-analysis/새공고-intake.md
```

보고서에 나오는 것(모두 후보 — 원문 쪽을 열어 확인할 것):

| 절 | 내용 | 쓰는 곳 |
|---|---|---|
| 1. 기본 | 이미 등록된 공고인지, 발행 기관·사업 유형 추정, 같은 사업의 등록 공고와 생성 스크립트 | 어떤 생성 스크립트에 넣을지 |
| 2. 공고일 | 공고일 후보와 원문 | `announcement_date` |
| 3. 접수기간 | 청약 접수기간 후보(✅ = 앞 문맥에 청약·신청·접수), `schedules.json` 초안 | `rules/schedules.json` |
| 4. 소득 기준표 | 등록된 기준표와 같은 숫자가 있는 쪽 — 같으면 `cited_pages`에 추가, 다르면 결정표에 직접 | `rules/reference/income_standard*.json` |
| 5. 기준일 | "…이후 출생", "혼인신고일이 '19.10.1.~" 같은 날짜 리터럴 — SH는 공고일−N년의 **다음 날**이므로 원문 날짜를 그대로 쓴다 | 조건의 `date` |
| 6. 키워드 | 계층·주택형·순위·주거약자 등이 나오는 쪽 | 계층 구성 파악 |
| 7. 체크리스트 | 아래 3절과 같다 | |

등록된 26건으로 시험한 결과: 접수기간 29개·공고일 26개·사업 유형 26개·기준일 리터럴 30개를 모두 후보에 올렸다
(`tests/test_e1_intake.py`). 새 사업 유형이나 처음 보는 표기는 놓칠 수 있으니 후보가 비면 원문을 직접 찾는다.

### 2-1. 자동 추출 초안 (`--draft`, A1 — 2026-10-27)

```bash
python tools/notice_intake.py "sample_lh/새공고.pdf" --draft --out docs/notice-analysis/새공고-intake.md
python tools/notice_intake.py "sample_lh/새공고.pdf" --draft --save-draft 초안.json   # 초안 규칙도 저장(두 번째 시험용)
```

보고서 8절에 P1 추출기(`src/draft.py` → `tools/sheet_extract.py`, **AI 없음**)가 만든 초안이 붙는다.

| 절 | 내용 | 할 일 |
|---|---|---|
| 상태 | ✅ 규칙을 만듦 / ⛔ 핵심 빈칸 보류 / ⛔ 사업 유형 모름 | ⛔면 그 값을 원문에서 직접 찾는다 |
| 8-1 채운 빈칸 | 공고일·기준일·문장 등 — 원문에 **글자로 있는 값만**, 쪽 번호와 찾은 방법 | 쪽을 열어 한 번 본다 |
| 8-2 보류된 빈칸 | 못 채운 것과 이유(핵심 = 판정에 직접 쓰임) | 원문에서 찾아 8-4 항목에 넣는다 |
| 8-3 규칙을 만들어 본 결과 | 찾지 못한 인용문·기준표 연도가 다른 조건·규칙에 없는 제한 문구 | 문장 고치기 / 새 연도 기준표 / 조건 추가 |
| 8-4 생성 스크립트 항목 | 그대로 붙여 넣을 PLAN 항목(행복주택은 TARGETS + 추가 계층·주거약자 PLAN) | 제목·notes를 원문대로 채운다 |
| 8-5 index.json 항목 | 공고 분석 목록에 넣을 키·파일·sha256 | 그대로 넣는다 |

합격 5개 사업(청년매입·LH 신혼·든든전세·장기전세·장기전세2)은 보통 보류 0이다 — 8-4를 붙여 넣고 아래 체크리스트를 진행하면 된다.
등록 5건으로 시험: 8-4 항목을 그대로 넣어 만든 규칙이 원문 대조를 모두 통과하고 등록 규칙과 같은 조건을 갖는다(`tests/test_a_stage.py`).
**두 번째 시험(B2)**: 새 공고는 정식 등록 **전에** `--save-draft`로 초안 규칙을 저장해 두고, 등록 후 같은 입력으로 판정을 비교한다.

## 3. 등록 체크리스트

1. **공고 분석** `docs/notice-analysis/<키>.md` + `index.json`에 파일·sha256 추가 — 계층·소득·자산·기준일·순위 구조를 원문 쪽과 함께
2. **규칙 데이터** `rules/notices/N<번호>.json` — 같은 사업이면 보고서가 알려 준 생성 스크립트(`tools/gen_*.py`)에 공고를 추가해 만든다.
   생성 스크립트는 재실행 안전해야 한다(`git status rules/`가 의도한 파일만 바뀌는지 확인).
3. **소득 기준표** — 같은 기준표면 `cited_pages`(필요하면 `required_by_notice`)에 추가, 다른 연도·사업이면 결정표에 직접
4. **접수기간** `rules/schedules.json` — 보고서 초안에서 라벨(인터넷 청약·순위별 등)과 기간 수를 원문대로 고친다
5. **골든** `tests/golden_cases.py` — `DATES`(손계산 기준일 — 엔진 함수로 계산하지 않는다), `GROUPS`(**맨 뒤에** 추가 → 기존 그룹 불변),
   필요하면 `PROGRAM_OF`·`REGION_FIELDS_BY_LAYER`
6. **새 사업 유형이면** `rules/reference/input_scope.json`(주택 소유·소득을 본인/세대 중 무엇으로 보는지)과 화면 질문
7. **확인**
   ```bash
   python tools/verify_sources.py        # 원문 대조 불일치 0
   python tools/regen_golden.py          # 새 그룹만 추가되고 기존 그룹은 그대로인지 확인
   python -m pytest -q
   python tools/ui_smoke.py
   python tools/notice_intake.py --audit # 등록 누락 0
   ```
8. **문서** — `docs/07-notice-generalization.md` 결과 절, CLAUDE.md·README의 공고 수

`--audit`는 등록된 공고마다 원문 PDF·공고 분석·접수기간·골든 기준일과 그룹(모든 계층)·입력 범위 규칙·소득표 대조가 다 있는지 본다.
pytest(`test_audit_is_clean_now`)가 같은 점검을 하므로 하나라도 빠뜨리면 CI가 실패한다.
