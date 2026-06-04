// frontend/tests/admin/e2e/statistics-and-voting.spec.ts
//
// UI-only assertions for PR #51 (Statistik tab + Voting). These complement
// scripts/smoke/backend_e2e.py — the Python smoke locks the API contract;
// this spec locks the *visual* contract the API can't see:
//   - Statistik mounts as the 6th DocStepTab with all three subsections
//   - Anti-anchoring: vote counts stay HIDDEN until the viewer has voted
//   - Per-user border-stripe colour matches the vote cast (emerald / red)
//   - Toggle-to-revoked clears the stripe + counts (Decision 12 + 14)
//   - Auth gate: logged-out → /statistics redirects to the login page
//
// The app uses a HashRouter, so every route is addressed as `/#/…`. Auth is
// role-based: seeding sessionStorage `goldens.role="admin"` (plus the api
// token the curator client sends as `X-Auth-Token`) satisfies AdminShell's
// guard. On the Synthesise tab the QuestionList renders only after a box is
// clicked in the read-only preview iframe, so the voting tests click the
// seeded `data-source-box` to reveal the card before asserting.
//
// Required environment:
//   LOCAL_PDF_E2E=1                              opt-in
//   LOCAL_PDF_TEST_TOKEN=<token>                 backend X-Auth-Token
//   LOCAL_PDF_TEST_SLUG=<slug>                   seeded doc (see below)
//   LOCAL_PDF_API_BASE=http://localhost:8000     default if unset
//
// Seed a doc first — backend_e2e.py writes html.html plus a p1-b2 question
// the voting tests drive through the real box-click UX:
//
//   GOLDENS_API_TOKEN=$LOCAL_PDF_TEST_TOKEN \
//   LOCAL_PDF_API_BASE=$LOCAL_PDF_API_BASE \
//   .venv/bin/python scripts/smoke/backend_e2e.py --keep
//   # → capture the printed slug into LOCAL_PDF_TEST_SLUG

import { expect, test, type Page } from "@playwright/test";

const TOKEN = process.env.LOCAL_PDF_TEST_TOKEN ?? "";
const API_BASE = process.env.LOCAL_PDF_API_BASE ?? "http://localhost:8000";
const PROVIDED_SLUG = process.env.LOCAL_PDF_TEST_SLUG;

test.skip(
  process.env.LOCAL_PDF_E2E !== "1",
  "Set LOCAL_PDF_E2E=1 to run (requires backend + frontend + chromium + valid TOKEN)",
);
test.skip(!TOKEN, "LOCAL_PDF_TEST_TOKEN env var not set");
test.skip(
  !PROVIDED_SLUG,
  "LOCAL_PDF_TEST_SLUG env var not set — run backend smoke with --keep first",
);

// Matches the QuestionList vote-count line, e.g. "1 ✓ · 0 ✗".
const COUNTS = "text=/\\d+\\s*✓\\s*·\\s*\\d+\\s*✗/";

// ── Helpers ──────────────────────────────────────────────────────────────────

interface Target {
  slug: string;
  entryId: string;
  boxId: string;
}

// Seed the role-based auth AdminShell's guard checks. Token-mode (vs. the
// cookie flow) is what lets the curator client attach X-Auth-Token to the
// API calls these tests trigger.
async function seedAuth(page: Page): Promise<void> {
  await page.addInitScript((t) => {
    sessionStorage.setItem("goldens.api_token", t as string);
    sessionStorage.setItem("goldens.role", "admin");
    sessionStorage.setItem("goldens.name", "e2e-smoke");
  }, TOKEN);
}

// Resolve the first seeded question's entry + box key from /questions. The
// box key (e.g. "p1-b2") is the `data-source-box` the preview iframe exposes;
// the voting tests click it to reveal the QuestionList. Production code never
// round-trips through /questions for an ID it already knows — this is a
// smoke-only convenience.
async function firstQuestion(slug: string): Promise<Target> {
  const r = await fetch(`${API_BASE}/api/admin/docs/${slug}/questions`, {
    headers: { "X-Auth-Token": TOKEN },
  });
  if (!r.ok) {
    throw new Error(`failed to load questions for slug=${slug}: ${r.status} ${await r.text()}`);
  }
  const body: Record<string, Array<{ entry_id: string }>> = await r.json();
  for (const [boxId, qs] of Object.entries(body)) {
    if (qs.length > 0) return { slug, entryId: qs[0].entry_id, boxId };
  }
  throw new Error(`no questions for slug=${slug}`);
}

// Drop any vote a previous run left so each test starts from my_vote=null.
// A revoked POST is idempotent even when no prior vote exists.
async function clearVote(slug: string, entryId: string): Promise<void> {
  await fetch(`${API_BASE}/api/admin/docs/${slug}/questions/${entryId}/vote`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ action: "revoked" }),
  });
}

