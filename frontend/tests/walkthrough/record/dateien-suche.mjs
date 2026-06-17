// Walkthrough recording: dateien-suche
// Tour the inbox filename/slug search filter. The „Dateien"-Tab (/admin/inbox)
// lists every uploaded PDF; the „suchen…"-Feld oben rechts filtert die Tabelle
// live (client-seitig) über Dateiname ODER slug. Reiner Read-Only-Flow — es
// wird kein Backend-State erzeugt, also kein Cleanup nötig.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
  sessionStorage.setItem("goldens.tenant_name", "Fachbereich 3.3");
}, { t: TOKEN });

// Pick a real filter token from the live doc list: a distinctive substring of
// the first filename (the filter matches filename OR slug, inbox.tsx:40).
let docCount = 0;
let token = "ronkohavi";
try {
  const r = await fetch(`${API}/api/admin/docs`, { headers: { "X-Auth-Token": TOKEN } });
  if (r.ok) {
    const docs = await r.json();
    docCount = docs.length;
    const first = docs[0]?.filename ?? "";
    const stem = first.replace(/\.pdf$/i, "");
    // Prefer a distinctive middle chunk over the (often shared) year prefix.
    const words = stem.split(/[\s_\-]+/).filter(w => w.length >= 5);
    token = (words[1] ?? words[0] ?? stem.slice(0, 6) ?? token).toLowerCase();
  }
} catch {
  /* backend not reachable at setup — fall back to the default token */
}
console.log(`Inbox docs: ${docCount} | filter token: "${token}"`);

const rec = new Recorder("dateien-suche", BASE);

await page.goto(`${BASE}/#/admin/inbox`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2000);

// Step 1: Dateien-Liste geladen, Such-Feld oben rechts
await rec.step(page, "Dateien-Tab: alle Dokumente + „suchen…“-Filter", {
  actions: ["goto /admin/inbox"],
  notes: [
    "Der „Dateien“-Tab (/admin/inbox) listet jedes hochgeladene PDF mit Seiten, Status, Elementen und „Zuletzt geändert“.",
    `Aktuell ${docCount || "alle"} Dokumente in der Tabelle.`,
    "Oben rechts steht das „suchen…“-Feld (BAM-Light-Surface, btn-primary „PDF hinzufügen“ daneben in BAM-Cyan).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'input[placeholder^="suchen"]', text: "Such-/Filter-Feld" },
    { kind: "highlight", selector: 'table', text: "Vollständige Dokumentliste" },
  ] }],
});

// Step 2: Filter eintippen → Tabelle narrowt live
await page.locator('input[placeholder^="suchen"]').fill(token);
await page.waitForTimeout(400);
await rec.step(page, `Tippen → Liste filtert live auf „${token}“`, {
  actions: [`fill input[placeholder^="suchen"] = "${token}"`],
  notes: [
    "Die Tabelle filtert client-seitig bei jedem Tastendruck (useState + Array.filter, inbox.tsx:40) — kein Server-Roundtrip.",
    "Der Treffer matcht über Dateiname ODER slug, beide case-insensitive — so findet man ein Dokument auch über seinen slug-Teil.",
    "Es bleiben nur die passenden Zeilen sichtbar; die restlichen werden aus dem Render entfernt.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'input[placeholder^="suchen"]', text: "Eingetippter Filter-Begriff" },
    { kind: "highlight", selector: 'table tbody tr', text: "Gefilterte Treffer-Zeile(n)" },
  ] }],
});

// Step 3: Filter leeren → volle Liste zurück
await page.locator('input[placeholder^="suchen"]').fill("");
await page.waitForTimeout(400);
await rec.step(page, "Filter geleert → vollständige Liste zurück", {
  actions: ['fill input[placeholder^="suchen"] = ""'],
  notes: [
    "Beim Leeren des Feldes greift der Filter nicht mehr → alle Dokumente erscheinen wieder.",
    "Der Filter ist nur UI-State (kein localStorage, kein Server) — Reload setzt ihn ohnehin zurück. Read-Only, kein Eingriff in Dokument-Daten.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Wieder im Default-Zustand (Filter leer, alle Zeilen sichtbar)" },
  ] }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
