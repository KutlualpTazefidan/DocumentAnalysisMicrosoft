// Walkthrough recording: synthese-box-select
// Tour the box-selection mechanism inside the Synthese view: the HTML
// preview lives in an iframe, each MinerU element is a clickable
// [data-source-box] target, click → app receives the box_id → middle
// panel + right sidebar update + iframe paints the active outline.
//
// We click two distinct boxes back-to-back: one with existing Q&A
// (questions populate) and one without (empty-state + Generate-CTA).

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
  return r.ok ? await r.json() : {};
}
async function findTargets() {
  const seg = await (await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": TOKEN } })).json();
  const qs = await getQuestions();
  const withQ = Object.keys(qs);
  // Both targets on page 2 so we don't need to navigate twice mid-recording.
  const paragraphs2 = seg.boxes.filter(b => b.kind === "paragraph" && b.page === 2);
  const withTarget = paragraphs2.find(b => withQ.includes(b.box_id));
  const withoutTarget = paragraphs2.find(b => !withQ.includes(b.box_id));
  return { withTarget, withoutTarget };
}

const { withTarget, withoutTarget } = await findTargets();
if (!withTarget || !withoutTarget) throw new Error("need at least one paragraph each (with & without questions) on page 2");
console.log("Targets — with Q&A:", withTarget.box_id, "· without:", withoutTarget.box_id);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const rec = new Recorder("synthese-box-select", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/synthesise`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2000);

// Navigate to page 2 (page with questions).
await page.locator('[data-testid="synth-page-next"]').click();
await page.waitForTimeout(900);

// ── Step 1: Vor dem Klick — Auswahl-Panel leer, Aktionen disabled ─────────
await rec.step(page, "Seite 2 geöffnet — keine Box gewählt, Aktionen disabled", {
  actions: [`goto /admin/doc/${SLUG}/synthesise`, "navigate to page 2"],
  notes: [
    "HTML-Vorschau (iframe links) zeigt den extrahierten Text der aktuellen Seite — jede MinerU-Box bekommt ein eigenes Element mit data-source-box=<box_id>.",
    "Initial-State: kein highlight, mittleres Panel zeigt den Klicken-Hinweis, rechte „Ausgewählte Box“-Sektion ist leer, „Fragen für diese Box generieren“ ist disabled.",
    "Selektion ist Voraussetzung für Box-spezifische Aktionen (Generate / Antworten / Remove-Duplicates auf Box-Ebene).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button[aria-label="Fragen für diese Box generieren"]', text: "Disabled solange keine Auswahl" },
  ] }],
});

// ── Step 2: Klick auf eine Box mit bestehenden Q&A ────────────────────────
const frame = page.frameLocator("iframe");
await frame.locator(`[data-source-box="${withTarget.box_id}"]`).first().click();
await page.waitForTimeout(900);
const withCount = (await getQuestions())[withTarget.box_id]?.length ?? 0;
await rec.step(page, `Box ${withTarget.box_id} angeklickt → ${withCount} Fragen erscheinen`, {
  actions: [`click iframe [data-source-box="${withTarget.box_id}"]`],
  notes: [
    "Klick-Event im iframe wird vom Document-Listener gefangen, t.closest('[data-source-box]') liest die box_id und sendet sie via onClickElement nach oben in die React-App.",
    "Visueller Effekt im iframe: angeklicktes Element bekommt die is-highlighted-Klasse → blauer 2px-Outline + helles Hintergrundtint.",
    "App-State: highlight=<box_id> → mittleres Panel rendert die questions-Liste der Box, rechtes Panel zeigt Box-Eigenschaften (Tag, Vorschau-Text, Q&A-Zähler).",
    `Diese Box hat ${withCount} bestehende Q&A-Pairs aus früheren Generate-Läufen.`,
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="synthesise-questions"]', text: "Q&A-Liste für die aktive Box" },
    { kind: "note", text: `Box-Eigenschaften: ${withTarget.box_id} · paragraph · ${withCount} Fragen` },
  ] }],
});

// ── Step 3: Klick auf eine Box ohne Q&A → Empty-State + Generate-CTA ──────
await frame.locator(`[data-source-box="${withoutTarget.box_id}"]`).first().click();
await page.waitForTimeout(900);
await rec.step(page, `Wechsel zu ${withoutTarget.box_id} — leeres Q&A-Panel, Generate-CTA aktiv`, {
  actions: [`click iframe [data-source-box="${withoutTarget.box_id}"]`],
  notes: [
    "Neue Auswahl löst dieselbe Sequenz aus: highlight-Klasse wandert, App-State setzt sich auf die neue box_id, Panels re-rendern.",
    "Diese Box hat noch keine Q&A → mittleres Panel zeigt „0 Fragen“ + Hinweis-Karte; rechts ist „Fragen für diese Box generieren“ aktiv (Single-Click würde den Generate-Workflow auslösen — siehe synthese-generate).",
    "Vorherige Auswahl ist im iframe entmarkiert (is-highlighted-Klasse entfernt) → immer nur eine aktive Box gleichzeitig.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button[aria-label="Fragen für diese Box generieren"]', text: "Jetzt aktiv für die neue Box" },
    { kind: "note", text: `Box-Eigenschaften: ${withoutTarget.box_id} · paragraph · 0 Fragen` },
  ] }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
