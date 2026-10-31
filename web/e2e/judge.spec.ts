// 공고 판정 화면 — 업로드·목록 선택 → 계층 → 서버가 준 양식 → 판정. 화면의 결과는 판정 API를 직접 부른 결과와 같아야 한다.
import { expect, test, type Page } from "@playwright/test";
import { createHash } from "node:crypto";
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(__dirname, "..", "..");
const API = "http://127.0.0.1:8765";

/** 등록 공고 원문 PDF — 규칙 파일의 원문 지문(sha256)으로 sample_lh·sample_sh에서 찾는다(파일 이름에 한글이 있어 이름으로 찾지 않음). */
function sourcePdf(nid: string): string {
  const sha = JSON.parse(readFileSync(path.join(ROOT, "rules", "notices", `${nid}.json`), "utf-8")).source.sha256;
  for (const dir of ["sample_lh", "sample_sh"]) {
    for (const name of readdirSync(path.join(ROOT, dir))) {
      if (!name.toLowerCase().endsWith(".pdf")) continue;
      const p = path.join(ROOT, dir, name);
      if (createHash("sha256").update(readFileSync(p)).digest("hex") === sha) return p;
    }
  }
  throw new Error(`${nid} 원문 PDF를 찾지 못함`);
}

const GROUP: Record<string, string> = {
  ELIGIBLE: "지원 가능", INELIGIBLE: "지원 불가", NEEDS_INFO: "보류", MANUAL_REVIEW: "보류", NOT_OFFERED: "해당 없음",
};

async function fillAmount(page: Page, name: string, value: string) {
  await page.locator(`[data-field="${name}"] input`).first().fill(value);
}

test("등록 공고 PDF를 올리면 검증된 규칙으로 판정하고, 결과가 API 판정과 같다", async ({ page, request }) => {
  await page.goto("/");
  await page.getByTestId("pdf-input").setInputFiles(sourcePdf("N12"));
  await expect(page.getByTestId("ident")).toContainText("등록 공고 N12");
  await page.getByRole("button", { name: "청년", exact: true }).click();
  await expect(page.locator('[data-field="age"]')).toBeVisible();
  // 서버 양식대로: 청년 계층에 없는 항목(혼인신고일·대학 소재지)은 묻지 않는다
  await expect(page.locator('[data-field="marriage_date"]')).toHaveCount(0);
  await expect(page.locator('[data-field="school_area"]')).toHaveCount(0);

  await page.getByRole("textbox", { name: "생년월일" }).fill("1999-05-01");
  await fillAmount(page, "monthly_income", "2500000");
  await fillAmount(page, "total_assets", "30000000");
  await page.locator('[data-field="car_value"] input').first().fill("0");
  await page.getByRole("button", { name: "판정하기" }).click();
  await expect(page.getByTestId("result")).toBeVisible();

  const direct = await request.post(`${API}/evaluate`, {
    data: { notice_id: "N12", layer: "청년", profile: {
      birth_date: "1999-05-01", marital_status: "미혼", home_ownership: "무주택", household_size: 1, dual_income: false,
      children_birth_dates: [], monthly_income: 2500000, total_assets: 30000000, car_value: 0, has_subscription_account: false,
    } },
  });
  const want = await direct.json();
  await expect(page.getByTestId("result-title")).toContainText(GROUP[want.verdict]);
  await expect(page.getByTestId("result")).toContainText(want.common_note);
});

test("목록에서 공고를 고르고, 나이 기준을 넘기면 지원 불가와 근거 쪽이 보인다", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "목록에서 고르기" }).click();
  await page.getByTestId("notice-select").selectOption("N12");
  await page.getByRole("button", { name: "청년", exact: true }).click();
  await page.getByRole("radio", { name: "만 나이" }).check();
  await page.getByRole("spinbutton", { name: "만 나이" }).fill("50");
  await page.getByRole("button", { name: "판정하기" }).click();
  await expect(page.getByTestId("result-title")).toContainText("지원 불가");
  await expect(page.getByTestId("result-title")).toBeInViewport();   // 긴 입력란 아래에 생긴 결과로 스크롤(PC·휴대폰)
  await expect(page.getByTestId("result")).toContainText("충족하지 못한 조건");
  await expect(page.getByTestId("result")).toContainText("공고문 p.");
});

test("혼인 상태를 '혼인중'으로 바꾸면 혼인신고일을 묻는다(서버 양식의 조건부 항목)", async ({ page, request }) => {
  const notices = (await (await request.get(`${API}/notices`)).json()).notices as { notice_id: string; layers: string[] }[];
  let target: { nid: string; layer: string } | null = null;
  for (const n of notices) {
    for (const layer of n.layers) {
      const form = await (await request.get(`${API}/form`, { params: { notice_id: n.notice_id, layer } })).json();
      if (form.fields.some((f: { name: string }) => f.name === "marriage_date")) target = { nid: n.notice_id, layer };
      if (target) break;
    }
    if (target) break;
  }
  expect(target).not.toBeNull();
  await page.goto("/");
  await page.getByRole("button", { name: "목록에서 고르기" }).click();
  await page.getByTestId("notice-select").selectOption(target!.nid);
  await page.getByRole("button", { name: target!.layer, exact: true }).click();
  await expect(page.locator('[data-field="marriage_date"]')).toHaveCount(0);
  await page.locator('[data-field="marital_status"] select').selectOption("혼인중");
  await expect(page.locator('[data-field="marriage_date"]')).toBeVisible();
});

test("PDF가 아니면 오류를 보이고, 판정할 수 없는 상태로 남는다", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("pdf-input").setInputFiles({ name: "memo.pdf", mimeType: "application/pdf", buffer: Buffer.from("hello") });
  await expect(page.getByRole("alert").filter({ hasText: "PDF" })).toContainText("PDF 파일이 아닙니다");
  await expect(page.getByRole("button", { name: "판정하기" })).toHaveCount(0);
});