// Navigate to the Synthesise tab and reveal the seeded question's card by
// clicking its box in the read-only preview iframe. The QuestionList (and its
// vote buttons) mount only once `highlight` is set by that click.
async function openQuestionCard(page: Page, target: Target) {
  await page.goto(`/#/admin/doc/${target.slug}/synthesise`);
  await page
    .frameLocator('iframe[data-testid="synth-html-preview"]')
    .locator(`[data-source-box="${target.boxId}"]`)
    .click();
  const card = page.getByTestId(`question-${target.entryId}`);
  await expect(card).toBeVisible();
  return card;
}

// ── Tests ────────────────────────────────────────────────────────────────────

test.describe("Statistik route structure", () => {
  test("renders the 6th DocStepTab and all three subsections", async ({ page }) => {
    await seedAuth(page);
    await page.goto(`/#/admin/doc/${PROVIDED_SLUG}/statistics`);

    // DocStepTabs persistence — Statistik is the 6th tab.
    await expect(page.getByRole("tab")).toHaveCount(6);
    await expect(page.getByRole("tab", { name: /statistik/i })).toBeVisible();

    // Three section headings render — h2 by Decision 1.
    await expect(page.getByRole("heading", { name: "Extrahieren", level: 2 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Synthese", level: 2 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Provenienz", level: 2 })).toBeVisible();
  });

  test("auth gate redirects logged-out visitors to the login page", async ({ page }) => {
    await page.context().clearCookies();
    // No seedAuth — visit cold. AdminShell's role guard fires before any
    // react-query runs and redirects to the login route.
    await page.goto(`/#/admin/doc/${PROVIDED_SLUG}/statistics`);

    await expect(page).toHaveURL(/#\/login/);
    await expect(page.getByRole("heading", { name: "Anmeldung" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Extrahieren", level: 2 })).toHaveCount(0);
  });
});

test.describe("Voting UI on QuestionList", () => {
  test.beforeEach(async () => {
    // Spec contract is "starts with no vote" — clear any leftover state.
    const target = await firstQuestion(PROVIDED_SLUG!);
    await clearVote(target.slug, target.entryId);
  });

  test("anti-anchoring: counts hidden before vote, visible after", async ({ page }) => {
    await seedAuth(page);
    const target = await firstQuestion(PROVIDED_SLUG!);
    const card = await openQuestionCard(page, target);

    // Pre-vote: NO counts text, transparent left stripe.
    await expect(card.locator(COUNTS)).toHaveCount(0);
    const stripeBefore = await card.evaluate((el) => getComputedStyle(el).borderLeftColor);
    // emerald-500 = rgb(16,185,129); red-500 = rgb(239,68,68); transparent
    // computes to "rgba(0, 0, 0, 0)".
    expect(stripeBefore).toBe("rgba(0, 0, 0, 0)");

    // Click Einverstanden — anti-anchoring releases the counts.
    await card.getByRole("button", { name: /einverstanden/i }).click();

    await expect(card.locator(COUNTS)).toBeVisible({ timeout: 5000 });
    await expect
      .poll(async () => await card.evaluate((el) => getComputedStyle(el).borderLeftColor))
      .toBe("rgb(16, 185, 129)");
  });

  test("toggle-to-revoked: second click removes stripe + counts", async ({ page }) => {
    await seedAuth(page);
    const target = await firstQuestion(PROVIDED_SLUG!);
    const card = await openQuestionCard(page, target);
    const approve = card.getByRole("button", { name: /einverstanden/i });

    // First click → cast, counts visible.
    await approve.click();
    await expect(card.locator(COUNTS)).toBeVisible({ timeout: 5000 });

    // Second click on the same button → revoked.
    await approve.click();

    // Counts gone (anti-anchoring re-engages because my_vote is null again).
    await expect(card.locator(COUNTS)).toHaveCount(0, { timeout: 5000 });
    await expect
      .poll(async () => await card.evaluate((el) => getComputedStyle(el).borderLeftColor))
      .toBe("rgba(0, 0, 0, 0)");
  });

  test("disqualifizieren paints the stripe red", async ({ page }) => {
    await seedAuth(page);
    const target = await firstQuestion(PROVIDED_SLUG!);
    const card = await openQuestionCard(page, target);

    await card.getByRole("button", { name: /disqualifizieren/i }).click();

    await expect
      .poll(async () => await card.evaluate((el) => getComputedStyle(el).borderLeftColor))
      .toBe("rgb(239, 68, 68)");
    // Counts appear with the rejected side > 0.
    await expect(card.locator("text=/0\\s*✓\\s*·\\s*[1-9]\\d*\\s*✗/")).toBeVisible();
  });
});
