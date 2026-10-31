# 공개 화면 (Next.js) — v3 ④-4

LH·SH 공고 자격 판정 서비스의 공개 화면. **판정 로직은 없다** — 판정 API(`../api/main.py`)가 준 양식(`/form`)대로 그리고,
결과(`/evaluate`·`/match`·`/whatif`)를 보여 주기만 한다. PC 브라우저 화면을 먼저 만들고, 모바일 웹은 그다음 단계(2026-10-31 결정).

## 로컬에서 띄우기 (PC)

```bash
# 1) 판정 API (저장소 루트에서) — 로컬 시험은 운영 DB에 쓰지 않게 CCJ_STORE=off
pip install -r requirements-api.txt
CCJ_STORE=off python -m uvicorn api.main:app --port 8000        # PowerShell: $env:CCJ_STORE="off"; python -m uvicorn ...

# 2) 화면 (web/에서)
npm install
npm run dev                                                      # http://localhost:3000
```

API 주소는 `NEXT_PUBLIC_API_URL`(기본 `http://127.0.0.1:8000`). API는 `CCJ_CORS_ORIGINS`(기본 `http://localhost:3000`)의 화면만 받는다.
미등록 공고 자동 판정을 화면에서 보려면 API를 `CCJ_AUTO_JUDGE_PUBLIC=1`로 띄운다(공개 전 기본 꺼짐).

## 화면 점검

```bash
npx playwright install chromium   # 처음 한 번
npx playwright test               # API(8765)와 화면(3100)을 직접 띄워 PC 브라우저(1440×900)로 확인
```

## 구성

- `src/lib/api.ts` — API 호출과 응답 형식
- `src/components/ProfileForm.tsx` — `/form` 양식대로 입력란(모름 → null, 생년월일은 API가 공고일 기준 만 나이로)
- `src/components/ResultView.tsx` — 3상태 결과·원문 확인할 곳·조건별 근거·순위별 결과·공통 문구
- `src/components/MatchList.tsx` — 전 공고 결과(3상태 묶음, 접수 중 → 예정 → 마감 순, 공고 카드)
- `src/components/WhatIf.tsx` — 조건 하나만 부족한 공고(금액 한도)·시나리오 비교
- `src/app/page.tsx` — 공고 판정(PDF 올리기 / 목록에서 고르기 → 계층 → 입력 → 판정)
- `src/app/find/page.tsx` — 내 조건으로 공고 찾기(`/match/form` 양식 → `/match` → What-if). 내 조건 파일(ccj-profile/1) 저장·불러오기는
  브라우저 안에서만(서버에 보내는 것은 판정 요청뿐, 저장하지 않음)
