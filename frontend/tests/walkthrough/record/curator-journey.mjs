// Walkthrough recording: curator-journey
// The full curator end-to-end journey: log in as a curator (role gate in
// CuratorShell) → see the list of assigned documents → open one → read a
// source element → page through elements (Next / j-k) → write a question
// against the current element and submit it ("Senden").
//
// Setup provisions a throwaway curator via the admin API and assigns it to
// the test doc. Cleanup deprecates the question, un-assigns and revokes the
// curator so re-runs stay pristine.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const ADMIN_TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";
const CURATOR_Q = "Worin unterscheiden sich Cross-Validation und Bootstrap bei der Fehlerschätzung?";

// 1) Provision a curator via admin + assign to the doc.
async function provisionCurator() {
  const r = await fetch(`${API}/api/admin/curators`, {
    method: "POST",
    headers: { "X-Auth-Token": ADMIN_TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ name: "walkthrough-journey-curator" }),
  });
  if (!r.ok) throw new Error(`create curator: ${r.status} ${await r.text()}`);
  const c = await r.json(); // { id, name, token, token_prefix, created_at }
  const ar = await fetch(`${API}/api/admin/docs/${SLUG}/curators`, {
    method: "POST",
    headers: { "X-Auth-Token": ADMIN_TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ curator_id: c.id }),
  });
  if (!ar.ok) throw new Error(`assign curator: ${ar.status} ${await ar.text()}`);
  return c;
}
async function dropCurator(curatorId) {
  await fetch(`${API}/api/admin/docs/${SLUG}/curators/${curatorId}`, {
    method: "DELETE",
    headers: { "X-Auth-Token": ADMIN_TOKEN },
  }).catch(() => {});
  await fetch(`${API}/api/admin/curators/${curatorId}`, {
    method: "DELETE",
    headers: { "X-Auth-Token": ADMIN_TOKEN },
  }).catch(() => {});
}

const curator = await provisionCurator();
console.log("Provisioned curator:", curator.id);

// Read the curator-visible element list with the curator token so the
// element_id we target matches exactly what the UI renders.
const elsR = await fetch(`${API}/api/curate/docs/${SLUG}/elements`, {
  headers: { "X-Auth-Token": curator.token },
});
const elements = elsR.ok ? await elsR.json() : [];
const target = elements.find(e => e.element_type === "paragraph") ?? elements[1] ?? elements[0];
console.log("Elements:", elements.length, "→ target:", target?.element_id);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

// Confirm-dialog auto-accept guard for any window.confirm() during the run.
page.on("dialog", d => d.accept().catch(() => {}));

// Prime the curator session (token + role=curator gate the CuratorShell).
await page.goto(`${BASE}/`);
await page.evaluate(({ t, n }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "curator");
  sessionStorage.setItem("goldens.name", n);
}, { t: curator.token, n: curator.name });

const rec = new Recorder("curator-journey", BASE);

// Step 1: Curator shell + assigned-document list (role gate).
await page.goto(`${BASE}/#/curate`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(1800);
await rec.step(page, "Kurator-Login: Liste „Meine zugewiesenen Dokumente“", {
  actions: ["set sessionStorage goldens.role=curator", "goto /#/curate"],
  notes: [
    "Rollen-Gate: CuratorShell rendert nur bei role===\"curator\" — sonst Redirect nach /login. Das Token allein reicht nicht, die Rolle muss passen.",
    "BAM-Reskin: helle Canvas, weißer Header mit BAM-Mark + GOLDENS-Lockup und Cyan-Hairline; links die schmale Icon-Schiene (nur „Meine Dokumente“ für Kuratoren).",
    "Der Kurator sieht ausschließlich Dokumente, die ein Admin via POST /api/admin/docs/{slug}/curators zugewiesen hat — hier genau das eine Test-Doc.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'h1:has-text("Meine zugewiesenen Dokumente")', text: "Zugewiesene Dokumente" },
    { kind: "highlight", selector: 'a:has-text("öffnen")', text: "Doc öffnen" },
    { kind: "highlight", selector: 'nav[aria-label="Hauptnavigation"]', text: "Icon-Schiene (Meine Dokumente)" },
  ] }],
});

// Step 2: Open the doc — first source element + question input.
await page.locator('a:has-text("öffnen")').first().click().catch(() => {});
await page.waitForTimeout(400);
await page.goto(`${BASE}/#/curate/doc/${SLUG}`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2000);
await rec.step(page, "Doc geöffnet — Quell-Element lesen", {
  actions: ['click a:has-text("öffnen")', `goto /#/curate/doc/${SLUG}`],
  notes: [
    "Die Doc-Page zeigt jeweils EIN Quell-Element (data-Konvention: element-basiert, ein Element nach dem anderen) in einer hellen card: Seitenzahl, element_id (monospace) und der Element-Text.",
    "Quelle ist read_source_elements (die Source-Paragraphen aus der Extraktion), nicht die Chunks — Kurator-Fragen referenzieren stabile Quell-Elemente.",
    "Unten die Eingabe „Neue Frage“ mit Cyan-„Senden“-Button — hier formuliert der Kurator eine eigene Frage zum gezeigten Element.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: "article.card", text: "Aktuelles Quell-Element" },
    { kind: "highlight", selector: 'input[aria-label="Frage zu diesem Element"]', text: "Frage-Eingabe" },
  ] }],
});

