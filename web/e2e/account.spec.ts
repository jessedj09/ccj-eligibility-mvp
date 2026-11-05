// 회원 기능 화면 점검 — 회원가입(인증 코드) → 내 조건 저장 → 청약 흥신소에서 불러와 판정 → 로그아웃·로그인 → 탈퇴.
// API는 메모리 회원 저장소(CCJ_ACCOUNTS_MEMORY)·파일 메일(CCJ_MAIL_FILE)로 띄운다(playwright.config.ts) — 운영 DB·메일을 쓰지 않는다.
import fs from "node:fs";
import path from "node:path";
import { expect, test, type Page } from "@playwright/test";

const MAIL_FILE = path.join(__dirname, "..", "test-results", "mail.txt");   // playwright.config.ts의 MAIL_FILE과 같은 곳

async function codeFor(email: string): Promise<string> {
  for (let i = 0; i < 60; i++) {
    const text = fs.existsSync(MAIL_FILE) ? fs.readFileSync(MAIL_FILE, "utf-8") : "";
    const m = text.startsWith(`to=${email}`) ? text.match(/코드는 (\d{6})/) : null;
    if (m) return m[1];
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("인증 코드 메일이 오지 않았습니다");
}

async function signup(page: Page, email: string, password: string) {
  await page.goto("/signup");
  const form = page.getByTestId("signup-form");
  await form.getByLabel("이메일").fill(email);
  const pw = form.locator('input[type="password"]');
  await pw.nth(0).fill(password);
  await pw.nth(1).fill(password);
  const submit = form.getByRole("button", { name: "인증 코드 받기" });
  await expect(submit).toBeDisabled();                        // 필수 동의 전
  await form.getByLabel("모두 동의(필수)").check();
  await submit.click();
  await expect(page.getByTestId("signup-code")).toBeVisible();
  await page.getByLabel("인증 코드").fill(await codeFor(email));
  await page.getByRole("button", { name: "가입 완료" }).click();
  await expect(page).toHaveURL(/\/me$/);
}

test("회원가입부터 탈퇴까지 — 내 조건 저장·대표·흥신소에서 불러와 판정", async ({ page }, info) => {
  const email = `e2e-${info.project.name}-${Date.now()}@example.com`;
  const password = "abcd1234";
  await signup(page, email, password);
  await expect(page.getByRole("heading", { name: "내 조건 등록하기" })).toBeVisible();
  await expect(page.getByTestId("account-nav")).toContainText("로그아웃");

  // 새 조건 저장(모르는 항목은 '모름' 그대로 — 완성도로 보인다)
  await page.getByTestId("profile-new").click();
  await page.getByTestId("profile-alias").fill("나");
  await page.getByTestId("profile-editor").locator('[data-field="master.birth_date"] input').fill("1996-01-01");
  await page.getByTestId("profile-store").click();
  const list = page.getByTestId("profile-list");
  await expect(list).toContainText("나");
  await expect(list).toContainText("대표");
  await expect(list).toContainText("완성도");

  // 청약 흥신소에서 불러와 판정
  await list.getByRole("link", { name: "이 조건으로 공고 찾기" }).click();
  await expect(page).toHaveURL(/\/find\?profile=/);
  await expect(page.getByTestId("profile-loaded")).toContainText("'나' 조건으로 입력란을 채웠습니다");
  await page.getByRole("button", { name: "전체 공고 판정" }).click();
  await expect(page.getByTestId("schedule-counts")).toBeVisible();

  // 로그아웃 → 내 조건 등록하기는 로그인 화면으로 → 다시 로그인하면 돌아온다
  await page.getByTestId("account-nav").getByRole("button", { name: "로그아웃" }).click();
  await expect(page.getByTestId("account-nav")).toContainText("로그인");
  await page.goto("/me");
  await expect(page).toHaveURL(/\/login\?next=%2Fme|\/login\?next=\/me/);
  await page.getByTestId("login-form").getByLabel("이메일").fill(email);
  await page.getByTestId("login-form").getByLabel("비밀번호").fill("wrong999");
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page.getByText("이메일 또는 비밀번호가 맞지 않습니다.")).toBeVisible();
  await page.getByTestId("login-form").getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page).toHaveURL(/\/me$/);
  await expect(page.getByTestId("profile-list")).toContainText("나");

  // 탈퇴 — 즉시 지워지고 다시 로그인할 수 없다
  page.once("dialog", (d) => d.accept());
  await page.getByTestId("withdraw").click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/login");
  await page.getByTestId("login-form").getByLabel("이메일").fill(email);
  await page.getByTestId("login-form").getByLabel("비밀번호").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
  await expect(page.getByText("이메일 또는 비밀번호가 맞지 않습니다.")).toBeVisible();
});
