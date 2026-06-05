// Walkthrough recording: global-curators
// Tour the global curator CRUD page (/#/admin/curators). An admin creates a
// curator, sees the access token exactly once in a modal (C16: shown-once),
// the curator appears in the list with only its token prefix, then gets
// revoked. We use a throwaway, time-stamped name and revoke through the UI;
// a belt-and-suspenders API teardown removes any leftover curator with our
// name so re-runs stay pristine.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

// Unique throwaway name → the row/Revoke scope is unambiguous and a failed
// prior teardown can't collide with this run.
const NAME = `wt-curator-${Date.now()}`;

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

// Revoke triggers window.confirm — auto-accept every dialog up front.
page.on("dialog", (d) => d.accept());

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const rec = new Recorder("global-curators", BASE);

await page.goto(`${BASE}/#/admin/curators`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(1500);

// Step 1: Curators page — list + „Create curator"
await rec.step(page, "Kuratoren-Verwaltung: Liste + „Create curator“", {
  actions: ["goto /admin/curators"],
  notes: [
    "Globale Kuratoren-Verwaltung (Sidebar „Kuratoren“) — hier legt ein Admin Kurator-Zugänge an und entzieht sie wieder.",
    "Die Tabelle zeigt pro Kurator nur Name, Token-Präfix und Anlage-Datum — das volle Token wird hier nie angezeigt (BAM-Datengrid, helle Zebra-Zeilen).",
    "Der BAM-cyan „Create curator“-Button (oben rechts, btn-primary / brand-500 #00aff0) öffnet den Anlege-Dialog.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button:has-text("Create curator")', text: "Create curator (BAM-cyan CTA)" },
    { kind: "highlight", selector: "table", text: "Bestehende Kuratoren (nur Token-Präfix sichtbar)" },
  ] }],
});

// Step 2: open the create dialog → name input
await page.locator('button:has-text("Create curator")').click();
await page.locator('[role="dialog"]:has-text("Create curator")').waitFor({ state: "visible" });
await page.waitForTimeout(300);
await page.locator('[role="dialog"] input[placeholder="Name"]').fill(NAME);
await page.waitForTimeout(300);
await rec.step(page, "Anlege-Dialog: Name eingeben", {
  actions: ['click button "Create curator"', `fill Name = "${NAME}"`],
  notes: [
    "Der Dialog hat genau ein Feld: den Kurator-Namen (Platzhalter „Name“).",
    `Wir nutzen einen Wegwerf-Namen mit Zeitstempel (${NAME}), damit Wiederholungs-Läufe nicht kollidieren.`,
    "„Create“ ist deaktiviert, solange das Namensfeld leer ist (btn-primary disabled bei leerem Trim).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[role="dialog"] input[placeholder="Name"]', text: "Name des neuen Kurators" },
    { kind: "highlight", selector: '[role="dialog"] button[type="submit"]', text: "Create (aktiv, sobald Name gesetzt)" },
  ] }],
});

// Step 3: submit → token-shown-once modal
await page.locator('[role="dialog"] button[type="submit"]').click();
await page.locator('[role="dialog"]:has-text("Curator token")').waitFor({ state: "visible" });
await page.waitForTimeout(400);
await rec.step(page, "Token-Modal: Zugang wird genau EINMAL gezeigt (C16)", {
  actions: ['click "Create" (submit)', "POST /api/admin/curators"],
  notes: [
    "Nach dem Anlegen erscheint das volle API-Token in einem Modal — „Copy this token now — it will not be shown again.“",
    "Das ist der einzige Moment, in dem das Klartext-Token sichtbar ist; danach kennt der Server nur noch den Hash + das Präfix.",
    "„Copy“ schreibt das Token in die Zwischenablage; „Done“ schließt das Modal und lädt die Liste neu (invalidateQueries).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[role="dialog"]:has-text("Curator token") code', text: "Vollständiges Token (nur einmal sichtbar)" },
    { kind: "highlight", selector: '[role="dialog"] button:has-text("Copy")', text: "In Zwischenablage kopieren" },
  ] }],
});

// Step 4: dismiss modal → curator appears in the list
await page.locator('[role="dialog"] button:has-text("Done")').click();
await page.locator(`tr:has-text("${NAME}")`).waitFor({ state: "visible" });
await page.waitForTimeout(500);
await rec.step(page, "Neuer Kurator in der Liste — nur Token-Präfix", {
  actions: ['click "Done"', "Liste neu geladen"],
  notes: [
    `Der neue Kurator „${NAME}“ steht jetzt in der Tabelle — mit Token-Präfix (mono) und heutigem Anlage-Datum.`,
    "Das volle Token taucht nirgends mehr auf: nur das Präfix (token_prefix) wird gespeichert/angezeigt.",
    "Pro Zeile gibt es rechts einen roten „Revoke“-Link (text-bam-red) zum Entziehen des Zugangs.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: `tr:has-text("${NAME}")`, text: "Neu angelegter Kurator" },
    { kind: "highlight", selector: `tr:has-text("${NAME}") button:has-text("Revoke")`, text: "Revoke (rot, pro Zeile)" },
  ] }],
});

// Step 5: revoke → curator removed (confirm auto-accepted)
await page.locator(`tr:has-text("${NAME}") button:has-text("Revoke")`).click();
await page.locator(`tr:has-text("${NAME}")`).waitFor({ state: "detached" }).catch(() => {});
await page.waitForTimeout(800);
await rec.step(page, "Nach „Revoke“: Zugang entzogen, Zeile verschwindet", {
  actions: [`click "Revoke" in row "${NAME}"`, "confirm() bestätigt", "DELETE /api/admin/curators/{id}"],
  notes: [
    "„Revoke“ fragt vorher per Bestätigungs-Dialog nach („Revoke access for … This cannot be undone.“) — bestätigt löst DELETE auf den Kurator aus.",
    "Nach Erfolg verschwindet die Zeile aus der Liste (invalidateQueries) und ein Toast meldet „Curator revoked“.",
    "Das zugehörige Token ist damit serverseitig ungültig — der Kurator kann sich nicht mehr anmelden.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Zeile „${NAME}“ ist nach dem Revoke nicht mehr in der Tabelle` },
  ] }],
});

// Cleanup: revoke any leftover curator with our throwaway name (in case the
// UI revoke step didn't complete) so re-runs start from a pristine list.
try {
  const r = await fetch(`${API}/api/admin/curators`, { headers: { "X-Auth-Token": TOKEN } });
  if (r.ok) {
    const all = await r.json();
    const leftovers = (Array.isArray(all) ? all : []).filter((c) => c.name === NAME);
    for (const c of leftovers) {
      const del = await fetch(`${API}/api/admin/curators/${encodeURIComponent(c.id)}`, {
        method: "DELETE",
        headers: { "X-Auth-Token": TOKEN },
      });
      console.log(del.ok ? `Cleanup: revoked leftover ${c.id}` : `Cleanup failed for ${c.id}: ${del.status}`);
    }
    if (leftovers.length === 0) console.log("Cleanup: no leftover curator — UI revoke succeeded.");
  } else {
    console.log("Cleanup list fetch failed:", r.status);
  }
} catch (e) {
  console.log("Cleanup error:", e.message);
}

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
