// Walkthrough recording: provenienz-session-crud
// Lifecycle of a Provenienz-Sitzung: open Provenienz → empty rail →
// click „Neu“ → ChunkPicker dialog → select a chunk → session created
// + appears in rail → delete → rail empty again.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

async function findRootChunk() {
  const seg = await (await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": TOKEN } })).json();
  return seg.boxes.find(b => b.kind === "paragraph" && b.page === 2)?.box_id;
}
async function createSession(rootChunkId) {
  const r = await fetch(`${API}/api/admin/provenienz/sessions`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ slug: SLUG, root_chunk_id: rootChunkId }),
  });
  return r.json();
}
async function deleteSession(sid) {
  await fetch(`${API}/api/admin/provenienz/sessions/${sid}`, {
    method: "DELETE", headers: { "X-Auth-Token": TOKEN },
  }).catch(() => {});
}
async function listSessions() {
  const r = await fetch(`${API}/api/admin/provenienz/sessions?slug=${SLUG}`, { headers: { "X-Auth-Token": TOKEN } });
  return r.ok ? r.json() : [];
}

const rootChunk = await findRootChunk();
if (!rootChunk) throw new Error("no paragraph box on page 2");

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
  sessionStorage.setItem("goldens.tenant_name", "Fachbereich 3.3");
}, { t: TOKEN });

const rec = new Recorder("provenienz-session-crud", BASE);

// ── Step 1: Provenienz mit leerem Rail (vorausgesetzt: keine Sitzungen) ───
await page.goto(`${BASE}/#/admin/doc/${SLUG}/provenienz`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2200);
const sessionsBefore = (await listSessions()).filter(s => s.slug === SLUG);
await rec.step(page, `Provenienz geöffnet — ${sessionsBefore.length} Sitzung(en) im Rail`, {
  actions: [`goto /admin/doc/${SLUG}/provenienz`],
  notes: [
    "Frischer Start: keine Sitzungen, kein Canvas-Inhalt, Inspector zeigt Platzhalter.",
    "Eintrittspunkt für neue Sitzungen: „Neu“-Button oben im linken Rail.",
    "Aus dem leeren Zustand ist „Neu“ die einzige sinnvolle Aktion (außer ViewToggle wechseln).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button:has-text("Neu")', text: "„Neu“ öffnet den ChunkPicker" },
  ] }],
});

// ── Step 2: „Neu" klicken → ChunkPicker erscheint ─────────────────────────
await page.locator('button:has-text("Neu")').first().click();
await page.waitForTimeout(1000);
await rec.step(page, "„Neu“ → ChunkPicker-Dialog mit Live-Filter", {
  actions: ['click button "Neu"'],
  notes: [
    "ChunkPicker rendert alle Elemente des Dokuments als klickbare Liste mit Suchfeld.",
    "Live-Filter matcht über Box-Inhalt (lowercased substring), auch Kind/Box-ID treffen.",
    "Auswahl bestimmt root_chunk_id für die Sitzung — Wurzel des Reasoning-DAG.",
    "Esc / Abbrechen schließt den Dialog ohne Sitzungs-Erstellung.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "ChunkPicker-Dialog offen, Such-Input fokussiert" },
  ] }],
});

// ── Step 3: Sitzung via API anlegen (UI-Click-Path ist äquivalent) ────────
await page.keyboard.press("Escape").catch(() => {});
await page.waitForTimeout(400);
const session = await createSession(rootChunk);
console.log("Created session:", session.session_id);
await page.reload();
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2200);
await rec.step(page, `Sitzung angelegt — Rail zeigt jetzt 1 Eintrag, Canvas hat den Wurzel-Chunk`, {
  actions: [
    `POST /sessions {slug, root_chunk_id:"${rootChunk}"}`,
    "(UI: Klick auf einen Chunk im Picker → identischer POST)",
  ],
  notes: [
    "Server vergibt session_id (ULID) und initialisiert die Sitzung mit genau einem Knoten — dem Wurzel-Chunk.",
    "Linkes Rail bekommt sofort einen neuen Eintrag (react-query invalidiert die Sessions-Liste).",
    "Canvas wechselt von leer zu „1 Chunk-Knoten“ + bietet im rechten Inspector die nächste Aktion an (z.B. /next-step für AI-Vorschlag).",
    `Konkret: session_id=${session.session_id.slice(0,12)}…, root=${rootChunk}.`,
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Neue Sitzung im Rail (${session.session_id.slice(0,8)}…)` },
  ] }],
});

// ── Step 4: Sitzung löschen ───────────────────────────────────────────────
await deleteSession(session.session_id);
await page.reload();
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2200);
await rec.step(page, "Sitzung gelöscht — Rail wieder leer (Audit-Trail bleibt im Event-Log)", {
  actions: [`DELETE /sessions/${session.session_id}`],
  notes: [
    "UI-Pfad: „Sitzung löschen“-Button (aria-label) am Sitzungs-Eintrag im Rail; Bestätigungs-Dialog vor harter Aktion.",
    "Server entfernt die Sitzungs-Datei (sidecar) — react-query refetched und das Rail räumt den Eintrag weg.",
    "Audit-Trail im Event-Log bleibt erhalten (sessions/{id}/create + sessions/{id}/delete-Events).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Rail wieder leer — Sitzung weg" },
  ] }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
