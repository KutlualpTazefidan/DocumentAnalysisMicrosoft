// Walkthrough recording: vllm-topbar-inspect
// Tour the vLLM control that lives in the BAM topbar (BamHeader centerSlot,
// mounted by AdminShell so it is reachable from every /admin/* page).
// The control is a status pill (click → popover with model, error + log-tail),
// a model picker, and a single state-driven Start/Stop button.
// This is a read-only tour: we open the popover and the model dropdown
// (pure useState toggles), but never click Start/Stop or pick a model —
// those would launch the vLLM subprocess / mutate the selected model
// server-side. Nothing to clean up.

import { chromium } from "playwright";
import fs from "node:fs";
import { Recorder } from "../record-walkthrough.mjs";

const SLUG = process.argv[2] || "1997-ronkohavi-standford-accuracy-estimation-model-selection";
const TOKEN = fs.readFileSync("/tmp/be.env", "utf8")
  .split("\n").find(l => l.startsWith("GOLDENS_API_TOKEN="))
  .split("=")[1].trim();
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8001";

// Resolve the real vLLM state + model list at run-time, exactly like
// extract-box-merge discovers real box IDs from /segments. The topbar UI
// is state-driven, so the action button's aria-label and the popover body
// depend on what the live server reports. Fall back to state-neutral
// selectors / notes if the backend is unreachable.
let status = null;
let models = [];
try {
  const sR = await fetch(`${API}/api/admin/llm/status`, { headers: { "X-Auth-Token": TOKEN } });
  if (sR.ok) status = await sR.json();
} catch (e) { console.log("status fetch failed:", String(e)); }
try {
  const mR = await fetch(`${API}/api/admin/llm/models`, { headers: { "X-Auth-Token": TOKEN } });
  if (mR.ok) models = (await mR.json()).models ?? [];
} catch (e) { console.log("models fetch failed:", String(e)); }

const state = status?.state ?? "stopped";
const cliMissing = status?.vllm_cli_available === false;
const currentModel = status?.model ?? null;
const STATE_LABEL = { stopped: "gestoppt", starting: "startet", running: "läuft", error: "Fehler" };

// Action-button selector branches on the live state. When the vllm CLI is
// missing the button is the disabled "nicht installiert" pill (no aria-label),
// so we fall back to the always-present last direct-child button: the
// ModelPicker's button is nested in a div, so :last-of-type lands on the
// action button in every state.
const ACTION_FALLBACK = '[data-testid="llm-topbar"] > button:last-of-type';
const ACTION_ARIA = {
  running: 'button[aria-label="vLLM stoppen"]',
  starting: 'button[aria-label="vLLM startet"]',
  error: 'button[aria-label="vLLM neu starten"]',
  stopped: 'button[aria-label="vLLM starten"]',
};
const actionSelector = cliMissing ? ACTION_FALLBACK : (ACTION_ARIA[state] ?? ACTION_FALLBACK);
const actionDesc = cliMissing
  ? "Action-Button: deaktiviert „nicht installiert“ (vllm-CLI fehlt)"
  : state === "running" ? "Action-Button: roter ■ Stop (läuft)"
  : state === "starting" ? "Action-Button: ⟳ „Startet…“ (deaktiviert, pollt Status)"
  : state === "error" ? "Action-Button: oranger ⟲ „Neustart“"
  : "Action-Button: grüner ▶ Start (gestoppt)";

const modelNames = models.slice(0, 3).map(m => `${m.label} (${m.parameters_b}B, ~${m.vram_bf16_gb} GB bf16)`);
console.log("vLLM state:", state, "| cliMissing:", cliMissing, "| model:", currentModel, "| #models:", models.length);

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

const rec = new Recorder("vllm-topbar-inspect", BASE);

// Land on /admin/inbox — the topbar is global (AdminShell centerSlot), and
// inbox has no slug/doc-load dependency that could error the outlet.
await page.goto(`${BASE}/#/admin/inbox`);
await page.waitForLoadState("networkidle").catch(() => {});
await page.waitForTimeout(2000);

// Step 1: the topbar pill — status dot + "vLLM" + state label
await rec.step(page, "vLLM-Pille in der BAM-Topbar (centerSlot)", {
  actions: ["goto /admin/inbox"],
  notes: [
    "Die vLLM-Steuerung sitzt mittig in der weißen BAM-Topbar (BamHeader centerSlot) und ist von jeder /admin/*-Seite aus erreichbar — AdminShell mountet sie einmal global.",
    "Die anklickbare Status-Pille zeigt einen farbigen Punkt (grau=gestoppt, gelb-pulsierend=startet, grün=läuft, rot=Fehler), das Label „vLLM“ und den Zustandstext.",
    `Live-Zustand jetzt: „vLLM ${STATE_LABEL[state] ?? state}“.`,
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="llm-topbar"]', text: "Topbar-Steuerung: Pille · Modell-Picker · Start/Stop" },
    { kind: "highlight", selector: '[data-testid="llm-topbar"] button[title="Logs / Details anzeigen"]', text: `Status-Pille: vLLM ${STATE_LABEL[state] ?? state}` },
  ] }],
});

