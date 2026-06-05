// Walkthrough recording: login-auth-tenants
// Three phases against the BAM light-theme reskin (post-PR #56):
//   (1) the GOLDENS login card — BAM lockup, dev banner, credential fields;
//   (2) the auth-failure path — wrong password → 401 → inline error alert;
//   (3) tenant + user admin CRUD — create/edit/delete a Fachbereich, create a
//       user inside it — then logout back to the login screen.
//
// AUTH MODEL (important): /api/admin/tenants* is COOKIE-ONLY from the UI.
// TenantsAdmin.tsx calls apiFetch(path, "") with an EMPTY token, so the
// frontend never sends X-Auth-Token for these calls — only the lpdf_session
// session cookie authenticates them (auth.py: cookie-first, header fallback,
// and the lpdf_session cookie is a real SQLite session, not the env token).
// Seeding sessionStorage is therefore NOT enough for Phase 3: we establish a
// real session by POSTing /api/auth/login (the cookie lands in the browser
// context's jar via ctx.request), then drive the tenant CRUD through the UI.
//
// CREDENTIALS: Phase 3 needs a valid admin login in your dev backend. Defaults
// match the standard local seed (tenant=default, user=admin, password=admin);
// override with WT_TENANT / WT_USER / WT_PASSWORD. If the login fails (creds
// not valid in this env) Phase 3 is skipped with a recorded note — Phases 1+2
// (login UI + auth-failure) record fine without any valid credentials.
//
// IDEMPOTENCY: Phase 3 creates a throwaway tenant (unique timestamp slug) and
// deletes it through the UI; a final API DELETE is belt-and-braces cleanup.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

// Phase-3 login credentials (override per env). Defaults match the standard
// local dev seed; the lpdf_session cookie they yield is what authenticates
// the cookie-only TenantsAdmin calls.
const TENANT = process.env.WT_TENANT || "default";
const USER = process.env.WT_USER || "admin";
const PASSWORD = process.env.WT_PASSWORD || "admin";

// Unique, throwaway tenant for this run — keeps re-runs from clashing on slug.
const STAMP = new Date().toISOString().replace(/[^0-9]/g, "").slice(8, 14); // HHMMSS
const TENANT_SLUG = `wt-tenant-${STAMP}`;
const TENANT_NAME = `Walkthrough Tenant ${STAMP}`;
const USER_NAME = `wt-curator-${STAMP}`;

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

// Auto-accept the window.confirm() that the tenant-delete button fires.
page.on("dialog", (d) => d.accept().catch(() => {}));

const rec = new Recorder("login-auth-tenants", BASE);

// ── Phase 1: the BAM login card (logged-out) ──────────────────────────────
// Fresh context = no cookie, no sessionStorage → the card shows logged-out.
await page.goto(`${BASE}/#/login`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(800);

// Step 1: login card — BAM lockup + dev banner
await rec.step(page, "Login: GOLDENS-Lockup auf weißer Karte (BAM-Reskin)", {
  actions: ["goto /#/login"],
  notes: [
    "Nach dem BAM-Reskin: weiße Login-Karte auf dunklem Backdrop (bg-backdrop), oben das BAM-Logo + „GOLDENS“-Lockup (Großbuchstaben, gesperrte Letter-Spacing) — kein dunkles/blaues Alt-Theme mehr.",
    "Unter der Karte der Test-Hinweis: amber-getöntes Band (#fff8e1, Rand-links #ffcb46) mit „Achtung — Test- und Entwicklungsumgebung“.",
    "Default-Ansicht zeigt nur den Credential-Flow (drei Felder). Der Legacy-API-Token-Tab erscheint nur mit ?legacy=1.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: "img[alt='BAM']", text: "BAM-Logo-Lockup" },
    { kind: "highlight", selector: "h1:has-text('Goldens')", text: "GOLDENS-Schriftzug" },
    { kind: "highlight", selector: "div:has(> strong:has-text('Achtung'))", text: "Test-Umgebungs-Hinweis (amber)" },
  ] }],
});

