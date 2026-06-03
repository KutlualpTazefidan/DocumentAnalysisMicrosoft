// frontend/tests/admin/e2e/statistics-and-voting.spec.ts
//
// UI-only assertions for PR #51 (Statistik tab + Voting):
//   - Statistics route mounts with DocStepTabs persistent
//   - All 3 sections (Extrahieren / Synthese / Provenienz) render headings
//   - Anti-anchoring: vote counts are HIDDEN when the viewer has not voted
//   - Toggle-to-revoked: clicking the cast vote a second time removes the
//     stripe + counts (Decision 12 + 14 of the spec)
//   - Per-user border-stripe color matches the vote cast
//   - Auth gate: logout → /statistics → "Bitte zuerst anmelden."
//
// These complement scripts/smoke/backend_e2e.py — the Python smoke locks the
// API contract; this spec locks the visual contract.
//
// Required environment:
//   LOCAL_PDF_E2E=1                         opt-in (mirrors the existing spec)
//   LOCAL_PDF_TEST_TOKEN=<token>            backend X-Auth-Token (admin equiv)
//   LOCAL_PDF_API_BASE=http://localhost:8000  default if unset
//
// Required services:
//   - backend (uvicorn local_pdf.api.app:create_app --factory)
//   - frontend dev server on 5173 (npm run dev) — auto-started by playwright config
//
// On run:
//   POST seeds an isolated slug (smoke-ui-<timestamp>) via the backend's
//   data_root. cleanup happens in afterAll.

import { expect, test } from "@playwright/test";

const TOKEN = process.env.LOCAL_PDF_TEST_TOKEN ?? "";
const API_BASE = process.env.LOCAL_PDF_API_BASE ?? "http://localhost:8000";

test.skip(
  process.env.LOCAL_PDF_E2E !== "1",
  "Set LOCAL_PDF_E2E=1 to run (requires backend + frontend + chromium + valid TOKEN)",
);

test.skip(!TOKEN, "LOCAL_PDF_TEST_TOKEN env var not set");

// ── Seeding helpers ────────────────────────────────────────────────────────

interface SeedResult {
  slug: string;
  entryId: string;
}

// Mirror of scripts/smoke/backend_e2e.py _seed_doc — we use the events
// log directly by POST-ing through a thin seed route. If the backend
// exposes no seed endpoint (it does not — we go through the regular
// vote endpoint plus a minimal events.jsonl write via the file system,
// which is not reachable from the browser). Instead this spec ASSUMES
// the caller seeded a doc beforehand:
//
//   cd /path/to/repo
//   LOCAL_PDF_API_BASE=http://localhost:8000 \
//   GOLDENS_API_TOKEN=$LOCAL_PDF_TEST_TOKEN \
//   LOCAL_PDF_DATA_ROOT=<your data root> \
//   .venv/bin/python scripts/smoke/backend_e2e.py --keep
//
// then captures the printed slug into LOCAL_PDF_TEST_SLUG. The slug must
// have at least one question for the voting tests to address.

const PROVIDED_SLUG = process.env.LOCAL_PDF_TEST_SLUG;

test.skip(
  !PROVIDED_SLUG,
  "LOCAL_PDF_TEST_SLUG env var not set — run backend smoke with --keep first",
);

// Fetch the first question's entry_id from the provided slug so vote
// assertions address a real entry. This is a smoke-only helper — production
// code never round-trips through `/questions` for an ID it already knows.
async function firstQuestion(slug: string): Promise<SeedResult> {
  const r = await fetch(`${API_BASE}/api/admin/docs/${slug}/questions`, {
    headers: { "X-Auth-Token": TOKEN },
  });
  if (!r.ok) {
    throw new Error(`failed to load questions for slug=${slug}: ${r.status} ${await r.text()}`);
  }
  const body: Record<string, Array<{ entry_id: string }>> = await r.json();
  for (const qs of Object.values(body)) {
    if (qs.length > 0) return { slug, entryId: qs[0].entry_id };
  }
  throw new Error(`no questions for slug=${slug}`);
}

// Drop any vote events the previous run may have left so the spec starts
// from a clean (no my_vote) state. Implemented as a POST revoked +
// expected behaviour even when no prior vote exists.
async function clearVote(slug: string, entryId: string): Promise<void> {
  await fetch(
    `${API_BASE}/api/admin/docs/${slug}/questions/${entryId}/vote`,
    {
      method: "POST",
      headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
      body: JSON.stringify({ action: "revoked" }),
    },
  );
}

// ── Tests ──────────────────────────────────────────────────────────────────

