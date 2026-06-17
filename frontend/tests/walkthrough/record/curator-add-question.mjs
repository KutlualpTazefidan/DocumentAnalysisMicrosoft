// Walkthrough recording: curator-add-question
// Tour the curator's „eigene Frage anlegen“ path. Setup creates a fresh
// curator account via admin (gets a token), assigns the curator to the
// test doc, then drives the curator UI to POST a new question.
// Cleanup removes the test question and the throwaway curator.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const ADMIN_TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";
const OWN_Q = "Welcher der zwei Verfahren liefert auf kleinen Stichproben die genauere Schätzung?";

// 1) Provision a curator + assign to the doc.
async function provisionCurator() {
  const r = await fetch(`${API}/api/admin/curators`, {
    method: "POST",
    headers: { "X-Auth-Token": ADMIN_TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ name: "walkthrough-test-curator" }),
  });
  if (!r.ok) throw new Error(`create curator: ${r.status} ${await r.text()}`);
  const c = await r.json();
  const ar = await fetch(`${API}/api/admin/docs/${SLUG}/curators`, {
    method: "POST",
    headers: { "X-Auth-Token": ADMIN_TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ curator_id: c.id }),
  });
  if (!ar.ok) throw new Error(`assign curator: ${ar.status} ${await ar.text()}`);
  return c; // { id, name, token, ... }
}
async function dropCurator(curatorId) {
  await fetch(`${API}/api/admin/docs/${SLUG}/curators/${curatorId}`, {
    method: "DELETE",
    headers: { "X-Auth-Token": ADMIN_TOKEN },
  }).catch(()=>{});
  await fetch(`${API}/api/admin/curators/${curatorId}`, {
    method: "DELETE",
    headers: { "X-Auth-Token": ADMIN_TOKEN },
  }).catch(()=>{});
}

const curator = await provisionCurator();
console.log("Provisioned curator:", curator.id);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

// Prime curator session via the curator-token path.
await page.goto(`${BASE}/`);
await page.evaluate(({ t, n }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "curator");
  sessionStorage.setItem("goldens.name", n);
  sessionStorage.setItem("goldens.tenant_name", "Fachbereich 3.3");
}, { t: curator.token, n: curator.name });

const rec = new Recorder("curator-add-question", BASE);

// Step 1: Curator-Shell + Doc-Liste
await page.goto(`${BASE}/#/curate/`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(1800);
await rec.step(page, "Kurator-Shell: Liste der zugewiesenen Dokumente", {
  actions: [`goto /curate/`],
  notes: [
    "Curator-Login leitet automatisch nach /curate/ (siehe useAuth-Logic).",
    "Curator sieht nur Dokumente, denen der Admin sie/ihn zugewiesen hat (per POST /api/admin/docs/{slug}/curators).",
    "Klick auf ein Doc öffnet die Curator-Doc-Page mit den Boxen + bestehenden Q&A.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Curator-Pseudonym: ${curator.name} (${curator.id.slice(0,8)}…)` },
  ] }],
});

// Step 2: Open the doc
await page.goto(`${BASE}/#/curate/doc/${SLUG}`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2000);
await rec.step(page, "Doc öffnen — Quell-Element auswählen für die neue Frage", {
  actions: [`goto /curate/doc/${SLUG}`],
  notes: [
    "Die Curator-UI zeigt Element-Liste + Eingabefeld für die eigene Frage.",
    "Jede Frage referenziert ein bestimmtes Element (element_id) — der Bezug zur Quell-Box bleibt nachvollziehbar.",
    "Vor dem POST: Curator wählt ein Element aus, formuliert die Frage selbst.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Curator-Doc-View — Element-Auswahl + Frage-Eingabe" },
  ] }],
});

// Step 3: POST the question via the curator-side endpoint
// Pick a paragraph element as target.
const segR = await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": ADMIN_TOKEN } });
const seg = await segR.json();
const para = seg.boxes.find(b => b.page === 1 && b.kind === "paragraph");
const elementId = para.box_id;
const postR = await fetch(`${API}/api/curate/docs/${SLUG}/questions`, {
  method: "POST",
  headers: { "X-Auth-Token": curator.token, "Content-Type": "application/json" },
  body: JSON.stringify({ element_id: elementId, query: OWN_Q }),
});
const newQ = postR.ok ? await postR.json() : null;
await page.reload();
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2000);
await rec.step(page, "Eigene Frage absenden → POST /curate/docs/{slug}/questions", {
  actions: [
    `POST /api/curate/docs/${SLUG}/questions`,
    `body={element_id:"${elementId}", query:"…"}`,
  ],
  notes: [
    `Curator-Frage: „${OWN_Q}“`,
    `Ziel-Element: ${elementId} (paragraph, Seite ${para.page}).`,
    "Server vergibt question_id, schreibt sie in curator-questions.json. Admin sieht sie nicht im /admin/questions (separater Bucket), sondern unter den Curator-Beiträgen.",
    "Refine / Deprecate funktionieren analog: POST /curate/.../questions/{id}/refine bzw. /deprecate.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: newQ?.question_id ? `Neue question_id: ${newQ.question_id.slice(0,8)}…` : "POST fehlgeschlagen" },
  ] }],
});

// Cleanup: remove the test question, curator-doc-assignment, and curator.
if (newQ?.question_id) {
  await fetch(`${API}/api/curate/docs/${SLUG}/questions/${newQ.question_id}/deprecate`, {
    method: "POST",
    headers: { "X-Auth-Token": curator.token, "Content-Type": "application/json" },
    body: JSON.stringify({ reason: "walkthrough cleanup" }),
  }).catch(()=>{});
}
await dropCurator(curator.id);
console.log("Curator + test question cleaned up.");

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