// Step 2: credential fields — Fachbereich / Benutzername / Passwort
await page.locator("input[aria-label='Fachbereich']").fill(TENANT);
await page.locator("input[aria-label='Benutzername']").fill(USER);
await page.locator("input[aria-label='Passwort']").fill("•••••••");
await page.waitForTimeout(300);
await rec.step(page, "Login: drei Credential-Felder mit Icons", {
  actions: [
    `fill input[aria-label='Fachbereich'] = '${TENANT}'`,
    `fill input[aria-label='Benutzername'] = '${USER}'`,
    "fill input[aria-label='Passwort'] = '…'",
  ],
  notes: [
    "Drei Felder mit führenden Icons: Building2 (Fachbereich), User (Benutzername), Lock (Passwort).",
    "Passwort-Feld hat rechts einen Auge-Toggle (aria-label „Passwort anzeigen“ / „Passwort verbergen“) zum Ein-/Ausblenden.",
    "Hilfetext unter dem Passwort: „Im Audit-Log erscheint dein Pseudonym, nie dein Benutzername.“",
    "Der „Einloggen“-Button (btn-primary, BAM-Cyan #00aff0) ist aktiv, sobald alle drei Felder gefüllt sind.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: "input[aria-label='Fachbereich']", text: "Fachbereich (Building2-Icon)" },
    { kind: "highlight", selector: "input[aria-label='Benutzername']", text: "Benutzername (User-Icon)" },
    { kind: "highlight", selector: "input[aria-label='Passwort']", text: "Passwort (Lock + Auge-Toggle)" },
    { kind: "highlight", selector: "button:has-text('Einloggen')", text: "Einloggen-CTA (BAM-Cyan)" },
  ] }],
});

// ── Phase 2: 401 auth-failure path ────────────────────────────────────────
// Submit deliberately-wrong credentials. The login POST returns 401, the form
// sets its error state and stays on /login. A *real* round-trip, no mocking,
// and no valid credentials required.
await page.locator("input[aria-label='Passwort']").fill("definitiv-falsch");
await page.locator("button:has-text('Einloggen')").click();
await page.locator("div[role='alert']").first().waitFor({ timeout: 6000 }).catch(() => {});
await page.waitForTimeout(500);
await rec.step(page, "Auth-Fehler: falsches Passwort → 401 → Inline-Alert", {
  actions: [
    "fill input[aria-label='Passwort'] = 'definitiv-falsch'",
    "click button:has-text('Einloggen')",
    "POST /api/auth/login → 401",
  ],
  notes: [
    "POST /api/auth/login mit falschen Credentials liefert 401. Der Frontend fängt status===401 ab und setzt die Fehlermeldung.",
    "Inline-Alert (role='alert', rot) unter dem Passwort-Feld: „Login fehlgeschlagen — Fachbereich, Benutzername oder Passwort falsch.“",
    "Das Formular bleibt auf /login (keine Navigation) und ist weiter bedienbar — korrigieren und erneut versuchen.",
    "Bei zu vielen Fehlversuchen (429) zeigt dasselbe Alert stattdessen „Zu viele Fehlversuche. Erneut möglich ab HH:MM.“",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: "div[role='alert']", text: "401-Fehlermeldung (rot)" },
    { kind: "highlight", selector: "button:has-text('Einloggen')", text: "Formular bleibt aktiv" },
  ] }],
});

// ── Phase 3: establish a real session, then tenant + user CRUD ────────────
// /api/admin/tenants is cookie-only from the UI, so we need a real session
// cookie. POST /api/auth/login via ctx.request stores lpdf_session in the
// context's cookie jar (shared with the page); we then mirror the identity
// into sessionStorage so the admin shell renders.
let authed = false;
try {
  const resp = await ctx.request.post(`${BASE}/api/auth/login`, {
    data: { tenant_slug: TENANT, username: USER, password: PASSWORD },
  });
  if (resp.ok()) {
    const ident = await resp.json().catch(() => ({}));
    await page.goto(`${BASE}/`);
    await page.evaluate((id) => {
      sessionStorage.setItem("goldens.api_token", ""); // cookie-mode → empty token
      sessionStorage.setItem("goldens.role", id.role || "admin");
      sessionStorage.setItem("goldens.name", id.pseudonym || "probe");
      if (id.tenant_slug) sessionStorage.setItem("goldens.tenant_slug", id.tenant_slug);
    }, ident);
    authed = true;
  } else {
    console.log(`Phase 3 login failed (${resp.status()}) — skipping Tenant-CRUD. Set WT_TENANT/WT_USER/WT_PASSWORD.`);
  }
} catch (e) {
  console.log("Phase 3 login request failed:", e.message, "— skipping Tenant-CRUD.");
}

