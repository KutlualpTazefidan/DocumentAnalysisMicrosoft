// Walkthrough recording: settings
// Tour the Einstellungen-Seite (/admin/settings) + Abmelden-Flow. The
// settings screen is a READ-ONLY account view: Pseudonym, Rolle und
// Fachbereich werden angezeigt, aber Benutzername/Passwort sind zentral
// von der Administration verwaltet und hier nicht änderbar. Am Ende klickt
// „Abmelden“ → Session wird verworfen → Landung auf /login.
// Keine Backend-State-Änderung: wir seeden nur sessionStorage (Token-Mode),
// und logout() widerruft eine Cookie-Session, die hier nie angelegt wurde —
// also kein Cleanup nötig, Re-Runs bleiben sauber.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
  sessionStorage.setItem("goldens.tenant_name", "Fachbereich 3.3");
  // Seed the active tenant so the Fachbereich-Zeile + Header-Badge eine
  // echte Identität zeigen (Credential-Login setzt das normalerweise).
  sessionStorage.setItem("goldens.tenant_slug", "default");
}, { t: TOKEN });

const rec = new Recorder("settings", BASE);

await page.goto(`${BASE}/#/admin/settings`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(1500);

// Step 1: Einstellungen-Seite — Konto-Übersicht (read-only)
await rec.step(page, "Einstellungen: Konto-Übersicht (Pseudonym · Rolle · Fachbereich)", {
  actions: ["goto /admin/settings"],
  notes: [
    "Die Einstellungen-Seite zeigt das Konto für den aktiven Fachbereich: Pseudonym (hier „probe“), Rolle (Administrator → Cyan-Pill) und Fachbereich („default“).",
    "Erreichbar über das Rollen-Pill oben rechts → „Einstellungen“, oder direkt per Route /admin/settings.",
    "BAM-Reskin: helle Card-Fläche, Cyan-Akzent-Pill für die Rolle, der Fachbereich als Monospace-Slug.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'h1:has-text("Einstellungen")', text: "Seitentitel „Einstellungen“" },
    { kind: "highlight", selector: 'h2:has-text("Konto")', text: "Konto-Card: Pseudonym · Rolle · Fachbereich" },
  ] }],
});

// Step 2: Read-only-Hinweis — keine Selbstverwaltung von Login-Daten
await rec.step(page, "Read-only: Benutzername & Passwort sind admin-verwaltet", {
  actions: ["read account info"],
  notes: [
    "Bewusst keine Edit-Controls: kein Passwort-ändern, kein Benutzername-Feld. Der Info-Hinweis sagt es explizit — Login-Daten werden zentral von der Administration verwaltet und sind hier nicht änderbar.",
    "Das ist Policy, kein fehlendes Feature: Self-Service-Auth gibt es in diesem Tool nicht.",
    "Die einzige Aktion auf dieser Seite ist „Abmelden“ (rote btn-danger ganz unten).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'p:has-text("zentral von der Administration verwaltet")', text: "Read-only-Hinweis (keine Selbstverwaltung)" },
    { kind: "highlight", selector: 'button:has-text("Abmelden")', text: "Einzige Aktion: Abmelden" },
  ] }],
});

// Step 3: Rollen-Menü oben rechts — der zweite Weg zu Einstellungen/Abmelden
await page.locator('[aria-label*="Menü öffnen"]').click().catch(()=>{});
await page.waitForTimeout(400);
await rec.step(page, "Rollen-Pill (Header) → Menü „Einstellungen / Abmelden“", {
  actions: ['click [aria-label*="Menü öffnen"] (Rollen-Pill rechts oben)'],
  notes: [
    "Das Cyan-Rollen-Pill rechts oben ist klickbar und öffnet ein Dropdown mit „Einstellungen“ und „Abmelden“ — derselbe Logout wie der Button auf der Seite.",
    "Links daneben der Fachbereichs-Badge („default“) und das Glocken-Icon (Benachrichtigungen).",
    "Wir schließen das Menü gleich wieder und melden uns über den Seiten-Button ab.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Dropdown: „Einstellungen“ + „Abmelden“ (gleicher Logout-Pfad)" },
  ] }],
});

// Close the dropdown so it doesn't overlay the logout click.
await page.keyboard.press("Escape").catch(()=>{});
await page.waitForTimeout(300);

// Step 4: Abmelden → Session verworfen → Landung auf /login
await page.locator('button:has-text("Abmelden")').click();
await page.locator('button:has-text("Einloggen")').first().waitFor({ timeout: 5000 }).catch(()=>{});
await page.waitForTimeout(800);
await rec.step(page, "Abmelden → Login-Seite (Session verworfen)", {
  actions: ['click button:has-text("Abmelden")', "redirect → /login"],
  notes: [
    "„Abmelden“ leert die Session (sessionStorage-Keys goldens.api_token/role/name/tenant_slug) und widerruft best-effort die Server-Cookie-Session — dann Redirect auf /login.",
    "Die Login-Seite zeigt die GOLDENS-Lockup (BAM-Logo + Wortmarke), das Anmeldeformular (Fachbereich · Benutzername · Passwort) und den Test-Umgebungs-Warnhinweis.",
    "Ab hier ist man ausgeloggt: jeder Aufruf von /admin/* leitet zurück auf /login (Rollen-Gate im AdminShell).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'h1:has-text("Goldens")', text: "GOLDENS-Login-Lockup" },
    { kind: "highlight", selector: 'button:has-text("Einloggen")', text: "Anmelde-Button — wieder ausgeloggt" },
  ] }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
