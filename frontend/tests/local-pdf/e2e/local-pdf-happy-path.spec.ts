// frontend/tests/local-pdf/e2e/local-pdf-happy-path.spec.ts
import { expect, test } from "@playwright/test";
import { resolve } from "node:path";

const TOKEN = process.env.LOCAL_PDF_TEST_TOKEN ?? "tok-e2e";
const FRONTEND = process.env.LOCAL_PDF_FRONTEND ?? "http://127.0.0.1:5173";

// Skip unless the caller has explicitly opted in by setting LOCAL_PDF_E2E=1.
// Real runs require: backend running (`query-eval segment serve --port 8001`)
// and frontend dev server (`npm run dev`). Browsers must be installed via
// `npx playwright install chromium`.
test.skip(
  process.env.LOCAL_PDF_E2E !== "1",
  "Set LOCAL_PDF_E2E=1 to run (requires backend + frontend + chromium)"
);

test.describe("local-pdf happy path", () => {
  test("upload → segment → edit → extract → export", async ({ page }) => {
    await page.addInitScript((t) => sessionStorage.setItem("auth-token", t), TOKEN);
    await page.goto(`${FRONTEND}/#/local-pdf/inbox`);

    // Upload a small fixture PDF
    const pdf = resolve("frontend/tests/local-pdf/e2e/fixtures/small.pdf");
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(pdf);
    await expect(page.getByText("uploaded")).toBeVisible({ timeout: 10_000 });

    // Click into the doc
    await page.getByRole("link", { name: /^start$/i }).first().click();
    await expect(page.getByRole("button", { name: /run segmentation/i })).toBeVisible();
    await page.getByRole("button", { name: /run segmentation/i }).click();
    await expect(page.getByText(/segmented/i)).toBeVisible({ timeout: 30_000 });

    // Press 'h' to set selected box to heading
    await page.locator('[data-testid^="box-"]').first().click();
    await page.keyboard.press("h");

    // Run extraction
    await page.getByRole("button", { name: /run extraction/i }).click();
    await expect(page.getByText(/extracted/i)).toBeVisible({ timeout: 60_000 });

    // Export
    await page.getByRole("button", { name: /export/i }).click();
    await expect(page.getByText(/exported sourceelements/i)).toBeVisible({ timeout: 10_000 });
  });
});