if (!authed) {
  await rec.step(page, "Phase 3 übersprungen — keine gültigen Login-Credentials", {
    actions: ["POST /api/auth/login → ≠ 200"],
    notes: [
      "Tenant-CRUD (Phase 3) braucht eine echte Admin-Session (lpdf_session-Cookie). /api/admin/tenants ist Cookie-only — der seeded X-Auth-Token reicht hier nicht.",
      "Setze WT_TENANT / WT_USER / WT_PASSWORD passend zum Dev-Backend (Default: default/admin/admin), dann läuft Phase 3 durch.",
    ],
  });
} else {
  // Step 3: admin shell — IconRail nav (icon-only, aria-label) + BamHeader
  await page.goto(`${BASE}/#/admin/inbox`);
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1200);
  await rec.step(page, "Admin-Shell nach Login: IconRail + BamHeader", {
    actions: ["echtes /api/auth/login → Session-Cookie", "goto /#/admin/inbox"],
    notes: [
      "Linke IconRail (nur Icons, je mit aria-label/title): Dokumente, Kuratoren, Fachbereiche, Pipelines, Übersicht — aktives Item bekommt einen Cyan-Indikator.",
      "Oben die BamHeader: BAM-Lockup links, LlmTopBarControl mittig, rechts Fachbereich-Badge + Glocke + Rollen-Pill (Klick öffnet Einstellungen/Abmelden).",
      "Inhaltsfläche hell (bg-canvas), Navy-Text, Cyan-CTAs — durchgehend Light-Theme nach Reskin.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: "nav[aria-label='Hauptnavigation']", text: "IconRail (Sektions-Navigation)" },
      { kind: "highlight", selector: "a[aria-label='Fachbereiche']", text: "Fachbereiche-Rail-Item" },
      { kind: "highlight", selector: "button[aria-label*='Menü öffnen']", text: "Rollen-Pill (Abmelden-Menü)" },
    ] }],
  });

  // Step 4: click the rail → Tenants page (icon-only → target by aria-label).
  await page.locator("a[aria-label='Fachbereiche']").click();
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1000);
  await rec.step(page, "Fachbereiche-Seite: Liste links + Anlegen-Button", {
    actions: ["click a[aria-label='Fachbereiche']", "→ /#/admin/tenants"],
    notes: [
      "Linke Spalte (aside): Überschrift „Fachbereiche“ + Plus-Button (aria-label „Neuen Fachbereich anlegen“), darunter die Tenant-Liste.",
      "Bei genau einem Fachbereich wird er automatisch selektiert; sonst zeigt die rechte Spalte „Fachbereich aus der Liste links wählen…“.",
      "Jede Listenzeile zeigt Slug (Mono, klein) + Anzeigename und blendet bei Hover/aktiv Bearbeiten- (Edit3) und Löschen-Icons (Trash2) ein.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: "h1:has-text('Fachbereiche')", text: "Fachbereiche-Überschrift" },
      { kind: "highlight", selector: "button[aria-label='Neuen Fachbereich anlegen']", text: "Neuen Fachbereich anlegen (+)" },
    ] }],
  });

  // Step 5: open the create-tenant modal and create the throwaway tenant.
  await page.locator("button[aria-label='Neuen Fachbereich anlegen']").click();
  await page.locator("text=Neuer Fachbereich").first().waitFor({ timeout: 4000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.locator("input[aria-label='Slug']").fill(TENANT_SLUG);
  await page.locator("input[aria-label='Anzeigename']").fill(TENANT_NAME);
  await page.waitForTimeout(300);
  await rec.step(page, "Neuen Fachbereich anlegen: Modal mit Slug + Anzeigename", {
    actions: [
      "click button[aria-label='Neuen Fachbereich anlegen']",
      `fill input[aria-label='Slug'] = '${TENANT_SLUG}'`,
      `fill input[aria-label='Anzeigename'] = '${TENANT_NAME}'`,
    ],
    notes: [
      "Radix-Dialog: dunkles Overlay (bg-black/40) + weiße Karte. Titel „Neuer Fachbereich“.",
      "Zwei Pflichtfelder: Slug (Kurz-ID — Kleinbuchstaben, Zahlen, Bindestriche) und Anzeigename.",
      "„Fachbereich anlegen“ (btn-primary) ist disabled, bis beide Felder gefüllt sind. Klick → POST /api/admin/tenants {slug, name}.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: "input[aria-label='Slug']", text: "Slug (Kurz-ID, unveränderlich)" },
      { kind: "highlight", selector: "input[aria-label='Anzeigename']", text: "Anzeigename" },
      { kind: "highlight", selector: "button:has-text('Fachbereich anlegen')", text: "Anlegen-CTA" },
    ] }],
  });

  // Submit the create form — modal closes, tenant is auto-selected.
  await page.locator("button:has-text('Fachbereich anlegen')").click();
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1200);
  await rec.step(page, "Fachbereich angelegt → auto-selektiert, Detail-Pane offen", {
    actions: ["click button:has-text('Fachbereich anlegen')", "POST /api/admin/tenants → 201"],
    notes: [
      `Der neue Fachbereich „${TENANT_SLUG}“ erscheint in der Liste links und ist aktiv selektiert (bg-rowsel, Text in BAM-Cyan, font-semibold).`,
      "Rechts öffnet sich die TenantDetail: Header „Fachbereich <slug>“, darunter das „Neuer Benutzer“-Formular und die (noch leere) Benutzer-Tabelle.",
      "Die ['tenants']-Query wird invalidiert → die Liste lädt frisch nach.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: `button[aria-label='Fachbereich ${TENANT_SLUG} bearbeiten']`, text: "Neuer Fachbereich (aktiv)" },
      { kind: "highlight", selector: "h3:has-text('Neuer Benutzer')", text: "Benutzer-anlegen-Formular" },
    ] }],
  });

  // Step 6: create a user in the selected tenant. The CreateUserForm inputs
  // have no aria-label — scope by the "Neuer Benutzer" card + field order.
  const userForm = page.locator("form:has(h3:has-text('Neuer Benutzer'))");
  await userForm.locator("input[type='text']").first().fill(USER_NAME);
  await userForm.locator("input[type='password']").fill("test-passwort-123");
  await userForm.locator("select").selectOption("curator").catch(() => {});
  await page.waitForTimeout(300);
  await rec.step(page, "Benutzer im Fachbereich anlegen: Formular ausfüllen", {
    actions: [
      `fill Benutzername = '${USER_NAME}'`,
      "fill Passwort = '…'",
      "select Rolle = 'curator'",
    ],
    notes: [
      "Das „Neuer Benutzer“-Formular ist eine Karte (card p-4) im Detail-Pane mit 2×2-Grid: Benutzername, Passwort, Rolle (Select: curator/reviewer/admin), Pseudonym.",
      "Benutzername + Passwort sind Pflicht; Rolle steht per Default auf „curator“. Pseudonym optional — leer lassen erzeugt es automatisch, oder „Vorschlagen“ holt einen Server-Vorschlag (Adjektiv + Tier).",
      "Die Felder tragen keine aria-labels — sie werden über die Karte + Feld-Reihenfolge angesprochen.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: "form:has(h3:has-text('Neuer Benutzer'))", text: "Neuer-Benutzer-Karte" },
      { kind: "highlight", selector: "button:has-text('Benutzer anlegen')", text: "Benutzer-anlegen-CTA" },
    ] }],
  });

  // Submit user create → table re-renders with the new row.
  await page.locator("button:has-text('Benutzer anlegen')").click();
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1200);
  await rec.step(page, "Benutzer angelegt → erscheint in der Tabelle als „aktiv“", {
    actions: ["click button:has-text('Benutzer anlegen')", "POST /api/admin/tenants/<slug>/users → 201"],
    notes: [
      "Die UserTable rendert Spalten: Benutzername, Pseudonym, Rolle, Aktiv, Letzte Anmeldung, Aktionen.",
      `Neue Zeile: Benutzername „${USER_NAME}“, Rolle „curator“, Status „aktiv“ (grüner StatusBadge mit CheckCircle2).`,
      "Spalte Aktionen zeigt bei aktiven Benutzern „Deaktivieren“ (btn-danger) — Soft-Delete: setzt active=0 und verwirft offene Sessions, behält die Zeile fürs Audit.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: `td:has-text('${USER_NAME}')`, text: "Neue Benutzer-Zeile" },
      { kind: "highlight", selector: "td:has-text('aktiv')", text: "Status „aktiv“ (StatusBadge)" },
    ] }],
  });

  // Step 7: edit the tenant name via the EditTenantModal.
  await page.locator(`button[aria-label='Fachbereich ${TENANT_SLUG} bearbeiten']`).click();
  await page.locator("text=Fachbereich bearbeiten").first().waitFor({ timeout: 4000 }).catch(() => {});
  await page.waitForTimeout(400);
  await page.locator("input[aria-label='Anzeigename']").fill(`${TENANT_NAME} (umbenannt)`);
  await page.waitForTimeout(300);
  await rec.step(page, "Fachbereich umbenennen: Slug read-only, Anzeigename editierbar", {
    actions: [
      `click button[aria-label='Fachbereich ${TENANT_SLUG} bearbeiten']`,
      "fill input[aria-label='Anzeigename'] = '… (umbenannt)'",
    ],
    notes: [
      "Edit-Button je Zeile: aria-label „Fachbereich <slug> bearbeiten“ (Edit3-Icon), sichtbar bei Hover oder wenn die Zeile aktiv ist.",
      "EditTenantModal: Slug wird read-only als <code> angezeigt (unveränderlich — partitioniert die Daten unter data_root), nur der Anzeigename ist editierbar.",
      "„Speichern“ (btn-primary) ist erst aktiv, wenn der Name sich vom Original unterscheidet. Klick → PATCH /api/admin/tenants/<slug> {name}.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: "input[aria-label='Anzeigename']", text: "Anzeigename (editierbar)" },
      { kind: "highlight", selector: "button:has-text('Speichern')", text: "Speichern-CTA" },
    ] }],
  });
  await page.locator("button:has-text('Speichern')").click();
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1000);

  // Step 8: delete the tenant (window.confirm auto-accepted by the handler).
  await rec.step(page, "Fachbereich löschen: Bestätigungsdialog (window.confirm)", {
    actions: [
      `click button[aria-label='Fachbereich ${TENANT_SLUG} löschen']`,
      "window.confirm → OK → DELETE /api/admin/tenants/<slug>",
    ],
    notes: [
      "Löschen-Button je Zeile: aria-label „Fachbereich <slug> löschen“ (Trash2-Icon).",
      "Klick öffnet window.confirm: „Fachbereich \"<slug>\" wirklich löschen? Alle Benutzer und Sessions werden mitgelöscht — Dateien unter data_root/tenants/<slug>/ bleiben auf der Platte.“",
      "Bei Bestätigung: DELETE /api/admin/tenants/<slug>. Der Server lehnt das Löschen des EIGENEN Fachbereichs ab (409) — hier ist es ein Wegwerf-Tenant, also erlaubt.",
      "Nach Erfolg: ['tenants'] invalidiert, Selektion geleert, Toast „Fachbereich \"<slug>\" gelöscht“.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: `button[aria-label='Fachbereich ${TENANT_SLUG} löschen']`, text: "Löschen-Button (Trash2)" },
    ] }],
  });
  await page.locator(`button[aria-label='Fachbereich ${TENANT_SLUG} löschen']`).click();
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1200);

  // Step 9: logout via the RoleMenu dropdown → back to the login screen.
  await page.locator("button[aria-label*='Menü öffnen']").click();
  await page.waitForTimeout(400);
  await page.getByRole("menuitem", { name: "Abmelden" }).click().catch(() => {});
  await page.waitForTimeout(1200);
  await rec.step(page, "Abmelden → zurück auf den GOLDENS-Login", {
    actions: [
      "click button[aria-label*='Menü öffnen']",
      "click menuitem 'Abmelden'",
      "→ /#/login",
    ],
    notes: [
      "Die Rollen-Pill (BamHeader, rechts) öffnet ein Radix-Menü mit „Einstellungen“ und „Abmelden“.",
      "„Abmelden“ feuert useAuth().logout(): sessionStorage wird geleert, das 'goldens:logout'-Event verteilt, logoutSession() ruft best-effort /api/auth/logout (Cookie revoken).",
      "Der Router navigiert mit replace:true auf /login — saubere Session, bereit für den nächsten Anmeldeversuch.",
    ],
    shots: [{ annotations: [
      { kind: "highlight", selector: "h1:has-text('Goldens')", text: "Wieder auf dem Login" },
      { kind: "note", text: "Session geleert — Default-Zustand wiederhergestellt" },
    ] }],
  });
}

// ── Cleanup: make sure the throwaway tenant is gone even if the UI delete
// didn't land. Direct API DELETE uses the X-Auth-Token header (admin env
// token), which the backend accepts for /api/admin/* — a 404 just means it
// was already removed (or never created when Phase 3 was skipped).
if (authed) {
  try {
    const r = await fetch(`${API}/api/admin/tenants/${encodeURIComponent(TENANT_SLUG)}`, {
      method: "DELETE",
      headers: { "X-Auth-Token": TOKEN },
    });
    if (r.ok || r.status === 204) {
      console.log(`Cleanup: tenant ${TENANT_SLUG} deleted via API.`);
    } else if (r.status === 404) {
      console.log(`Cleanup: tenant ${TENANT_SLUG} already gone (UI delete worked).`);
    } else {
      console.log(`Cleanup: unexpected status ${r.status} for tenant ${TENANT_SLUG}.`);
    }
  } catch (e) {
    console.log("Cleanup request failed:", e.message);
  }
}

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
