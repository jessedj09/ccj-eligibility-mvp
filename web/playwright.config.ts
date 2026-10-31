// 공개 화면 점검(④-4) — 판정 API와 Next.js 화면을 함께 띄워 실제 브라우저로 확인한다. PC 브라우저와 휴대폰 브라우저.
// API는 공유 저장소를 쓰지 않는다(CCJ_STORE=off — 운영 DB에 쓰지 않게).
import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8765;
const WEB_PORT = 3100;
const python = process.env.PYTHON || "python";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${WEB_PORT}`,
    viewport: { width: 1440, height: 900 },
    locale: "ko-KR",
    timezoneId: "Asia/Seoul",
    trace: "retain-on-failure",
  },
  // PC 브라우저(1440×900)와 휴대폰 브라우저(Pixel 7, 412×915 — 같은 Chromium) 둘 다에서 같은 점검을 돌린다
  projects: [
    { name: "pc-chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
  webServer: [
    {
      command: `${python} -m uvicorn api.main:app --port ${API_PORT}`,
      cwd: "..",
      url: `http://127.0.0.1:${API_PORT}/health`,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
      env: {
        CCJ_STORE: "off",
        CCJ_CORS_ORIGINS: `http://127.0.0.1:${WEB_PORT},http://localhost:${WEB_PORT}`,
        PYTHONIOENCODING: "utf-8",
      },
    },
    {
      command: `npm run build && npx next start -p ${WEB_PORT}`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      timeout: 300_000,
      reuseExistingServer: !process.env.CI,
      env: { NEXT_PUBLIC_API_URL: `http://127.0.0.1:${API_PORT}` },
    },
  ],
});