test.describe("Statistik route structure", () => {
  test("renders the 6th DocStepTab and all three subsections", async ({ page }) => {
    await page.addInitScript((t) => sessionStorage.setItem("auth-token", t), TOKEN);
    const target = await firstQuestion(PROVIDED_SLUG!);

    await page.goto(`/admin/doc/${target.slug}/statistics`);

    // DocStepTabs persistence — Statistik is the 6th tab
    const navTabs = page.getByRole("tab");
    await expect(navTabs).toHaveCount(6);
    await expect(page.getByRole("tab", { name: /statistik/i })).toBeVisible();

    // Three section headings render — h2 by Decision 1
    await expect(page.getByRole("heading", { name: "Extrahieren", level: 2 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Synthese", level: 2 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Provenienz", level: 2 })).toBeVisible();
  });

  test("auth gate redirects to login message when logged out", async ({ page }) => {
    // Clear any prior auth state and visit directly.
    await page.context().clearCookies();
    await page.addInitScript(() => sessionStorage.removeItem("auth-token"));
    const target = await firstQuestion(PROVIDED_SLUG!);

    await page.goto(`/admin/doc/${target.slug}/statistics`);

    // Should NOT show the section headings (the route's auth-guard fires
    // before any react-query runs).
    await expect(page.getByText("Bitte zuerst anmelden.")).toBeVisible();
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
    await page.addInitScript((t) => sessionStorage.setItem("auth-token", t), TOKEN);
    const target = await firstQuestion(PROVIDED_SLUG!);

    await page.goto(`/admin/doc/${target.slug}/synthesise`);

    const card = page.getByTestId(`question-${target.entryId}`);
    await expect(card).toBeVisible();

    // Pre-vote: NO counts text, transparent left stripe.
    await expect(card.locator("text=/\\d+\\s*✓\\s*·\\s*\\d+\\s*✗/")).toHaveCount(0);
    const stripeBefore = await card.evaluate(
      (el) => getComputedStyle(el).borderLeftColor,
    );
    // emerald-500 is rgb(16,185,129); red-500 is rgb(239,68,68). transparent
    // computes to "rgba(0, 0, 0, 0)" in browsers.
    expect(stripeBefore).toBe("rgba(0, 0, 0, 0)");

    // Click Einverstanden — anti-anchoring should release counts.
    await card.getByRole("button", { name: /einverstanden/i }).click();

    // Counts appear and read "1 ✓ · 0 ✗" (or any "N ✓ · M ✗" where N≥1)
    await expect(card.locator("text=/\\d+\\s*✓\\s*·\\s*\\d+\\s*✗/")).toBeVisible({
      timeout: 5000,
    });

    // Stripe is now emerald.
    await expect.poll(
      async () =>
        await card.evaluate((el) => getComputedStyle(el).borderLeftColor),
    ).toBe("rgb(16, 185, 129)");
  });

  test("toggle-to-revoked: second click removes stripe + counts", async ({ page }) => {
    await page.addInitScript((t) => sessionStorage.setItem("auth-token", t), TOKEN);
    const target = await firstQuestion(PROVIDED_SLUG!);

    await page.goto(`/admin/doc/${target.slug}/synthesise`);

    const card = page.getByTestId(`question-${target.entryId}`);
    const approve = card.getByRole("button", { name: /einverstanden/i });

    // First click → cast, counts visible.
    await approve.click();
    await expect(card.locator("text=/\\d+\\s*✓\\s*·\\s*\\d+\\s*✗/")).toBeVisible({
      timeout: 5000,
    });

    // Second click on the same button → revoked.
    await approve.click();

    // Counts gone (anti-anchoring re-engages because my_vote is null again).
    await expect(card.locator("text=/\\d+\\s*✓\\s*·\\s*\\d+\\s*✗/")).toHaveCount(0, {
      timeout: 5000,
    });

    // Stripe back to transparent.
    await expect.poll(
      async () =>
        await card.evaluate((el) => getComputedStyle(el).borderLeftColor),
    ).toBe("rgba(0, 0, 0, 0)");
  });

  test("disqualifizieren paints the stripe red", async ({ page }) => {
    await page.addInitScript((t) => sessionStorage.setItem("auth-token", t), TOKEN);
    const target = await firstQuestion(PROVIDED_SLUG!);

    await page.goto(`/admin/doc/${target.slug}/synthesise`);

    const card = page.getByTestId(`question-${target.entryId}`);
    await card.getByRole("button", { name: /disqualifizieren/i }).click();

    // Stripe is red-500.
    await expect.poll(
      async () =>
        await card.evaluate((el) => getComputedStyle(el).borderLeftColor),
    ).toBe("rgb(239, 68, 68)");

    // Counts appear with the rejected count side > 0.
    await expect(card.locator("text=/0\\s*✓\\s*·\\s*[1-9]\\d*\\s*✗/")).toBeVisible();
  });
});
