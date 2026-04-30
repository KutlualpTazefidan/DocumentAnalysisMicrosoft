import { test, expect } from "@playwright/test";

const TOKEN = process.env.GOLDENS_API_TOKEN ?? "";

test.skip(!TOKEN, "GOLDENS_API_TOKEN env var not set; skipping E2E");

test("login + walk + add question + dry-run synthesise", async ({ page }) => {
  await page.goto("/");
  // Should redirect to login
  await expect(page).toHaveURL(/\/login$/);

  // Login
  await page.getByLabel(/api-token/i).fill(TOKEN);
  await page.getByRole("button", { name: /einloggen/i }).click();

  // Docs index
  await expect(page.getByText(/dokumente/i)).toBeVisible();
  await page.getByRole("link", { name: /smoke-test-tragkorb/i }).click();

  // Doc elements page — element-walk
  const sidebar = page.locator('[role="navigation"]').or(page.locator("aside"));
  await expect(sidebar).toBeVisible();

  // Add a question to the first element
  await page.getByLabel(/neue frage/i).fill("E2E test question");
  await page.getByRole("button", { name: /speichern/i }).click();
  await expect(page.locator("text=gespeichert")).toBeVisible({ timeout: 3000 });

  // Synthesise dry-run
  await page.goto("/#/docs/smoke-test-tragkorb/synthesise");
  await page.getByRole("button", { name: /synthesise starten/i }).click();
  await expect(page.locator("text=Complete")).toBeVisible({ timeout: 60_000 });
});
