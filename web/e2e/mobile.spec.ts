// 휴대폰 화면(1단 배치)과 서버 시동 안내. 판정 흐름 자체는 judge·find 점검이 PC·휴대폰 둘 다에서 확인한다.
import { expect, test, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8765";

async function noSideScroll(page: Page) {
  const [scroll, client] = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(scroll, "가로 스크롤이 생기면 안 된다").toBeLessThanOrEqual(client);
}

test("휴대폰: 공고 판정 — 가로 넘침 없이 1단으로 쌓이고, 판정하면 결과로 스크롤한다", async ({ page, isMobile }) => {
  test.skip(!isMobile, "휴대폰 화면 전용");
  await page.goto("/");
  await noSideScroll(page);
  await page.getByRole("button", { name: "목록에서 고르기" }).click();
  await page.getByTestId("notice-select").selectOption("N12");
  await page.getByRole("button", { name: "청년", exact: true }).click();
  // 입력란은 1열: 두 항목의 왼쪽 끝이 같다
  const a = await page.locator('[data-field="age"]').boundingBox();
  const b = await page.locator('[data-field="marital_status"]').boundingBox();
  expect(Math.abs(a!.x - b!.x)).toBeLessThan(2);
  await page.getByRole("radio", { name: "만 나이" }).check();
  await page.getByRole("spinbutton", { name: "만 나이" }).fill("50");
  await page.getByRole("button", { name: "판정하기" }).click();
  await expect(page.getByTestId("result-title")).toContainText("지원 불가");
  await expect(page.getByTestId("result-title")).toBeInViewport();
  await noSideScroll(page);
});

test("휴대폰: 공고 찾기 — 판정하면 결과로 스크롤하고, 결과·What-if도 가로로 넘치지 않는다", async ({ page, isMobile }) => {
  test.skip(!isMobile, "휴대폰 화면 전용");
  await page.goto("/find");
  await noSideScroll(page);
  await page.locator('[data-field="master.birth_date"] input').fill("1996-01-01");
  await page.locator('[data-field="master.income_household"] input').fill("4000000");
  await page.getByRole("button", { name: "전체 공고 판정" }).click();
  await expect(page.getByTestId("match-result")).toBeVisible();
  await expect(page.getByText("접수 상태", { exact: true })).toBeInViewport();
  await page.getByRole("radio", { name: "전체 공고(마감 포함)" }).check();
  await page.getByTestId("match-card").first().locator("summary").click();
  await page.getByRole("button", { name: "시나리오로 비교" }).click();
  await page.getByRole("radio", { name: "혼인신고를 하면" }).check();
  await noSideScroll(page);
});

test("서버가 늦게 깨어나면 '서버 시동 중' 안내(돌아가는 모래시계)를 보이고, 응답이 오면 감춘다", async ({ page }) => {
  // 잠든 서버를 흉내 낸다: 화면을 열 때 보내는 깨우기 요청(/health)을 4초 늦춘다
  await page.route(`${API}/health`, async (route) => {
    await new Promise((r) => setTimeout(r, 4000));
    await route.continue();
  });
  await page.goto("/");
  await expect(page.getByTestId("server-waking")).toContainText("서버 시동 중입니다. 잠시만 기다려주세요.");
  // 로딩 중임을 알리는 모래시계 — 돌아가는 애니메이션이 걸려 있다
  const anim = await page.getByTestId("hourglass").evaluate((el) => getComputedStyle(el).animationName);
  expect(anim).toBe("hourglass-turn");
  await expect(page.getByTestId("server-waking")).toHaveCount(0, { timeout: 15_000 });
  // 깨어난 뒤의 요청에는 안내하지 않는다
  await page.getByRole("button", { name: "목록에서 고르기" }).click();
  await page.getByTestId("notice-select").selectOption("N12");
  await expect(page.getByTestId("server-waking")).toHaveCount(0);
});

test("이용 안내: 판정 범위·한계·개인정보 처리를 보이고, 화면 아래에서 갈 수 있다", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "이용 안내·개인정보 처리" }).click();
  await expect(page.getByRole("heading", { name: "이용 안내" })).toBeVisible();
  await expect(page.getByText("입력한 조건(나이·소득·자산 등)은 저장하지 않습니다.")).toBeVisible();
  await expect(page.getByText("최종 자격은 공고 기관(LH·SH)의 서류 심사로 확정")).toBeVisible();
  await noSideScroll(page);
});


test("상단: 서비스 이름과 대표 메뉴(재판소·청약 흥신소), 내 조건 등록하기는 준비 중", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("청약 포청천 — 청약 지원자격 판정 AI");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("⚖️ 재판소");
  await page.getByRole("navigation", { name: "대표 메뉴" }).getByRole("link", { name: /청약 흥신소/ }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("📜 청약 흥신소");
  await expect(page.getByTestId("menu-profile")).toContainText("준비 중");
  await noSideScroll(page);
});
