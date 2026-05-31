// Walkthrough recording: synthese-edit-answer
// Tour overwriting an LLM-generated answer with the admin's own text.
// Prereq: at least one generated question with an answer (we ensure this
// at setup by triggering a per-box synthesise if /questions is empty).

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";
const OWN_ANSWER = "Eine vom Admin überschriebene Antwort — gilt als finale Wahrheit für diesen Eintrag.";

async function getQuestions() {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/questions`, { headers: { "X-Auth-Token": TOKEN } });
  const j = r.ok ? await r.json() : {};
  // Flatten across box_ids
  const all = [];
  if (Array.isArray(j)) all.push(...j);
  else for (const [boxId, qs] of Object.entries(j)) {
    if (Array.isArray(qs)) qs.forEach(q => all.push({ ...q, box_id: boxId }));
  }
  return all;
}
async function ensureQuestion() {
  let qs = await getQuestions();
  if (qs.length > 0) return qs[0];
  // Need to generate one for a known box.
  const segR = await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": TOKEN } });
  const seg = await segR.json();
  const para = seg.boxes.find(b => b.page === 1 && b.kind === "paragraph");
  if (!para) throw new Error("no paragraph box on page 1");
  console.log("Generating Q&A for", para.box_id, "...");
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/synthesise?box_id=${encodeURIComponent(para.box_id)}`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN },
  });
  if (!r.ok) throw new Error(`synthesise failed: ${r.status} ${await r.text()}`);
  await r.json();
  qs = await getQuestions();
  return qs[0];
}

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const target = await ensureQuestion();
console.log("Target question:", target.entry_id || target.question_id, "box:", target.box_id);
const QID = target.entry_id || target.question_id;
const originalAnswer = target.answer ?? "";

const rec = new Recorder("synthese-edit-answer", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/synthesise`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2500);

// Step 1: Question liste sichtbar, original Antwort markiert
await rec.step(page, `Synthese-Liste mit generierten Fragen — Ziel: ${QID}`, {
  actions: [`goto /admin/doc/${SLUG}/synthesise`],
  notes: [
    "Pro Frage zeigt der Eintrag: Frage-Text, generierte Antwort, Box-Pin (springt zur Quelle), Bearbeiten/Verfeinern/Löschen-Aktionen.",
    "Antworten kommen vom LLM auf Basis der Quell-Box. Der Admin kann sie hier durch eigene Texte ersetzen.",
    `Original-Antwort: „${originalAnswer.slice(0,80)}…“`,
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Ziel-Eintrag: ${QID}` },
  ] }],
});

// Step 2: PATCH answer via API (UI uses a contentEditable field; simpler+more reliable via API)
const r = await fetch(`${API}/api/admin/docs/${SLUG}/answers/${QID}`, {
  method: "PATCH",
  headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
  body: JSON.stringify({ text: OWN_ANSWER }),
});
const patched = r.ok ? await r.json() : null;
await page.reload();
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2000);
await rec.step(page, "Eigene Antwort einsetzen → PATCH /answers/{entry_id}", {
  actions: [`PATCH /api/admin/docs/${SLUG}/answers/${QID} body={text: own-text}`],
  notes: [
    "Im echten UI: Klick in das Antwort-Feld → tippen → Blur löst PATCH automatisch aus.",
    "Server schreibt die neue Antwort in den answers-Sidecar. /questions invalidiert react-query → Liste rendert die neue Antwort sofort.",
    "Die ursprüngliche LLM-Antwort wird überschrieben — nicht versioniert (für Audit-Trail siehe Provenienz-Sitzung).",
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Neue Antwort: „${OWN_ANSWER.slice(0,60)}…“` },
  ] }],
});

// Step 3: Verify the new answer is in the questions list
const qs2 = await getQuestions();
const updated = qs2.find(q => (q.entry_id || q.question_id) === QID);
const matches = updated?.answer === OWN_ANSWER;
await rec.step(page, matches ? "Reload bestätigt: eigene Antwort in der Liste" : "Antwort-Update nicht verifiziert", {
  actions: ["GET /questions", "compare answer field"],
  notes: [
    matches
      ? "Die Antwort steht jetzt im Server-State. Beim nächsten Export-Lauf landet sie in den Goldens-Daten."
      : "Antwort-Update nicht in der Liste sichtbar.",
    `Live answer in /questions: „${(updated?.answer ?? "").slice(0,80)}…“`,
  ],
  shots: [{ annotations: [
    { kind: "note", text: matches ? "PATCH ✓ persistiert" : "Diff ✗" },
  ] }],
});

// Cleanup — restore the original LLM answer
if (originalAnswer) {
  await fetch(`${API}/api/admin/docs/${SLUG}/answers/${QID}`, {
    method: "PATCH",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ text: originalAnswer }),
  });
  console.log("Original answer restored.");
}

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
