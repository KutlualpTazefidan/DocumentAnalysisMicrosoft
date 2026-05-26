/**
 * Login + Tenant-Admin walkthrough.
 *
 * Prereqs:
 *   1. Backend running on 127.0.0.1:8001 (`bash scripts/dev-local-pdf.sh`).
 *   2. Vite dev server on 127.0.0.1:5173 (`npm run dev`).
 *   3. Auth bootstrapped with at least one admin user:
 *        query-eval segment auth init \
 *          --tenant-slug default \
 *          --tenant-name "Default" \
 *          --admin-username admin \
 *          --admin-password <pw>
 *
 * Override the bootstrap credentials via env vars if you used
 * different ones:
 *   WT_TENANT=default
 *   WT_USERNAME=admin
 *   WT_PASSWORD=<your-admin-password>
 *
 * What this exercises:
 *   - /login (Credentials tab)
 *   - cookie session + redirect to /admin/inbox
 *   - header pill renders tenant + pseudonym
 *   - /admin/tenants list + create + select
 *   - per-tenant user-create form with pseudonym auto-suggest
 */

import type { Walkthrough } from "../walkthrough";

const TENANT = process.env.WT_TENANT ?? "default";
const USERNAME = process.env.WT_USERNAME ?? "admin";
const PASSWORD = process.env.WT_PASSWORD ?? "admin";

// Brand-new tenant we create during the walkthrough; suffix with a
// timestamp so re-runs don't clash with existing rows.
const NEW_TENANT_SLUG = `walkthrough-${Date.now().toString(36)}`;
const NEW_TENANT_NAME = "Walkthrough Demo Tenant";
const NEW_USERNAME = "wt-curator";

export default async function (w: Walkthrough): Promise<void> {
  // ── 1. Open login ──────────────────────────────────────────────────
  await w.step("Open login page", async (s) => {
    await s.goto("/login");
    await s.expectVisible("h1");
    s.note(
      "Two tabs visible — Credentials (new flow) and API-Token (legacy).",
    );
    s.highlight("h1", "Page title");
    await s.screenshot();
  });

  // ── 2. Fill credentials ───────────────────────────────────────────
  await w.step("Fill credentials", async (s) => {
    await s.fill('input[aria-label="Tenant-Slug"]', TENANT);
    await s.fill('input[aria-label="Username"]', USERNAME);
    await s.fill('input[aria-label="Passwort"]', PASSWORD);
    s.highlight('button[type="submit"]', "Login button");
    s.note("Cookie is set HttpOnly by the backend on success.");
    await s.screenshot({ note: "Form pre-submit" });
  });

  // ── 3. Submit + verify redirect ───────────────────────────────────
  await w.step("Submit + land on inbox", async (s) => {
    await s.click('button[type="submit"]');
    await s.waitForUrl(/\/admin\//);
    s.note("Browser was redirected to /admin/inbox (or wherever the role lands).");
    await s.screenshot({ note: "Post-login state" });
  });

  // ── 4. Check header pill ──────────────────────────────────────────
  await w.step("Verify header shows tenant + pseudonym", async (s) => {
    await s.expectVisible("header");
    s.note(
      "Top-right of the admin shell should now show: tenant slug + pseudonym chip + Logout.",
    );
    s.highlight("header", "Admin shell header");
    await s.screenshot();
  });

  // ── 5. Navigate to /admin/tenants ─────────────────────────────────
  await w.step("Open Tenants admin", async (s) => {
    await s.goto("/admin/tenants");
    await s.expectVisible("text=Tenants");
    s.note("Left column lists tenants; right pane is empty until a tenant is selected.");
    await s.screenshot();
  });

  // ── 6. Create a new tenant ────────────────────────────────────────
  await w.step("Create new tenant", async (s) => {
    await s.fill('input[placeholder="slug (a-z 0-9 -)"]', NEW_TENANT_SLUG);
    await s.fill('input[placeholder="Name"]', NEW_TENANT_NAME);
    s.note(`Creating tenant '${NEW_TENANT_SLUG}'.`);
    await s.screenshot({ note: "Pre-create" });
    await s.click('button:has-text("Anlegen")');
    await s.expectVisible(`text=${NEW_TENANT_SLUG}`);
    await s.screenshot({ note: "Post-create: tenant appears in the list AND is auto-selected" });
  });

  // ── 7. Pseudonym auto-suggest ─────────────────────────────────────
  await w.step("Try the pseudonym suggester", async (s) => {
    s.highlight('button[title*="Pseudonym vom Server vorschlagen"]', "Suggest pseudonym");
    await s.click('button[title*="Pseudonym vom Server vorschlagen"]');
    // The suggestion lands inside the pseudonym input.
    await s.expectVisible('input[placeholder*="Wachsamer Hirsch"]');
    s.note(
      "Server returns a fresh Adjective+Animal pair; user can also type their own.",
    );
    await s.screenshot();
  });

  // ── 8. Create a curator in the new tenant ─────────────────────────
  await w.step("Create curator user", async (s) => {
    await s.fill('input[autocomplete="username"]', NEW_USERNAME);
    await s.fill('input[autocomplete="new-password"]', "curatorpw");
    s.note("Role defaults to 'curator'. The auto-suggested pseudonym is kept.");
    await s.screenshot({ note: "Filled create-user form" });
    await s.click('button:has-text("Benutzer anlegen")');
    await s.expectVisible(`text=${NEW_USERNAME}`);
    await s.screenshot({ note: "User row appears in the table — workflow complete." });
  });
}
