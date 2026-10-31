// 내 조건으로 공고 찾기 — 서버 양식(/match/form)대로 입력 → 전 공고 판정 → What-if. 화면 결과는 판정 API를 직접 부른 결과와 같아야 한다.
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const API = "http://127.0.0.1:8765";
const DAY = "2026-10-14"; // 그날 정오에 접수 중인 공고 5건(tests/test_d4_match.py와 같은 날)
const AT = `${DAY}T12:00:00+09:00`;

const field = (page: Page, name: string) => page.locator(`[data-field="${name}"]`);

async function fillSingle(page: Page) {
  await page.goto("/find");
  await field(page, "master.birth_date").locator("input").fill("1996-01-01");
  await field(page, "master.home_self").locator("select").selectOption("무주택");
  await field(page, "master.home_household").locator("select").selectOption("무주택");
  for (const [name, v] of [["income_household", "4000000"], ["income_self", "4000000"], ["assets_household", "50000000"],
    ["assets_self", "50000000"], ["car_household", "0"], ["car_self", "0"]])
    await field(page, `master.${name}`).locator("input").fill(v);
  await field(page, "residence_area").locator("select").selectOption("서울특별시");
}

async function saved(page: Page) {
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("profile-save").click()]);
  expect(download.suggestedFilename()).toBe("내조건.json");
  return JSON.parse(readFileSync((await download.path())!, "utf-8"));
}

test("전체 공고 판정 결과가 API /match와 같고, 기준일·보기를 바꾸면 다시 판정한다", async ({ page, request }) => {
  await fillSingle(page);
  const profile = await saved(page);
  expect(profile.master).toMatchObject({ birth_date: "1996-01-01", home_self: "무주택", income_household: 4000000, car_self: 0 });
  expect(profile.common).toMatchObject({ marital_status: "미혼", household_size: 1, residence_area: "서울특별시", house_head_status: null });

  await page.getByRole("button", { name: "전체 공고 판정" }).click();
  await expect(page.getByTestId("match-result")).toBeVisible();
  await page.getByLabel("기준일").fill(DAY);
  await expect(page.getByTestId("schedule-counts")).toContainText("2026-10-14 12:00");

  const want = await (await request.post(`${API}/match`, { data: { profile, at: AT, only_open: true } })).json();
  const c = (v: string) => String(want.counts[v] ?? 0);
  await expect(page.getByTestId("count-ELIGIBLE")).toHaveText(c("ELIGIBLE"));
  await expect(page.getByTestId("count-INELIGIBLE")).toHaveText(c("INELIGIBLE"));
  await expect(page.getByTestId("count-HOLD")).toHaveText(String((want.counts.NEEDS_INFO ?? 0) + (want.counts.MANUAL_REVIEW ?? 0)));
  await expect(page.getByTestId("schedule-counts")).toContainText("접수 중 5건");

  // 마감 포함으로 바꾸면 공고 전체
  await page.getByRole("radio", { name: "전체 공고(마감 포함)" }).check();
  const all = await (await request.post(`${API}/match`, { data: { profile, at: AT, only_open: false } })).json();
  await expect(page.getByTestId("count-INELIGIBLE")).toHaveText(String(all.counts.INELIGIBLE ?? 0));
  await expect(page.getByTestId("match-card").first()).toBeVisible();
  await expect(page.getByTestId("missing-inputs")).toBeVisible();
});

test("내 조건 파일로 저장한 것을 불러오면 입력란이 그대로 채워진다", async ({ page }) => {
  await fillSingle(page);
  await field(page, "marital_status").locator("select").selectOption("혼인중");
  await field(page, "marriage_date").locator("input").fill("2024-03-02");
  const profile = await saved(page);
  expect(profile.common).toMatchObject({ marital_status: "혼인중", marriage_date: "2024-03-02" });

  await page.reload();
  await expect(field(page, "master.birth_date").locator("input")).toHaveValue("");
  await page.getByTestId("profile-file").setInputFiles({
    name: "내조건.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(profile)),
  });
  await expect(page.getByTestId("profile-loaded")).toBeVisible();
  await expect(field(page, "master.birth_date").locator("input")).toHaveValue("1996-01-01");
  await expect(field(page, "marriage_date").locator("input")).toHaveValue("2024-03-02");
  await expect(field(page, "master.income_household").locator("input")).toHaveValue("4,000,000");
  await expect(field(page, "residence_area").locator("select")).toHaveValue("서울특별시");
  expect(await saved(page)).toEqual(profile);

  await page.getByTestId("profile-file").setInputFiles({
    name: "x.json", mimeType: "application/json", buffer: Buffer.from('{"schema":"other"}'),
  });
  await expect(page.getByRole("alert").filter({ hasText: "불러오지" })).toContainText("ccj-profile/1");
});

test("What-if: 조건 하나만 부족한 공고와 시나리오 비교가 API /whatif와 같다", async ({ page, request }) => {
  await fillSingle(page);
  const profile = await saved(page);
  await page.getByRole("button", { name: "전체 공고 판정" }).click();
  await page.getByRole("radio", { name: "전체 공고(마감 포함)" }).check();
  await expect(page.getByTestId("near-list")).toContainText("이하");

  await page.getByRole("button", { name: "시나리오로 비교" }).click();
  await page.getByRole("radio", { name: "세대를 분리하면" }).check();
  await page.getByRole("button", { name: "이 시나리오로 다시 판정" }).click();
  const want = await (await request.post(`${API}/whatif`, { data: { profile, scenario: "separate", only_open: false } })).json();
  await expect(page.getByTestId("whatif-result")).toContainText(`지금 ${want.before.ELIGIBLE}건 → ${want.after.ELIGIBLE}건 지원 가능`);
  if (want.gained.length) await expect(page.getByTestId("whatif-result")).toContainText(`새로 지원 가능 ${want.gained.length}건`);
});

test("추가 정보는 접혀 있고, 생년월일 없이 판정하면 안내한다", async ({ page }) => {
  await page.goto("/find");
  await expect(field(page, "student_status")).toBeHidden();
  await page.locator('[data-section="추가 자격 정보"] summary').click();
  await expect(field(page, "student_status")).toBeVisible();
  await page.getByRole("button", { name: "전체 공고 판정" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "생년월일" })).toBeVisible();
  await expect(page.getByTestId("match-result")).toHaveCount(0);
});
