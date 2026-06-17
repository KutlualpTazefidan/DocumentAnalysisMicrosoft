// Walkthrough recording: provenienz-agent-tour
// Tour the Agent-View: Orchestrator-Topologie im Canvas + 5 Tabs im
// rechten Panel (Auswahl, Schritte, Werkzeuge, Fähigkeiten, Wünsche).
// Doc-agnostic — der Agent-Apparat ist global; wir öffnen ihn aus
// einem beliebigen Doc-Provenienz-Tab.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";

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

const rec = new Recorder("provenienz-agent-tour", BASE);

await page.goto(`${BASE}/#/admin/doc/${SLUG}/provenienz`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2200);

// Switch to Agent view
await page.locator('nav button:has-text("Agent")').click();
await page.waitForTimeout(1500);

// ── Step 1: Agent-View geöffnet — Orchestrator-Topologie + Auswahl-Tab ────
await rec.step(page, "Agent-View — Orchestrator + Sub-Agent + 5 Tabs", {
  actions: [`goto /admin/doc/${SLUG}/provenienz`, 'click view toggle "Agent"'],
  notes: [
    "Canvas oben: Orchestrator (gerade aktiv) — wählt einen Sub-Agent. Sub-Agent trägt seine Skills (orange Pills) + Werkzeuge (cyan Pills) inline.",
    "Klick auf ein Pill → Detail im Auswahl-Tab rechts.",
    "Default-Tab beim Wechsel: „Auswahl“ — leerer Platzhalter solange kein Pill/Knoten selektiert.",
    "Header: aktiver LLM-Backend + Modell-Name (z.B. Qwen3-8B via vLLM).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'nav button:has-text("Auswahl")', text: "Auswahl-Tab (Default beim Agent-View-Start)" },
  ] }],
});

// ── Step 2: Tab „Schritte" — StepRegistry ─────────────────────────────────
await page.locator('nav button:has-text("Schritte")').click();
await page.waitForTimeout(900);
await rec.step(page, "Tab „Schritte“ — Registry der ausführbaren LLM-Schritte", {
  actions: ['click tab "Schritte"'],
  notes: [
    "Liste aller registrierten Steps, die der Orchestrator vorschlagen kann: extract_claims, formulate_task, search, cross_doc_search, register_lookup, evaluate, propose_stop, decompose_hit, promote_search_result, investigate_table.",
    "Pro Step: Name, Beschreibung, akzeptierte Anker-Typen, optional Beispiel-Prompts.",
    "Klick auf einen Step → Auswahl-Tab zeigt das Detail (Parameter-Schema, akzeptierte Anker-Knoten, Implementierungs-Pfad).",
    "Dieser Tab macht sichtbar, was der Agent „kann“ — die Provenance-DAGs setzen sich aus genau diesen Steps zusammen.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'nav button:has-text("Schritte")', text: "Step-Registry-Tab" },
  ] }],
});

// ── Step 3: Tab „Werkzeuge" — ToolRegistry ────────────────────────────────
await page.locator('nav button:has-text("Werkzeuge")').click();
await page.waitForTimeout(900);
await rec.step(page, "Tab „Werkzeuge“ — Tools, die Sub-Agents zur Verfügung haben", {
  actions: ['click tab "Werkzeuge"'],
  notes: [
    "Tools sind primitivere Bausteine als Steps: BM25-Search, Cross-Doc-Search, Register-Lookup, Calculator, Investigate-Table, etc.",
    "Ein Step kombiniert ein oder mehrere Tools mit LLM-Aufrufen zu einer höheren Aktion.",
    "Klick auf ein Tool → Detail im Auswahl-Tab: Input/Output-Schema, welche Sub-Agents es tragen, Beispiel-Calls.",
    "Trennt das WAS (Step) vom WIE (Tool) — wichtig wenn Tools wiederverwendet werden über mehrere Steps.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'nav button:has-text("Werkzeuge")', text: "Tool-Registry-Tab" },
  ] }],
});

// ── Step 4: Tab „Fähigkeiten" — SkillLibrary ──────────────────────────────
await page.locator('nav button:has-text("Fähigkeiten")').click();
await page.waitForTimeout(900);
await rec.step(page, "Tab „Fähigkeiten“ — Skill-Library der Sub-Agents", {
  actions: ['click tab "Fähigkeiten"'],
  notes: [
    "Skills sind verfeinerbare LLM-Skill-Pakete (System-Prompts + Approach-Definitionen) für spezifische Aufgaben.",
    "Pro Skill: Name, Beschreibung, zugehörige Steps, Versions-Historie.",
    "Skills sind editierbar / versionierbar — POST/PATCH /skills für eigene Anpassungen, GET /skills/{id}/runs für Lauf-Historie.",
    "Wenn ein Step eine Skill braucht, sucht der Server eine passende aus dieser Library (Best-Match nach Tags + Context).",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'nav button:has-text("Fähigkeiten")', text: "Skill-Library-Tab" },
  ] }],
});

// ── Step 5: Tab „Wünsche" — Capability-Requests ──────────────────────────
await page.locator('nav button:has-text("Wünsche")').click();
await page.waitForTimeout(900);
await rec.step(page, "Tab „Wünsche“ — Capability-Requests des Agents", {
  actions: ['click tab "Wünsche"'],
  notes: [
    "Wenn der Agent erkennt, dass ihm ein Tool / eine Skill fehlt, hinterlegt er einen Capability-Request — ähnlich einem Feature-Wunsch.",
    "Pro Request: gewünschte Capability, Begründung, betroffener Lauf (Session + Node).",
    "Liste der offenen Wünsche dient als Backlog für die Toolchain-Erweiterung — Entwickler arbeiten sie ab, registrieren neue Tools/Steps.",
    "Geschlossene/erfüllte Requests bleiben sichtbar (Audit), gefiltert oben in den Listen-Optionen.",
    "Dieses Konstrukt schließt den Kreis: Agent läuft → erkennt Defizit → meldet als Wunsch → Team baut → Agent kann mehr.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'nav button:has-text("Wünsche")', text: "Capability-Requests-Tab" },
  ] }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