// Step 3: Page to the next element via the Next button (j/k also work).
await page.locator('button:has-text("Next")').click().catch(() => {});
await page.waitForTimeout(900);
await rec.step(page, "Durch die Elemente blättern — „Next“ (oder Taste j/k)", {
  actions: ['click button:has-text("Next")'],
  notes: [
    "„Prev“ / „Next“ (btn-secondary) blättern durch die Element-Liste; die URL wird zu /curate/doc/{slug}/element/{element_id}, sodass jedes Element eine eigene Adresse hat.",
    "Tastatur-Shortcuts: j = nächstes Element, k = vorheriges (außer der Fokus liegt in einem Eingabefeld). Schnelles Durchsehen ohne Maus.",
    "Am Listenrand sind die Buttons disabled (kein Prev am ersten, kein Next am letzten Element).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button:has-text("Next")', text: "Nächstes Element" },
    { kind: "highlight", selector: 'button:has-text("Prev")', text: "Vorheriges Element" },
  ] }],
});

// Step 4: Navigate to the chosen target element and write + submit a question.
if (target?.element_id) {
  await page.goto(`${BASE}/#/curate/doc/${SLUG}/element/${target.element_id}`);
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1200);
}
await page.locator('input[aria-label="Frage zu diesem Element"]').fill(CURATOR_Q).catch(() => {});
await page.waitForTimeout(400);
await rec.step(page, "Kuratieren: eigene Frage formulieren", {
  actions: [
    `goto /#/curate/doc/${SLUG}/element/${target?.element_id}`,
    'fill input[aria-label="Frage zu diesem Element"]',
  ],
  notes: [
    `Ziel-Element: ${target?.element_id ?? "?"} (Seite ${target?.page_number ?? "?"}, Typ ${target?.element_type ?? "?"}).`,
    `Eingetippte Frage: „${CURATOR_Q}“`,
    "Der „Senden“-Button (btn-primary, BAM-Cyan) ist disabled, solange das Feld leer ist — sobald Text drinsteht, wird er aktiv.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'input[aria-label="Frage zu diesem Element"]', text: "Frage eingegeben" },
    { kind: "highlight", selector: 'button:has-text("Senden")', text: "Senden (jetzt aktiv)" },
  ] }],
});

// Step 5: Submit → POST /api/curate/docs/{slug}/questions, toast confirms.
let postedQuestionId = null;
await page.locator('button:has-text("Senden")').click().catch(() => {});
await page.waitForTimeout(1500);
// Resolve the created question_id for cleanup (curator-side listing).
const qListR = await fetch(
  `${API}/api/curate/docs/${SLUG}/questions?element_id=${encodeURIComponent(target?.element_id ?? "")}`,
  { headers: { "X-Auth-Token": curator.token } },
).catch(() => null);
if (qListR && qListR.ok) {
  const qs = await qListR.json();
  const mine = qs.find(q => q.query === CURATOR_Q);
  postedQuestionId = mine?.question_id ?? null;
}
await rec.step(page, "Frage absenden → gespeichert (POST /curate/.../questions)", {
  actions: ['click button:has-text("Senden")', `POST /api/curate/docs/${SLUG}/questions`],
  notes: [
    "Klick auf „Senden“ feuert POST /api/curate/docs/{slug}/questions mit { element_id, query }; der Server vergibt eine question_id und legt sie im Kurator-Bucket ab (getrennt von den Admin-/LLM-Fragen).",
    "Bei Erfolg erscheint der Toast „Frage gespeichert“, das Eingabefeld wird geleert und die Element-Liste neu geladen.",
    postedQuestionId ? `Neue question_id: ${postedQuestionId.slice(0, 8)}…` : "question_id für Cleanup nicht aufgelöst.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Toast „Frage gespeichert“ — Eingabe geleert, bereit fürs nächste Element" },
  ] }],
});

// Cleanup: deprecate the test question, then un-assign + revoke the curator.
if (postedQuestionId) {
  await fetch(`${API}/api/curate/docs/${SLUG}/questions/${postedQuestionId}/deprecate`, {
    method: "POST",
    headers: { "X-Auth-Token": curator.token, "Content-Type": "application/json" },
    body: JSON.stringify({ reason: "walkthrough cleanup" }),
  }).catch(() => {});
}
await dropCurator(curator.id);
console.log("Cleaned up: question deprecated, curator un-assigned + revoked.");

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
