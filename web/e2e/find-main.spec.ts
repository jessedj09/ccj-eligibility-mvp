// 청약 흥신소 주 흐름(2026-11-11) — 기본 조건 → 지금 모집 중인 공고 목록(판정 API /find). 화면 결과는 API를 직접 부른 결과와 같아야 한다.
// 수집 공고는 표본(tests/fixtures/live/find_rows.json — playwright.config의 CCJ_LIVE_FIXTURE)으로, 기준일은 ?at=2026-11-10.
import { expect, test, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8765";
const DAY = "2026-11-10";
const AT = `${DAY}T12:00:00+09:00`;
const field = (page: Page, name: string) => page.locator(`[data-field="${name}"]`);

async function fillYouth(page: Page) {
  await page.goto(`/find?at=${DAY}`);
  await field(page, "master.birth_date").locator("input").fill("1998-03-01");
  await field(page, "master.home_self").locator("select").selectOption("무주택");
  await field(page, "master.home_household").locator("select").selectOption("무주택");
  await field(page, "house_head_status").locator("select").selectOption("세대주");
  for (const [name, v] of [["income_household", "3000000"], ["assets_household", "50000000"], ["car_household", "0"]])
    await field(page, `master.${name}`).locator("input").fill(v);
  await field(page, "residence_area").locator("select").selectOption("서울특별시");
}

const PROFILE = {
  schema: "ccj-profile/1",
  master: { birth_date: "1998-03-01", home_self: "무주택", home_household: "무주택", income_household: 3000000, income_self: null,
    assets_household: 50000000, assets_self: null, car_household: 0, car_self: null },
  common: { marital_status: "미혼", household_size: 1, house_head_status: "세대주", residence_area: "서울특별시" },
};

test("기본 조건만으로 지금 모집 중인 공고를 묶음별로 보여 주고, 건수가 API /find와 같다", async ({ page, request }) => {
  await fillYouth(page);
  // 첫 화면은 기본 조건만 — 대학생·복지 자격 같은 추가 항목은 묻지 않는다
  await expect(field(page, "student_status")).toHaveCount(0);
  await page.getByRole("radio", { name: "전국" }).check();
  await page.getByTestId("find-run").click();
  await expect(page.getByTestId("find-list")).toBeVisible();

  const want = await (await request.post(`${API}/find`, { data: { profile: PROFILE, at: AT } })).json();
  for (const g of want.groups) await expect(page.getByTestId(`count-${g}`)).toHaveText(String(want.counts[g]));
  expect(want.counts.likely + want.counts.eligible).toBeGreaterThan(0);

  // 예비 판정 카드: 단서 붙은 '지원 가능' 또는 다른 묶음 + 근거 문장 + 공고문 올리기·분석 요청
  const preview = page.locator('[data-testid="find-card"][data-basis="preview"]').first();
  await expect(preview.getByTestId("card-basis")).toContainText("같은 사업 최근 공고");
  await expect(preview.getByTestId("card-upload")).toBeVisible();
  if (want.counts.likely) await expect(page.getByTestId("group-likely")).toContainText("지원 가능 (단, 공고문 내 지원자격 상세 확인 필요)");

  // 접힌 묶음(실제 공고문 확인필요·지원 어려움·판정 안 함)은 <details>
  await expect(page.getByTestId("group-unjudged")).toHaveJSProperty("tagName", "DETAILS");
  await expect(page.getByTestId("group-unjudged")).not.toHaveAttribute("open", "");
  if (want.counts.verify) await expect(page.getByTestId("group-verify")).toHaveJSProperty("tagName", "DETAILS");
});

test("분석 요청은 한 번 누르면 '요청했습니다'로 바뀌고, 공고문 올리기는 재판소로 공고 이름을 넘긴다", async ({ page }) => {
  await fillYouth(page);
  await page.getByRole("radio", { name: "전국" }).check();
  await page.getByTestId("find-run").click();
  const preview = page.locator('[data-testid="find-card"][data-basis="preview"]').first();
  await preview.getByTestId("card-request").click();
  await expect(preview.getByTestId("card-request")).toHaveText("분석 요청했습니다");
  await expect(preview.getByTestId("card-request")).toBeDisabled();
  await preview.getByTestId("card-upload").click();
  await expect(page).toHaveURL(/\/\?from=/);
  await expect(page.getByTestId("from-notice")).toContainText("공고문 PDF를 공식 공고 페이지에서 내려받아 올리면");
});

test("지역·임대/분양을 바꾸면 다시 찾고, 생년월일 없이 찾으면 안내한다", async ({ page, request }) => {
  await page.goto(`/find?at=${DAY}`);
  await page.getByTestId("find-run").click();
  await expect(page.getByRole("alert").filter({ hasText: "생년월일" })).toBeVisible();
  await fillYouth(page);
  await page.getByRole("radio", { name: "전국" }).check();
  await page.getByTestId("find-run").click();
  await expect(page.getByTestId("find-list")).toBeVisible();
  await page.getByRole("radio", { name: "분양", exact: true }).check();
  const want = await (await request.post(`${API}/find`, { data: { profile: PROFILE, at: AT, kind: "분양" } })).json();
  await expect(page.getByTestId("count-unjudged")).toHaveText(String(want.counts.unjudged));
  await expect(page.locator('[data-testid="find-card"]')).toHaveCount(want.items.length);
});

test("자세히(전체 조건·지난 공고·What-if)는 /find/all로 옮겼다", async ({ page }) => {
  await page.goto("/find");
  await page.getByTestId("find-all-link").click();
  await expect(page).toHaveURL(/\/find\/all$/);
  await expect(page.getByRole("button", { name: "전체 공고 판정" })).toBeVisible();
});

test("휴대폰: 목록이 가로로 넘치지 않고, 찾으면 목록으로 스크롤한다", async ({ page, isMobile }) => {
  test.skip(!isMobile, "휴대폰 화면 전용");
  await fillYouth(page);
  await page.getByRole("radio", { name: "전국" }).check();
  await page.getByTestId("find-run").click();
  await expect(page.getByTestId("find-list")).toBeInViewport();
  const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over).toBeLessThanOrEqual(1);
});
