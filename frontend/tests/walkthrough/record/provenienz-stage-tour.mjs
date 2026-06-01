// Walkthrough recording: provenienz-stage-tour
// Big-picture tour of the Provenienz UI: ViewToggle (Sitzungen/Agent),
// left rail with session list, central canvas (DAG of nodes), right
// inspector. Setup creates one demo session via API so the canvas shows
// something meaningful, cleanup removes it.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

async function createSession() {
  const seg = await (await fetch(`${API}/api/admin/docs/${SLUG}/segments`, { headers: { "X-Auth-Token": TOKEN } })).json();
  const root = seg.boxes.find(b => b.kind === "paragraph" && b.page === 2);
  const r = await fetch(`${API}/api/admin/provenienz/sessions`, {
    method: "POST",
    headers: { "X-Auth-Token": TOKEN, "Content-Type": "application/json" },
    body: JSON.stringify({ slug: SLUG, root_chunk_id: root.box_id }),
  });
  return r.json();
}
async function deleteSession(sid) {
  await fetch(`${API}/api/admin/provenienz/sessions/${sid}`, {
    method: "DELETE", headers: { "X-Auth-Token": TOKEN },
  }).catch(() => {});
}

const session = await createSession();
console.log("Demo session:", session.session_id);

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
const page = await ctx.newPage();
await page.goto(`${BASE}/`);
await page.evaluate(({ t }) => {
  sessionStorage.setItem("goldens.api_token", t);
  sessionStorage.setItem("goldens.role", "admin");
  sessionStorage.setItem("goldens.name", "probe");
}, { t: TOKEN });

const rec = new Recorder("provenienz-stage-tour", BASE);

// ── Step 1: Provenienz-Tab geöffnet — Drei-Spalten-Layout ─────────────────
await page.goto(`${BASE}/#/admin/doc/${SLUG}/provenienz`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2500);
await rec.step(page, "Provenienz-Tab — Drei-Spalten-Layout (Rail · Canvas · Inspector)", {
  actions: [`goto /admin/doc/${SLUG}/provenienz`],
  notes: [
    "Provenienz ist die forensische Sicht auf das LLM-Reasoning: jede Sitzung sammelt einen Graphen aus Chunks, Claims, Tasks, Search-Results, Evaluations.",
    "Layout: linkes Rail listet alle Sitzungen für das Dokument; mittlere Spalte zeigt den DAG der aktiven Sitzung; rechtes Panel ist der Knoten-Inspector.",
    "Oben in der Sub-Topbar: ViewToggle „Sitzungen“ (Sitzungs-Modus, gerade aktiv) vs. „Agent“ (Registries-Modus — Steps/Werkzeuge/Fähigkeiten/Wünsche).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'nav button:has-text("Sitzungen")', text: "View-Toggle (Sitzungen aktiv)" },
  ] }],
});

// ── Step 2: Sitzungs-Liste im linken Rail ─────────────────────────────────
await page.waitForTimeout(500);
await rec.step(page, "Linkes Rail: Sitzungs-Liste für das Dokument", {
  actions: ["observe left rail"],
  notes: [
    "Pro Sitzung ein Eintrag mit Wurzel-Chunk-ID, Status (open/closed) + Zeitstempel.",
    "Klick auf einen Eintrag selektiert die Sitzung → Canvas und Inspector aktualisieren sich.",
    "„Neu“-Button öffnet den ChunkPicker für eine frische Sitzung (siehe Slot 2 „Sitzung anlegen/löschen“).",
    `Aktuelle Demo-Sitzung mit Wurzel-Chunk ${session.root_chunk_id}.`,
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Sitzungs-Rail — pro Eintrag Klick selektiert" },
  ] }],
});

// ── Step 3: Canvas mit dem DAG ────────────────────────────────────────────
await rec.step(page, "Canvas — DAG der Sitzung (hier: nur der Wurzel-Chunk)", {
  actions: ["observe central canvas"],
  notes: [
    "Cytoscape-Layout: Knoten = Reasoning-Schritte (chunk/claim/task/search_result/plan_proposal/…), Kanten = Eltern-Kind-Beziehung.",
    "Frisch angelegte Sitzung hat genau 1 Knoten — den Wurzel-Chunk. Spätere Iterationen (siehe Slot 3 „AI-Vorschlag → Anwenden“) hängen weitere Knoten daran.",
    "Klick auf einen Knoten öffnet das passende Panel im rechten Inspector (ChunkPanel/ClaimPanel/TaskPanel/…).",
    "Doppelklick + Drag erlaubt manuelles Re-Layout; Scroll zoomt.",
  ],
  shots: [{ annotations: [
    { kind: "note", text: "Canvas zeigt den Wurzel-Chunk als einzigen Knoten" },
  ] }],
});

// ── Step 4: Wechsel auf Agent-View ────────────────────────────────────────
await page.locator('nav button:has-text("Agent")').click();
await page.waitForTimeout(1000);
await rec.step(page, "Wechsel auf Agent-View — Orchestrator-Topologie + Tab-Bar", {
  actions: ['click nav button "Agent"'],
  notes: [
    "Agent-View ist die Live-Sicht auf den Reasoning-Apparat: Orchestrator oben, gerade aktiver Sub-Agent mit seinen Skills (orange) und Werkzeugen (cyan).",
    "Rechts: Tab-Bar mit 5 Tabs — Auswahl (Detail des selektierten Pills/Knotens), Schritte (Step-Registry), Werkzeuge (Tool-Registry), Fähigkeiten (Skill-Library), Wünsche (Capability-Requests).",
    "Header zeigt Modell-Backend + Modell-Name + Architektur-Erklärung (Orchestrator wählt Sub-Agent, Sub-Agent trägt Skills + Werkzeuge inline).",
    "Datenfluss-Linie unten (Chunk → Claim → Task → …) ist gedimmt — sekundär zur Agent-Topologie.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'nav button:has-text("Agent")', text: "Agent-Modus aktiv" },
  ] }],
});

// ── Step 5: Zurück zu Sitzungen-View — Kreis schließt sich ────────────────
await page.locator('nav button:has-text("Sitzungen")').click();
await page.waitForTimeout(800);
await rec.step(page, "Zurück zur Sitzungs-View — beide Views sind komplementär", {
  actions: ['click nav button "Sitzungen"'],
  notes: [
    "Sitzungen-View = was wurde gedacht? (forensische Sicht auf das Reasoning-DAG eines konkreten Dokuments).",
    "Agent-View = wie wird gedacht? (Registries + Orchestrator-Topologie, doc-agnostisch).",
    "Im Alltag startet man in der Sitzungen-View an einem Chunk, lässt sich vom Agent eine Aktion vorschlagen und durchläuft die Iteration — siehe Slot 3 „AI-Vorschlag → Anwenden“.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'nav button:has-text("Sitzungen")', text: "Sitzungen-Modus wieder aktiv" },
  ] }],
});

await deleteSession(session.session_id);
console.log("Demo session cleaned up.");

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