// Step 2: click pill → popover with model / error / log-tail
await page.locator('[data-testid="llm-topbar"] button[title="Logs / Details anzeigen"]').click();
await page.waitForTimeout(500);
await rec.step(page, "Pille anklicken → Popover mit Details + Log-Tail", {
  actions: ['click [title="Logs / Details anzeigen"]'],
  notes: [
    "Klick auf die Pille öffnet ein Popover („vLLM-Server-Details“), rechtsbündig unter der Steuerung.",
    "Inhalt: aktuelles Modell, ggf. eine rote Fehlerbox, ein amber CLI-Warnhinweis falls die vllm-CLI fehlt, sowie ein aufklappbares „Logs (N)“-<details> mit dem Log-Tail.",
    cliMissing
      ? "Hier: amber Hinweis „vllm-CLI nicht gefunden“ — Setup-Anleitung in vllm-server/README.md."
      : "Das Logs-<details> klappt bei state „startet“/„Fehler“ automatisch auf, damit man die Transition sofort sieht.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: '[data-testid="llm-topbar-popover"]', text: "Popover: Modell · Fehler · Log-Tail" },
    { kind: "highlight", selector: '[data-testid="llm-topbar-popover"] summary', text: "Aufklappbares „Logs (N)“" },
  ] }],
});

// Close the popover before touching the model picker — the picker button
// sits outside popoverRef, so clicking it fires the outside-mousedown
// handler and would auto-close the popover mid-shot. Click the pill again.
await page.locator('[data-testid="llm-topbar"] button[title="Logs / Details anzeigen"]').click();
await page.waitForTimeout(300);

// Step 3: open the model picker dropdown
await page.locator('button[title="Modell auswählen — wirkt erst beim nächsten Start"]').click();
await page.waitForTimeout(500);
await rec.step(page, "Modell-Picker öffnen — kuratierte Modell-Liste", {
  actions: ['click [title="Modell auswählen — wirkt erst beim nächsten Start"]'],
  notes: [
    currentModel
      ? `Picker-Button zeigt das aktuell gewählte Modell; bei laufendem Server kommt ein amber Hinweis „Modellwechsel wirkt erst nach Stop + Start“.`
      : "Ohne gewähltes Modell zeigt der Picker-Button „Modell wählen“.",
    "Die Liste ist kuratiert (useLlmModels): pro Eintrag Name (monospace), Label, Parameter-Größe, VRAM-bf16-Bedarf und Lizenz; das aktive Modell trägt einen blauen „aktiv“-Tag, Modelle ohne 24-GB-bf16-Fit ein amber „braucht Quantisierung“.",
    modelNames.length
      ? `Beispiele aus der Live-Liste: ${modelNames.join("; ")}.`
      : "Modell-Liste beim Aufnehmen nicht abrufbar (Backend offline) — UI rendert dann den leeren/deaktivierten Picker.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: 'button[title="Modell auswählen — wirkt erst beim nächsten Start"]', text: currentModel ? "Aktuelles Modell" : "„Modell wählen“" },
    { kind: "note", text: "Auswahl wirkt erst beim nächsten Start — wird hier nur angeschaut, nicht geklickt." },
  ] }],
});

// Close the dropdown again so the final shot is clean.
await page.locator('button[title="Modell auswählen — wirkt erst beim nächsten Start"]').click();
await page.waitForTimeout(300);

// Step 4: the unified state-driven Start/Stop button
await rec.step(page, "Start/Stop — ein zustandsabhängiger Button", {
  actions: ["highlight action button (kein Klick — read-only Tour)"],
  notes: [
    "Rechts in der Steuerung: ein einziger Button, dessen Aussehen und Aktion vom Zustand abhängen — gestoppt→grüner ▶ Start (/llm/start), startet→⟳ „Startet…“ (disabled), läuft→roter ■ Stop (/llm/stop), Fehler→oranger ⟲ „Neustart“.",
    "Fehlt die vllm-CLI, ist der Button deaktiviert („nicht installiert“) und verweist auf vllm-server/README.md.",
    `Live: ${actionDesc}.`,
    "Bewusst nicht geklickt — Start würde einen echten vLLM-Subprozess starten; diese Tour bleibt zustandsneutral.",
  ],
  shots: [{ annotations: [
    { kind: "highlight", selector: actionSelector, text: actionDesc },
  ] }],
});

const outDir = await rec.finish();
await browser.close();
console.log("Wrote walkthrough to", outDir);
