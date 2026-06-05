// Walkthrough recording: statistik-voting
// Tour the Reviewer-Voting flow end-to-end: on the Synthese tab we
// approve one generated question and reject another (left-stripe colour
// + vote-count line react live), then jump to the Statistik tab to see
// those votes roll up into the weighted dashboards — the two MetricGauge
// radials (Curator-Überleben, Reviewer-Zustimmung) and the
// VoteDistributionBar stacked bar (approved=green / rejected=red per
// question). Finally we return to Synthese to show the stripes persist
// across tab navigation (votes are backend state, re-queried on mount).
//
// Voting writes backend state, so we snapshot each touched question's
// original my_vote up-front and restore it at the end (revoke when it
// was unvoted) — re-runs stay pristine, mirroring extract-box-merge's
// unmerge cleanup.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

// ── Setup: find a box that already has ≥2 active questions ───────────
// Questions come back keyed by box_id (Record<box_id, Question[]>); we
// vote on the first two of whichever box has the most, and we derive
// the box's page from the box_id (pN-bM) so we can navigate to it.
async function getQuestions() {
  const r = await fetch(`${API}/api/admin/docs/${SLUG}/questions`, {
    headers: { "X-Auth-Token": TOKEN },
  });
  return r.ok ? await r.json() : {};
}

async function setVote(entryId, action) {
  // action: "approved" | "rejected" | "revoked"
  const r = await fetch(
    `${API}/api/admin/docs/${SLUG}/questions/${encodeURIComponent(entryId)}/vote`,
    {
      method: "POST",
      headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    },
  );
  if (!r.ok) console.log(`vote ${action} on ${entryId} failed:`, r.status, await r.text());
  return r.ok;
}

const byBox = await getQuestions();
const bestBox = Object.entries(byBox)
  .filter(([, qs]) => Array.isArray(qs) && qs.length >= 2)
  .sort((a, b) => b[1].length - a[1].length)[0];
if (!bestBox) throw new Error("need a box with ≥2 generated questions on this slug");
const [boxId, boxQs] = bestBox;
const q1 = boxQs[0];
const q2 = boxQs[1];
const pageMatch = boxId.match(/^p(\d+)-/);
const boxPage = pageMatch ? parseInt(pageMatch[1], 10) : 1;
// Snapshot original votes so cleanup can restore them.
const orig1 = q1.vote_summary?.my_vote ?? null;
const orig2 = q2.vote_summary?.my_vote ?? null;
console.log(`Voting box ${boxId} (page ${boxPage}) · q1=${q1.entry_id} q2=${q2.entry_id}`);
console.log(`Original votes — q1:${orig1 ?? "none"} q2:${orig2 ?? "none"}`);

// The vote buttons TOGGLE on current my_vote (approved→revoked, etc.).
// Normalize both targets to unvoted before the demo so the UI clicks
// cleanly SET approved/rejected (and the stripes appear, not vanish).
// Cleanup below restores orig1/orig2 regardless.
if (orig1) await setVote(q1.entry_id, "revoked");
if (orig2) await setVote(q2.entry_id, "revoked");

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1400, height: 900 } });
const page = await ctx.newPage();

