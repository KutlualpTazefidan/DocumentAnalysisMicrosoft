// Walkthrough recording: synthese-generate
// End-to-end story of the box-scoped LLM generation: ensure vLLM is up,
// open Synthese, click a paragraph in the HTML-Vorschau (iframe), trigger
// „Fragen für diese Box generieren“, watch the questions populate.
// Cleanup deprecates only the test questions we generated.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

async function llmStatus() {
  const r = await fetch(`${API}/api/admin/llm/status`, { headers: { "X-Auth-Token": TOKEN } });
  return r.ok ? r.json() : null;
}
async function ensureLlmRunning() {
  let s = await llmStatus();
  if (s?.healthy) return s;
  if (s?.state === "stopped") {
    await fetch(`${API}/api/admin/llm/start`, { method: "POST", headers: { "X-Auth-Token": TOKEN } });
  }
  for (let i = 0; i < 30; i++) {
    s = await llmStatus();
    if (s?.healthy) return s;
    await new Promise(r => setTimeout(r, 5000));
  }
  throw new Error("vLLM didn't become healthy");
}

async function getQuestions() {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/questions`, { headers: { "X-Auth-Token": TOKEN } });
  return r.ok ? await r.json() : {};
}
async function findFreshBoxId() {
  const seg = await (await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": TOKEN } })).json();
  const qs = await getQuestions();
  const taken = new Set(Object.keys(qs));
  // Prefer page 3+ paragraphs so the recording shows navigation; large enough
  // text to make the LLM accept (no_sub_units skip).
  return seg.boxes.find(b => b.kind === "paragraph" && b.page >= 3 && !taken.has(b.box_id))?.box_id;
}

const targetBoxId = await findFreshBoxId();
if (!targetBoxId) throw new Error("no fresh paragraph box available");
const targetPage = parseInt(targetBoxId.match(/p(\d+)/)[1], 10);
console.log("Target box:", targetBoxId, "on page", targetPage);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const rec = new Recorder("synthese-generate", BASE);

// ── Step 1: vLLM-Status prüfen / starten ──────────────────────────────────
const llmBefore = await llmStatus();
await page.goto(`${BASE}/#/admin/doc/${SLUG}/synthesise`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(1800);
await rec.step(page, `Voraussetzung: vLLM verfügbar — Status „${llmBefore?.state}“`, {
  actions: ["GET /api/admin/llm/status"],
  notes: [
    "Synthese braucht ein laufendes LLM. Status-Pill oben (vLLM gestoppt/läuft) macht das sichtbar.",
    "Start/Stop-Buttons direkt in der Top-Bar — alternativ POST /api/admin/llm/start.",
    `Aktuelles Modell: ${llmBefore?.model ?? "—"}, base_url: ${llmBefore?.base_url ?? "—"}.`,
    "Erst wenn der Status auf „läuft“ steht, sind die Generate-Buttons im Synthese-Tab aktivierbar.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button:has-text("Start"), button:has-text("Stop")', text: "LLM-Start/Stop-Button" },
  ] }],
});
await ensureLlmRunning();

// ── Step 2: Navigate to target page, show empty middle panel ──────────────
for (let i = 1; i < targetPage; i++) {
  await page.locator('[data-testid="synth-page-next"]').click();
  await page.waitForTimeout(400);
}
await page.waitForTimeout(1000);
await rec.step(page, `Seite ${targetPage} geöffnet — mittleres Panel wartet auf Box-Klick`, {
  actions: [`navigate to page ${targetPage}`],
  notes: [
    "Mittleres Panel zeigt „Klicke ein Element im HTML-Bereich, um Fragen zu sehen“ — Box-Auswahl ist Voraussetzung.",
    "Linke Spalte = read-only HTML-Vorschau der aktuellen Seite (iframe, vom Server gelieferte html.html-Slice).",
    "Rechts: vLLM-Status, Seiten-Navigation, „Diese Seite sperren“, Box-Eigenschaften (noch leer).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Auf Seite ${targetPage} (über ▶-Buttons aus dem Page-Strip)` },
  ] }],
});

