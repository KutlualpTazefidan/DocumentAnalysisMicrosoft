// Walkthrough recording: synthese-deprecate
// Tour deprecating a generated question that's not suitable (e.g.,
// references content outside the box, redundant with another, off-topic).
// The entry stays in the audit log but is excluded from /questions reads
// and from the next export — clean retire, not hard delete.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

async function getQuestions() {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/questions`, { headers: { "X-Auth-Token": TOKEN } });
  const j = r.ok ? await r.json() : {};
  const all = [];
  if (Array.isArray(j)) all.push(...j);
  else for (const [boxId, qs] of Object.entries(j)) {
    if (Array.isArray(qs)) qs.forEach(q => all.push({ ...q, box_id: boxId }));
  }
  return all;
}
// Don't touch any pre-existing questions: generate ONE fresh question on a
// box that doesn't have one yet, deprecate only that. Pre-existing seeded
// questions survive the recording so manual exploration in the UI keeps
// its data.
async function ensureFreshQuestion() {
  const existing = await getQuestions();
  const existingBoxIds = new Set(existing.map(q => q.box_id));
  const segR = await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": TOKEN } });
  const seg = await segR.json();
  const candidates = seg.boxes.filter(b => b.kind === "paragraph" && !existingBoxIds.has(b.box_id));
  if (!candidates.length) throw new Error("no fresh paragraph box available");
  // Try a few candidates until one accepts. MinerU returns skipped_reason
  // for boxes that are headings (no_sub_units) or duplicate the existing pool.
  for (const target of candidates.slice(0, 8)) {
    const r = await fetch(`${API}/api/admin/docs/${SLUG}/synthesise?box_id=${encodeURIComponent(target.box_id)}`, {
      method: "POST",
      headers: { "X-Auth-Token": TOKEN },
    });
    if (!r.ok) continue;
    const result = await r.json();
    if ((result.accepted ?? 0) > 0) {
      const after = await getQuestions();
      const fresh = after.find(q => q.box_id === target.box_id);
      if (fresh) {
        console.log("Fresh question on", target.box_id, "→", fresh.entry_id || fresh.question_id);
        return fresh;
      }
    } else {
      console.log("Skipped", target.box_id, "—", result.skipped_reason);
    }
  }
  throw new Error("could not synthesise a fresh question on any candidate box");
}

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

const target = await ensureFreshQuestion();
const QID = target.entry_id || target.question_id;
console.log("Target to deprecate:", QID);

const rec = new Recorder("synthese-deprecate", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/synthesise`);
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2500);

await rec.step(page, `Fragen-Liste — Ziel zum Verwerfen: ${QID}`, {
  actions: [`goto /admin/doc/${SLUG}/synthesise`],
  notes: [
    "„Verwerfen“ / „Löschen“-Button setzt die Frage auf deprecated — sie bleibt im Event-Log (Audit-Trail), erscheint aber nicht mehr in /questions und nicht im Export.",
    "Sanftes Retire statt Hard-Delete — Goldens-Datenstand bleibt rekonstruierbar.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: `Frage ${QID} ist Kandidat zum Verwerfen` },
  ] }],
});

// Deprecate via API (UI button calls DELETE under the hood)
const r = await fetch(`${API}/api/admin/docs/${SLUG}/questions/${QID}`, {
  method: "DELETE",
  headers: { "X-Auth-Token": TOKEN },
});
const dep = r.ok ? await r.json().catch(()=>({ok:true})) : null;
await page.reload();
await page.waitForLoadState("networkidle").catch(()=>{});
await page.waitForTimeout(2000);
await rec.step(page, "DELETE /questions/{id} → deprecated-Flag gesetzt", {
  actions: [`DELETE /api/admin/docs/${SLUG}/questions/${QID}`],
  notes: [
    "Server schreibt ein deprecate-Event in das Doc-Event-Log und entfernt den Eintrag aus der active-Liste.",
    "Frage verschwindet aus der UI-Liste sofort nach react-query-Invalidation.",
    "Reversibel ist das nicht über die UI — Audit-Trail im Event-Log lässt es aber lückenlos nachverfolgen.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: dep ? "Deprecate-Aufruf erfolgreich" : "Deprecate fehlgeschlagen" },
  ] }],
});

const qs2 = await getQuestions();
const stillThere = qs2.find(q => (q.entry_id || q.question_id) === QID);
await rec.step(page, stillThere ? "❌ Frage taucht weiter auf" : "✓ Frage aus der aktiven Liste raus", {
  actions: ["GET /questions", "verify question_id absent"],
  notes: [
    stillThere
      ? "Frage ist noch in der Liste — Deprecate hat nicht gegriffen."
      : "Frage ist aus der aktiven Liste verschwunden. Audit-Eintrag bleibt im Event-Log.",
    `Verbleibende Q&A nach Deprecate: ${qs2.length}`,
  ],
  shots: [],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