await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const rec = new Recorder("statistik-voting", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/synthesise`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2000);

// Navigate to the box's page via the page-grid (open toggle → click N),
// then click the box in the read-only HTML iframe so its questions show.
if (boxPage !== 1) {
  await page.locator('[data-testid="synth-page-grid-toggle"]').click();
  await page.waitForTimeout(400);
  await page.locator(`[data-testid="synth-page-btn-${boxPage}"]`).click();
  await page.waitForTimeout(900);
}
const frame = page.frameLocator('[data-testid="synth-html-preview"]');
await frame.locator(`[data-source-box="${boxId}"]`).first().click();
await page.waitForTimeout(900);

const card1 = page.locator(`[data-testid="question-${q1.entry_id}"]`);
const card2 = page.locator(`[data-testid="question-${q2.entry_id}"]`);

// ── Step 1: Synthese-Tab — generierte Fragen der Box, noch ungevotet ──
await rec.step(page, "Synthese-Tab: generierte Fragen der Box — Voting-Buttons sichtbar", {
  actions: [
    `goto /admin/doc/${SLUG}/synthesise`,
    boxPage !== 1 ? `navigate to page ${boxPage}` : "stay on page 1",
    `click iframe [data-source-box="${boxId}"]`,
  ],
  notes: [
    "Voting ist Box-scoped: erst ein Element in der HTML-Vorschau (iframe links) anklicken, dann erscheinen im mittleren Panel (data-testid=synthesise-questions) die Fragen dieser Box.",
    "Jede Fragenkarte trägt unten rechts zwei Icon-Buttons: grünes CheckCircle2 (aria-label „Einverstanden“) und rotes XCircle (aria-label „Disqualifizieren“).",
    "Ungevotet = linker Rand transparent (border-l-transparent), keine Stimmen-Zeile. Der Vote schreibt Backend-State (POST …/questions/{id}/vote) und invalidiert sowohl die Fragenliste als auch den Synthese-Statistik-Cache.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="synthesise-questions"]', text: "Fragenliste der aktiven Box" },
    { kind: "highlight", selector: `[data-testid="question-${q1.entry_id}"] button[aria-label="Einverstanden"]`, text: "Einverstanden (grün)" },
    { kind: "highlight", selector: `[data-testid="question-${q1.entry_id}"] button[aria-label="Disqualifizieren"]`, text: "Disqualifizieren (rot)" },
  ] }],
});

// ── Step 2: Erste Frage „Einverstanden“ → grüner Streifen ────────────
await card1.locator('button[aria-label="Einverstanden"]').click();
await page.waitForTimeout(900);
await rec.step(page, "Frage 1 „Einverstanden“ → smaragdgrüner Streifen + Stimmen-Zeile", {
  actions: [`click question-${q1.entry_id} → Einverstanden`],
  notes: [
    "Klick auf „Einverstanden“ setzt my_vote=approved. Sofort sichtbar: linker Kartenrand wird emerald-500 (3px), der Button selbst bekommt text-emerald-700 + bg-emerald-50 (aktiver Zustand).",
    "Unter der Karte erscheint die Stimmen-Zeile „N ✓ · M ✗“ (approved_count / rejected_count über alle Reviewer).",
    "Erneuter Klick würde revoken (toggle approved → revoked) — hier lassen wir die Zustimmung stehen.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: `[data-testid="question-${q1.entry_id}"]`, text: "Smaragd-Streifen = approved" },
    { kind: "highlight", selector: `[data-testid="question-${q1.entry_id}"] button[aria-label="Einverstanden"]`, text: "Aktiv: emerald-700 / bg-emerald-50" },
  ] }],
});

// ── Step 3: Zweite Frage „Disqualifizieren“ → roter Streifen ─────────
await card2.locator('button[aria-label="Disqualifizieren"]').click();
await page.waitForTimeout(900);
await rec.step(page, "Frage 2 „Disqualifizieren“ → roter Streifen + Stimmen-Zeile", {
  actions: [`click question-${q2.entry_id} → Disqualifizieren`],
  notes: [
    "Klick auf „Disqualifizieren“ setzt my_vote=rejected. Linker Rand wird red-500, der Button bekommt text-red-700 + bg-red-50.",
    "Die Stimmen-Zeile zeigt jetzt für diese Frage die Rejected-Seite — Format bleibt „N ✓ · M ✗“.",
    "Approve und Reject schließen sich aus: ein Klick auf den anderen Button würde umstimmen, ein Klick auf denselben revoken.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: `[data-testid="question-${q2.entry_id}"]`, text: "Roter Streifen = rejected" },
    { kind: "highlight", selector: `[data-testid="question-${q2.entry_id}"] button[aria-label="Disqualifizieren"]`, text: "Aktiv: red-700 / bg-red-50" },
  ] }],
});

// ── Step 4: Wechsel zum Statistik-Tab ────────────────────────────────
await page.locator('nav[role="tablist"] a:has-text("Statistik")').click();
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(1800);
await rec.step(page, "Statistik-Tab geöffnet — Sektionen Extrahieren · Synthese · Provenienz", {
  actions: ['click nav „Statistik" (BarChart3)', `goto /admin/doc/${SLUG}/statistics`],
  notes: [
    "Der Statistik-Tab (BarChart3-Icon) liegt auf /admin/doc/{slug}/statistics. Die Seite rendert drei Sektionen mit navy-Überschriften (text-bam-navy): Extrahieren, Synthese, Provenienz.",
    "Post-BAM-Reskin: heller Canvas (bg-white), dunkle Schrift (text-ink), Charts sitzen auf weißen Karten (kein dunkles Navy-Theme mehr).",
    "Der Vote-Mutation invalidiert den Cache-Key [\"stats\",\"synthese\",slug] — die Synthese-Sektion spiegelt also die soeben abgegebenen Stimmen.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'section:has(h2:has-text("Synthese"))', text: "Synthese-Statistik-Sektion" },
  ] }],
});

// ── Step 5: MetricGauge „Curator-Überleben" ──────────────────────────
await rec.step(page, "Synthese-Metrik: „Curator-Überleben“-Gauge (Fragen-Überlebensrate)", {
  actions: ["Synthese-Sektion: linke MetricGauge betrachten"],
  notes: [
    "Linker Radial-Gauge (Recharts RadialBar) zeigt „Curator-Überleben“ = (questions_created − questions_deprecated) / questions_created — der Untertitel nennt genau diesen Bruch.",
    "Füllfarbe wertabhängig: ≥70 % grün (success #006d00), 40–70 % cyan (accent #00aff0), <40 % rot (danger #d2001f); der Prozentwert steht unter dem Ring.",
    "Misst, wie viele generierte Fragen NICHT deprecated wurden — hoher Wert = wenig Kurations-Ausschuss.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'section:has(h2:has-text("Synthese")) div:has-text("Curator-Überleben")', text: "Curator-Überleben-Gauge" },
  ] }],
});

// ── Step 6: MetricGauge „Reviewer-Zustimmung" ────────────────────────
await rec.step(page, "Synthese-Metrik: „Reviewer-Zustimmung“-Gauge (Zustimmungsrate)", {
  actions: ["Synthese-Sektion: rechte MetricGauge betrachten"],
  notes: [
    "Rechter Gauge „Reviewer-Zustimmung“ = vote_approved / (vote_approved + vote_rejected); der Untertitel zeigt „approved / gesamt“.",
    "Spiegelt die soeben abgegebenen Stimmen: ein Approve (Frage 1) und ein Reject (Frage 2) fließen in approved_count bzw. rejected_count ein.",
    "Gleiche Farb-Schwellen wie Curator-Überleben (≥70 % grün, 40–70 % cyan, <40 % rot).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'section:has(h2:has-text("Synthese")) div:has-text("Reviewer-Zustimmung")', text: "Reviewer-Zustimmung-Gauge" },
  ] }],
});

// ── Step 7: VoteDistributionBar — Stimmen pro Frage ──────────────────
await page.locator('text=Stimmen pro Frage (Top 20)').scrollIntoViewIfNeeded().catch(() => {});
await page.waitForTimeout(500);
await rec.step(page, "Synthese-Metrik: „Stimmen pro Frage (Top 20)“ — gestapelter Balken", {
  actions: ["scroll zu VoteDistributionBar"],
  notes: [
    "VoteDistributionBar ist ein horizontaler Stacked-Bar (Recharts BarChart, layout=vertical). Eine Zeile pro Frage, sortiert nach Stimmenzahl, Top 20.",
    "Grünes Segment = approved (palette.success #006d00), rotes Segment = rejected (palette.danger #d2001f); die Y-Achse zeigt text_short (gekürzter Fragetext, max 180px).",
    "Höhe ist dynamisch (rows·28px, min 200) — die beiden eben gevoteten Fragen tauchen hier als Balkenzeilen auf. Tooltip beim Hover nennt die exakten Counts.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'section:has(h2:has-text("Synthese")):has-text("Stimmen pro Frage (Top 20)")', text: "VoteDistributionBar (approved=grün / rejected=rot)" },
  ] }],
});

// ── Step 8: Light-Theme-Check (Post-BAM-Reskin) ──────────────────────
await rec.step(page, "Post-BAM-Reskin: heller Canvas, navy Überschriften, cyane Akzente", {
  actions: ["Hintergründe + Schrift-Kontrast prüfen"],
  notes: [
    "Der BAM-Reskin hat das Frontend von dunkel auf hell gedreht: Canvas weiß (bg-white), Fließtext dunkle Tinte (text-ink).",
    "Sektions-Überschriften sind navy (text-bam-navy: Extrahieren / Synthese / Provenienz); Chart-Akzente nutzen BAM-Cyan #00aff0, Gauge/Bar-Hintergründe sind weiße Karten.",
    "Kein „Blau-Variant“ und keine dunklen Flächen mehr — Charts und Text bleiben durchgehend auf hellem Grund lesbar.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'div.flex.flex-col.h-full:has(h2.text-bam-navy)', text: "Heller Statistik-Container, navy Headings" },
  ] }],
});

// ── Step 9: Zurück zu Synthese — Stimmen persistieren ────────────────
await page.locator('nav[role="tablist"] a:has-text("Synthese")').click();
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(1500);
// Re-select the same box (highlight resets on remount) to show its cards.
if (boxPage !== 1) {
  await page.locator('[data-testid="synth-page-grid-toggle"]').click();
  await page.waitForTimeout(400);
  await page.locator(`[data-testid="synth-page-btn-${boxPage}"]`).click();
  await page.waitForTimeout(900);
}
await frame.locator(`[data-source-box="${boxId}"]`).first().click();
await page.waitForTimeout(900);
await rec.step(page, "Zurück im Synthese-Tab — Streifen + Stimmen-Zeilen bleiben erhalten", {
  actions: ['click nav „Synthese"', `re-select box ${boxId}`],
  notes: [
    "Vote-State ist Backend-State, nicht lokal: beim Re-Mount re-queryt die Fragenliste (/questions) inkl. frischem vote_summary.",
    "Frage 1 trägt weiter den emerald-500-Streifen (approved), Frage 2 den red-500-Streifen (rejected) — identisch zum Stand vor dem Statistik-Abstecher.",
    "Damit ist Voting ↔ Statistik konsistent: was hier gefärbt ist, ist dort gezählt.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: `[data-testid="question-${q1.entry_id}"]`, text: "Frage 1 weiterhin approved (smaragd)" },
    { kind: "highlight", selector: `[data-testid="question-${q2.entry_id}"]`, text: "Frage 2 weiterhin rejected (rot)" },
  ] }],
});

// ── Cleanup: restore each touched question's original vote ───────────
// We set approved on q1 and rejected on q2; revert to the snapshot so
// re-runs (and the live stats dashboards) stay pristine.
await setVote(q1.entry_id, orig1 ?? "revoked");
await setVote(q2.entry_id, orig2 ?? "revoked");
console.log("Restored votes to original snapshot.");

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