// ── Step 3: Click the target paragraph in the iframe ──────────────────────
const frame = page.frameLocator("iframe");
await frame.locator(`[data-source-box="${targetBoxId}"]`).first().click();
await page.waitForTimeout(800);
await rec.step(page, `Box ${targetBoxId} ausgewählt → Generate-Button aktiviert`, {
  actions: [`click iframe [data-source-box="${targetBoxId}"]`],
  notes: [
    "Klick auf einen Paragraf-Block im iframe sendet die box_id an die React-App.",
    "Rechtes Panel füllt sich: Box-ID, Tag-Badge („paragraph“), Vorschau-Text, Anzahl bestehender Fragen.",
    "„Fragen für diese Box generieren“ ist jetzt aktiv (vorher disabled solange keine Auswahl).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button[aria-label="Fragen für diese Box generieren"]', text: "Aktivierter Generate-Button" },
    { kind: "note", text: `Box-Eigenschaften zeigen ${targetBoxId}` },
  ] }],
});

// ── Step 4: Click "Fragen für diese Box generieren" → LLM stream ──────────
const beforeCount = (await getQuestions())[targetBoxId]?.length ?? 0;
await page.locator('button[aria-label="Fragen für diese Box generieren"]').click();
await page.waitForTimeout(800);
await rec.step(page, "Box-Generate gestartet — vLLM streamt", {
  actions: ['click button "Fragen für diese Box generieren"'],
  notes: [
    "POST /api/admin/docs/{slug}/synthesise?box_id={box_id} — Server ruft das LLM mit Box-Text als Kontext.",
    "Antwort als NDJSON-Stream: pro Frage ein Event, plus work-complete am Ende.",
    "Button switcht auf „…“ (Pending-Indikator), restliche Aktionen sind disabled solange der Lauf läuft.",
    "Typische Laufzeit: 5-15s für 4-6 Fragen pro Box (Qwen3-8B auf RTX 4090).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Generate-Button im Pending-State, Stream läuft" },
  ] }],
});

// Wait until questions show up
for (let i = 0; i < 40; i++) {
  const qs = await getQuestions();
  if ((qs[targetBoxId]?.length ?? 0) > beforeCount) break;
  await page.waitForTimeout(1500);
}
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(1500);
const newCount = (await getQuestions())[targetBoxId]?.length ?? 0;
const newQs = (await getQuestions())[targetBoxId] ?? [];

// ── Step 5: Generated questions visible in middle panel ───────────────────
await rec.step(page, `${newCount} Fragen für ${targetBoxId} sichtbar`, {
  actions: ["wait for stream completion", "react-query auto-rerenders questions panel"],
  notes: [
    `LLM hat ${newCount} Q&A-Pairs für ${targetBoxId} erzeugt — Liste rendert im mittleren Panel.`,
    "Pro Frage: Frage-Text, generierte Antwort, Box-Pin (springt zum Quell-Element), Verfeinern / Antwort-überschreiben / Verwerfen-Aktionen.",
    "Antworten kommen automatisch mit dem ersten Generate (Server ruft LLM für jede Frage auf den Box-Text an).",
    "Für eigene, manuell formulierte Fragen → siehe Kurator-Pfad „eigene Frage anlegen“: POST /api/curate/docs/{slug}/questions.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="synthesise-questions"]', text: `${newCount} neue Q&A im Panel` },
  ] }],
});

console.log("Generated questions for", targetBoxId, ":", newCount);

// Cleanup: deprecate only the questions WE generated, so pre-existing data
// and other freshly-generated questions outside our scope remain intact.
for (const q of newQs) {
  const qid = q.entry_id || q.question_id;
  if (!qid) continue;
  await fetch(`${API}/api/admin/docs/${SLUG}/questions/${qid}`, {
    method: "DELETE",
    headers: { "X-Auth-Token": TOKEN },
  }).catch(() => {});
}
console.log("Cleanup: deprecated", newQs.length, "test questions for", targetBoxId);

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
