#!/usr/bin/env node
// Builds a self-contained interactive flow-map (flow-graph.html) from the
// recorded walkthrough runs under ./output. Pages become compound nodes,
// each flow step becomes a child node inside the page it lands on, and the
// flow threads through them as colored edges. Page-crossing edges carry the
// trigger ("what click moved us here") as their label.
//
// Run:  node tests/walkthrough/build-flow-graph.mjs
// Open: tests/walkthrough/flow-graph.html  (needs internet for the CDN libs)

import { readdirSync, readFileSync, writeFileSync, statSync } from "node:fs";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, "output");

// ---------------------------------------------------------------------------
// 1. Collect every recorded run, keep the newest per flow name.
// ---------------------------------------------------------------------------
function walkForDataJson(dir, acc) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) walkForDataJson(p, acc);
    else if (entry.name === "data.json") acc.push(p);
  }
  return acc;
}

function loadFlows() {
  const files = walkForDataJson(OUT_DIR, []);
  const byName = new Map();
  for (const file of files) {
    let json;
    try {
      json = JSON.parse(readFileSync(file, "utf8"));
    } catch {
      continue;
    }
    if (!json?.name || !Array.isArray(json.steps)) continue;
    const ts = Date.parse(json.startedAt ?? "") || statSync(file).mtimeMs;
    const prev = byName.get(json.name);
    if (!prev || ts > prev.ts) byName.set(json.name, { json, ts, file });
  }
  // keep the run dir (relative to this file) so we can point at its screenshots
  return [...byName.values()].map((v) => ({
    json: v.json,
    relDir: relative(__dirname, dirname(v.file)),
  }));
}

// ---------------------------------------------------------------------------
// 2. Route extraction. waitForUrl/goto actions are stored as RegExp.toString()
//    or raw paths; normalize both to a canonical route key.
// ---------------------------------------------------------------------------
function routeFromAction(action) {
  let m = action.match(/^waitForUrl\s+(.*)$/);
  if (m) {
    let s = m[1].trim();
    // strip the /…/ + flags wrapper of a RegExp literal
    s = s.replace(/^\/(.*)\/[a-z]*$/, "$1");
    s = s.replace(/\\\//g, "/"); // \/ -> /
    s = s.replace(/[$^]/g, ""); // drop anchors
    s = s.replace(/^#/, ""); // hash router prefix
    s = s.replace(/\.\*/g, ":slug"); // wildcard segment
    return normalizeRoute(s);
  }
  m = action.match(/^goto\s+(.*)$/);
  if (m) {
    let s = m[1].trim();
    s = s.split("?")[0]; // drop query
    s = s.replace(/^\/#/, ""); // /#/x -> /x
    s = s.replace(/^#/, "");
    return normalizeRoute(s);
  }
  return null;
}

function normalizeRoute(s) {
  if (!s || s === "/") return "/";
  s = s.replace(/\/+$/, ""); // trailing slash
  if (s === "" || s === "/") return "/";
  if (!s.startsWith("/")) s = "/" + s;
  // the generic "/admin/" landing == the admin inbox
  if (s === "/admin") return "/admin/inbox";
  return s;
}

// ---------------------------------------------------------------------------
// 3. Page catalog: canonical route -> {name, stage, hue}. Doc-stage routes
//    are matched by suffix so the :slug doesn't matter.
// ---------------------------------------------------------------------------
const STAGES = {
  auth: { col: 0, label: "Auth" },
  hub: { col: 1, label: "Admin-Hub" },
  doc: { col: 2, label: "Doc-Stufen" },
  role: { col: 3, label: "Rolle" },
};

function pageMeta(route) {
  const map = {
    "/": { name: "Landing", stage: "auth", hue: "#8b97a3" },
    "/login": { name: "Anmeldung", stage: "auth", hue: "#8b97a3" },
    "/admin/inbox": { name: "Dokumente", stage: "hub", hue: "#1E7EB2" },
    "/admin/tenants": { name: "Fachbereiche", stage: "hub", hue: "#1E7EB2" },
    "/admin/curators": { name: "Kuratoren", stage: "hub", hue: "#1E7EB2" },
    "/admin/pipelines": { name: "Pipelines", stage: "hub", hue: "#1E7EB2" },
    "/admin/dashboard": { name: "Übersicht", stage: "hub", hue: "#1E7EB2" },
    "/curate": { name: "Kurator", stage: "role", hue: "#3a9d5d" },
  };
  if (map[route]) return map[route];
  if (/\/extract$/.test(route)) return { name: "Extrahieren", stage: "doc", hue: "#d9822b" };
  if (/\/synthesise$/.test(route)) return { name: "Synthese", stage: "doc", hue: "#2bb673" };
  if (/\/(compare|vergleich)$/.test(route)) return { name: "Vergleich", stage: "doc", hue: "#b07cd6" };
  if (/\/provenienz$/.test(route)) return { name: "Provenienz", stage: "doc", hue: "#56b4d3" };
  // fallthrough: an unmapped admin page
  return { name: route.replace(/^\/admin\//, ""), stage: "hub", hue: "#1E7EB2" };
}

// collapse doc-stage routes (which carry a :slug) onto one node per stage so
// every flow's "Extrahieren" lands in the same compound.
function pageKey(route) {
  const meta = pageMeta(route);
  if (meta.stage === "doc") return "doc:" + meta.name;
  return "page:" + route;
}

// ---------------------------------------------------------------------------
// 4. Trigger label — what caused the move into this step.
// ---------------------------------------------------------------------------
function humanizeTrigger(step) {
  for (const sc of step.screenshots ?? []) {
    for (const a of sc.annotations ?? []) {
      if (a.kind === "highlight" && a.text) return a.text;
    }
  }
  for (const act of step.actions ?? []) {
    if (!act.startsWith("click")) continue;
    let t = act.match(/has-text\(\\?"([^"\\]+)\\?"\)/) || act.match(/has-text\("([^"]+)"\)/);
    if (t) return "„" + t[1] + "“";
    t = act.match(/aria-label=\\?"([^"\\]+)\\?"/) || act.match(/aria-label="([^"]+)"/);
    if (t) return "„" + t[1] + "“";
    if (/type=.?submit/.test(act)) return "absenden";
    return "klick";
  }
  return step.title ?? "";
}

const truncate = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s ?? "");

// ---------------------------------------------------------------------------
// 5. Build cytoscape elements.
// ---------------------------------------------------------------------------
const FLOW_COLORS = [
  "#4fc3f7", "#ffb74d", "#81c784", "#e57373", "#ba68c8",
  "#4db6ac", "#ff8a65", "#a1887f", "#90a4ae", "#f06292",
  "#9ccc65", "#7986cb", "#dce775", "#4dd0e1",
];

// Two-level grouping: ROLE (Admin/Kurator/Gemeinsam) → CATEGORY → workflow.
// "Gemeinsam" = anything not tied to a specific role (e.g. login error path).
// Unknown flow names fall through to Gemeinsam/Sonstige with the raw name.
// Journey-order inside each category (lower = earlier). 10/20/30/… spacing leaves
// room to slot new flows in without renumbering.
const FLOW_META = {
  // ── Anmeldung ─────────────────────────────────────────────────────────────
  "login-and-tenant-admin":  { role: "Admin",     cat: "Anmeldung",   order: 10, label: "Anmelden + ersten Fachbereich anlegen" },
  "auth-failure":            { role: "Gemeinsam", cat: "Anmeldung",   order: 10, label: "Anmelden: Fehler-Pfad" },
  // ── Verwaltung ────────────────────────────────────────────────────────────
  "tenant-edit-and-delete":  { role: "Admin",     cat: "Verwaltung",  order: 10, label: "Fachbereich bearbeiten / löschen" },
  "curator-management":      { role: "Admin",     cat: "Verwaltung",  order: 20, label: "Kuratoren anlegen / verwalten" },
  // ── Dokumente ─────────────────────────────────────────────────────────────
  "upload-pdf":              { role: "Admin",     cat: "Dokumente",   order: 10, label: "Dokument hochladen" },
  "dateien-suche":           { role: "Admin",     cat: "Dokumente",   order: 20, label: "Dokumente: Suche" },
  "admin-inbox-to-extract":  { role: "Admin",     cat: "Dokumente",   order: 30, label: "Dokument öffnen → Extrahieren" },
  // ── Extrahieren ──────────────────────────────────────────────────────────
  "extract-stage-tour":      { role: "Admin",     cat: "Extrahieren", order: 10, label: "Extrahieren: Rundgang" },
  "extract-page-extract":    { role: "Admin",     cat: "Extrahieren", order: 20, label: "Extrahieren: Diese Seite / Alle Seiten" },
  "extract-box-create":      { role: "Admin",     cat: "Extrahieren", order: 30, label: "Extrahieren: Neue Box anlegen" },
  "extract-box-edit":        { role: "Admin",     cat: "Extrahieren", order: 40, label: "Extrahieren: Box-Eigenschaften ändern" },
  "extract-box-merge":       { role: "Admin",     cat: "Extrahieren", order: 50, label: "Extrahieren: Boxen verbinden / trennen" },
  "extract-text-edit":       { role: "Admin",     cat: "Extrahieren", order: 60, label: "Extrahieren: HTML-Text korrigieren" },
  "extract-register-detect": { role: "Admin",     cat: "Extrahieren", order: 70, label: "Extrahieren: Verzeichnisse erkennen" },
  "extrahieren-lock":        { role: "Admin",     cat: "Extrahieren", order: 80, label: "Extrahieren: Seite abschließen" },
  "extract-export":          { role: "Admin",     cat: "Extrahieren", order: 90, label: "Extrahieren: Export → sourceelements.json" },
  // ── Synthese ──────────────────────────────────────────────────────────────
  "synthese-generate":       { role: "Admin",     cat: "Synthese",    order: 10, label: "Synthese: erzeugen" },
  "synthese-box-select":     { role: "Admin",     cat: "Synthese",    order: 20, label: "Synthese: Box auswählen" },
  "synthese-page-lock":      { role: "Admin",     cat: "Synthese",    order: 30, label: "Synthese: Seite abschließen / entsperren" },
  "synthese-edit-answer":    { role: "Admin",     cat: "Synthese",    order: 40, label: "Synthese: Antwort überschreiben" },
  "synthese-deprecate":      { role: "Admin",     cat: "Synthese",    order: 50, label: "Synthese: Frage verwerfen" },
  // ── Provenienz ────────────────────────────────────────────────────────────
  "provenienz-stage-tour":   { role: "Admin",     cat: "Provenienz",  order: 10, label: "Provenienz: Rundgang" },
  "provenienz-session-crud": { role: "Admin",     cat: "Provenienz",  order: 20, label: "Provenienz: Sitzung anlegen/löschen" },
  "provenienz-iterate":      { role: "Admin",     cat: "Provenienz",  order: 30, label: "Provenienz: AI-Vorschlag → Anwenden" },
  "provenienz-agent-tour":   { role: "Admin",     cat: "Provenienz",  order: 40, label: "Provenienz: Agent-Sicht" },
  // ── Hauptpfad (Kurator) ───────────────────────────────────────────────────
  "curator-journey":         { role: "Kurator",   cat: "Hauptpfad",   order: 10, label: "Kurator-Reise (Beispiel)" },
  "curator-add-question":    { role: "Kurator",   cat: "Hauptpfad",   order: 20, label: "Kurator: eigene Frage anlegen" },
  // ── System ────────────────────────────────────────────────────────────────
  "vllm-topbar-inspect":     { role: "Admin",     cat: "System",      order: 10, label: "vLLM-Topbar inspizieren" },
};
const ROLE_ORDER = ["Admin", "Kurator", "Gemeinsam"];
const CATEGORY_ORDER = ["Anmeldung", "Verwaltung", "Dokumente", "Extrahieren", "Synthese", "Provenienz", "Hauptpfad", "System", "Sonstige"];
const metaFor = (name) => FLOW_META[name] ?? { role: "Gemeinsam", cat: "Sonstige", order: 999, label: name };

function build() {
  // Process flows in journey order so each page-compound's storyboard renders
  // in the same sequence as the sidebar (Slot 1 first, then 2, 3, … in grid
  // reading order). Tie-break alphabetically for flows in the same slot.
  const flows = loadFlows().sort((a, b) => {
    const oa = (FLOW_META[a.json.name]?.order ?? 999);
    const ob = (FLOW_META[b.json.name]?.order ?? 999);
    return oa - ob || a.json.name.localeCompare(b.json.name);
  });
  const pages = new Map(); // key -> {key,route,name,stage,hue,flows:Set,notes:[],shots:[]}
  const stepNodes = [];
  const edges = [];
  const flowMeta = [];

  flows.forEach(({ json: flow, relDir }, fi) => {
    const color = FLOW_COLORS[fi % FLOW_COLORS.length];
    const pagesInFlow = new Set();
    let curRoute = "/";
    let prevStepId = null;
    let prevKey = null;

    flow.steps.forEach((step) => {
      for (const act of step.actions ?? []) {
        const r = routeFromAction(act);
        if (r) curRoute = r;
      }
      const key = pageKey(curRoute);
      const meta = pageMeta(curRoute);
      if (!pages.has(key)) {
        pages.set(key, { key, route: curRoute, ...meta, flows: new Set(), notes: [], shots: [] });
      }
      const page = pages.get(key);
      page.flows.add(flow.name);
      pagesInFlow.add(key);
      for (const n of step.notes ?? []) page.notes.push({ flow: flow.name, text: n });

      const shots = (step.screenshots ?? []).map((sc) => ({
        src: `${relDir}/${sc.filename}`.replace(/\\/g, "/"),
        cap: sc.note ?? "",
      }));
      for (const sh of shots) page.shots.push({ ...sh, flow: flow.name, step: step.title });

      const stepId = `s:${flow.name}:${step.index}`;
      stepNodes.push({
        data: {
          id: stepId,
          parent: key,
          label: truncate(step.title, 24),
          title: step.title ?? "",
          flow: flow.name,
          color,
          notes: step.notes ?? [],
          actions: step.actions ?? [],
          status: step.status ?? "ok",
          page: meta.name,
          shots,
          thumb: shots[0]?.src, // undefined (dropped from JSON) when the step has no shot
        },
      });

      if (prevStepId) {
        const crossing = prevKey !== key;
        edges.push({
          data: {
            id: `e:${flow.name}:${step.index}`,
            source: prevStepId,
            target: stepId,
            flow: flow.name,
            color,
            crossing,
            label: crossing ? humanizeTrigger(step) : "",
          },
        });
      }
      prevStepId = stepId;
      prevKey = key;
    });

    const fm = metaFor(flow.name);
    flowMeta.push({ name: flow.name, label: fm.label, role: fm.role, cat: fm.cat, order: fm.order ?? 999, color, pages: pagesInFlow.size, steps: flow.steps.length });
  });

  // Default: no flow on — start with an empty canvas, user picks via accordion.
  flowMeta.forEach((f) => (f.on = false));

  // ---- deterministic layout: stage columns, step-grid packed inside pages.
  // Positions are baked in so the page opens instantly (no force solve, which
  // either diagonal-collapses or, with column constraints, never terminates).
  const order = ["auth", "hub", "doc", "role"];
  // wide enough for the large screenshot-thumbnail step nodes (≈230×148)
  const COL_W = 2450, SDX = 580, SDY = 420, PAGE_GAP = 460, TOP = 380, COLS_MAX = 4;
  const stepsByPage = new Map();
  for (const s of stepNodes) {
    if (!stepsByPage.has(s.data.parent)) stepsByPage.set(s.data.parent, []);
    stepsByPage.get(s.data.parent).push(s);
  }
  const pagesByStage = {};
  for (const p of pages.values()) (pagesByStage[p.stage] ||= []).push(p);

  // Each consecutive run of same-flow children starts on a new row — so the
  // Rundgang row, the Lock row, the Export row are visually separated instead
  // of bleeding into one another. `kids` is already in journey order (flows
  // sorted by FLOW_META.order above), so grouping by flow is enough.
  function layoutKidsByFlow(kids) {
    const groups = [];
    let prev = null;
    for (const k of kids) {
      const f = k.data.flow;
      if (f !== prev) { groups.push([]); prev = f; }
      groups[groups.length - 1].push(k);
    }
    const rowsPer = groups.map(g => Math.ceil(g.length / COLS_MAX) || 1);
    const totalRows = rowsPer.reduce((a, b) => a + b, 0) || 1;
    const gridW = COLS_MAX * SDX, gridH = totalRows * SDY;
    return { groups, rowsPer, totalRows, gridW, gridH };
  }

  const pageNodes = [];
  order.forEach((stage, ci) => {
    let y = TOP;
    const cx = ci * COL_W + 560;
    for (const p of pagesByStage[stage] || []) {
      const kids = stepsByPage.get(p.key) || [];
      const L = layoutKidsByFlow(kids);
      const midY = y + L.gridH / 2;
      let rowOffset = 0;
      L.groups.forEach((group, gi) => {
        group.forEach((s, gk) => {
          const col = gk % COLS_MAX;
          const rowInGroup = Math.floor(gk / COLS_MAX);
          s.position = {
            x: cx - L.gridW / 2 + col * SDX + SDX / 2,
            y: y + (rowOffset + rowInGroup) * SDY + SDY / 2,
          };
        });
        rowOffset += L.rowsPer[gi];
      });
      pageNodes.push({
        data: {
          id: p.key, label: p.name, kind: "page", stage: p.stage, hue: p.hue,
          flowCount: p.flows.size, noteCount: p.notes.length, notes: p.notes, shots: p.shots,
        },
        position: { x: cx, y: midY },
      });
      y += L.gridH + PAGE_GAP;
    }
  });

  return {
    elements: [...pageNodes, ...stepNodes, ...edges],
    flows: flowMeta,
    roles: ROLE_ORDER,
    categories: CATEGORY_ORDER,
    stages: STAGES,
    generatedAt: new Date().toISOString(),
  };
}

// ---------------------------------------------------------------------------
// 6. quick self-test of routeFromAction against the real patterns
// ---------------------------------------------------------------------------
function selfTest() {
  const cases = [
    ["goto /", "/"],
    ["goto /login", "/login"],
    ["goto /#/login?reason=expired", "/login"],
    ["goto /#/login?legacy=1", "/login"],
    ["goto /admin/tenants", "/admin/tenants"],
    ["waitForUrl /\\/admin\\//", "/admin/inbox"],
    ["waitForUrl /#\\/admin\\//", "/admin/inbox"],
    ["waitForUrl /#\\/admin\\/tenants/", "/admin/tenants"],
    ["waitForUrl /#\\/admin\\/doc\\/.*\\/extract/", "/admin/doc/:slug/extract"],
    ["waitForUrl /#\\/admin\\/doc\\/.*\\/provenienz/", "/admin/doc/:slug/provenienz"],
    ["waitForUrl /#\\/curate/", "/curate"],
    ["expectVisible header", null],
  ];
  let ok = true;
  for (const [inp, exp] of cases) {
    const got = routeFromAction(inp);
    if (got !== exp) {
      ok = false;
      console.error(`  ✗ routeFromAction(${JSON.stringify(inp)}) = ${JSON.stringify(got)}, expected ${JSON.stringify(exp)}`);
    }
  }
  console.log(ok ? "  ✓ routeFromAction self-test passed" : "  ✗ routeFromAction self-test FAILED");
  return ok;
}

// ---------------------------------------------------------------------------
// 7. HTML emit
// ---------------------------------------------------------------------------
function html(graph) {
  const DATA = JSON.stringify(graph);
  return `<!doctype html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GOLDENS — Walkthrough-Flow-Karte</title>
<script src="lib/cytoscape.min.js"></script>
<script src="lib/layout-base.js"></script>
<script src="lib/cose-base.js"></script>
<script src="lib/cytoscape-fcose.js"></script>
<style>
  :root{--body:#222c35;--panel:#2b3640;--rail:#3a4753;--border:#56616b;--brand:#1E7EB2;--ink:#e8edf1;--muted:#9fb0bd;}
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;font-family:system-ui,-apple-system,sans-serif;background:var(--body);color:var(--ink)}
  #app{display:grid;grid-template-columns:var(--sb-w,240px) 6px 1fr 320px;grid-template-rows:52px 1fr;height:100%}
  header{grid-column:1/5;display:flex;align-items:center;gap:14px;padding:0 18px;background:#031E31;border-bottom:1px solid #021727}
  #sb-resizer{background:var(--rail);cursor:col-resize;transition:background .15s ease}
  #sb-resizer:hover,#sb-resizer.dragging{background:var(--brand)}
  header .logo{font-weight:700;letter-spacing:.04em}
  header .sub{font-size:12px;color:#8fbfdb}
  header .spacer{flex:1}
  header button{background:var(--rail);color:var(--ink);border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:12px;cursor:pointer;display:inline-flex;align-items:center}
  header button:hover{background:#455563}
  header button.on{background:var(--brand);border-color:var(--brand);color:#fff}
  header button svg{margin-right:5px}
  aside{background:var(--panel);overflow-y:auto;padding:12px 12px 24px}
  aside h2{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:14px 0 8px}
  aside h2:first-child{margin-top:2px}
  .role-head{font-size:12.5px;font-weight:800;letter-spacing:.06em;color:#fff;text-transform:uppercase;margin:16px 0 4px;padding:5px 0 5px 9px;border-left:4px solid var(--brand);border-radius:2px;background:rgba(255,255,255,.02);cursor:pointer;user-select:none;display:flex;align-items:center;gap:6px}
  .role-head:hover{background:rgba(255,255,255,.05)}
  .role-group:first-child .role-head{margin-top:0}
  .role-head[data-role="Admin"]{border-left-color:#e6b84a}
  .role-head[data-role="Kurator"]{border-left-color:#3a9d5d}
  .role-head[data-role="Gemeinsam"]{border-left-color:var(--muted)}
  .cat-head{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:8px 4px 2px 12px;padding-bottom:2px;cursor:pointer;user-select:none;display:flex;align-items:center;gap:5px}
  .cat-head:hover{color:#cfdde6}
  .cat-group:first-child .cat-head{margin-top:0}
  /* chevron: ▶ collapsed → ▼ expanded (rotated). aria-expanded drives state. */
  .chev{display:inline-block;font-size:9px;line-height:1;width:8px;transition:transform .15s ease;opacity:.7}
  [aria-expanded="true"] > .chev{transform:rotate(90deg)}
  .role-body, .cat-body{overflow:hidden}
  [aria-expanded="false"] + .role-body, [aria-expanded="false"] + .cat-body{display:none}
  .meta-count{margin-left:auto;color:var(--muted);font-size:10.5px;font-variant-numeric:tabular-nums;font-weight:500}
  .group-toggle{accent-color:var(--brand);margin:0;cursor:pointer;flex:0 0 auto}
  .flow .seq{color:var(--muted);font-size:11px;font-weight:600;font-variant-numeric:tabular-nums;min-width:16px;flex:0 0 auto}
  .flow.canvas-hover{background:rgba(30,126,178,.18);box-shadow:inset 3px 0 0 var(--brand)}
  .role-head.canvas-hover,.cat-head.canvas-hover{background:rgba(30,126,178,.10)}
  .flow{margin-left:8px}
  .flow{display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:6px;cursor:pointer;font-size:12.5px}
  .flow .lbl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .flow:hover{background:var(--rail)}
  .flow input{accent-color:var(--brand)}
  .dot{width:10px;height:10px;border-radius:50%;flex:0 0 auto}
  .flow .meta{margin-left:auto;color:var(--muted);font-size:10.5px;font-variant-numeric:tabular-nums}
  .legend .row{display:flex;align-items:center;gap:8px;font-size:12px;padding:3px 6px}
  .legend .swatch{width:12px;height:12px;border-radius:3px}
  #cy{background:radial-gradient(circle at 30% 20%,#26313b,#1c252d 70%)}
  #inspector{background:var(--panel);border-left:1px solid var(--rail);overflow-y:auto;padding:16px}
  #inspector .empty{color:var(--muted);font-size:13px;line-height:1.5;margin-top:8px}
  .badge{display:inline-block;font-size:10.5px;padding:2px 8px;border-radius:999px;background:var(--rail);color:var(--ink);margin:0 4px 4px 0}
  #inspector h3{font-size:15px;margin:2px 0 6px}
  #inspector .where{font-size:12px;color:#8fbfdb;margin-bottom:12px}
  .note{font-size:12.5px;line-height:1.5;background:#222c35;border-left:3px solid var(--brand);border-radius:4px;padding:8px 10px;margin:6px 0}
  .note .nf{display:block;font-size:10px;color:var(--muted);margin-top:4px}
  .acts{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#a7c7da;white-space:pre-wrap;background:#1b232b;border-radius:4px;padding:8px 10px;margin-top:6px}
  .seclabel{font-size:10px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:16px 0 6px}
  .hint{position:absolute;bottom:12px;left:252px;font-size:11px;color:var(--muted);background:rgba(11,17,23,.7);padding:4px 9px;border-radius:6px;pointer-events:none}
</style></head>
<body>
<div id="app">
  <header>
    <span class="logo">GOLDENS</span><span class="sub">Walkthrough-Flow-Karte</span>
    <span class="spacer"></span>
    <button id="all">Alle</button><button id="none">Keine</button><button id="fit">Anpassen</button><button id="reset">Raster</button><button id="physik">Physik</button><button id="lock" title="Knoten gegen versehentliches Ziehen sperren"></button>
  </header>
  <aside>
    <h2>Workflows</h2><div id="flows"></div>
    <h2>Seiten-Stufen</h2>
    <div class="legend">
      <div class="row"><span class="swatch" style="background:#8b97a3"></span>Auth (Landing/Login)</div>
      <div class="row"><span class="swatch" style="background:#1E7EB2"></span>Admin-Hub</div>
      <div class="row"><span class="swatch" style="background:#d9822b"></span>Extrahieren</div>
      <div class="row"><span class="swatch" style="background:#2bb673"></span>Synthese</div>
      <div class="row"><span class="swatch" style="background:#b07cd6"></span>Vergleich</div>
      <div class="row"><span class="swatch" style="background:#56b4d3"></span>Provenienz</div>
      <div class="row"><span class="swatch" style="background:#3a9d5d"></span>Kurator</div>
    </div>
    <h2>Lesen</h2>
    <div class="legend" style="font-size:11.5px;color:var(--muted);line-height:1.5;padding:0 6px">
      Große Kästen = Seiten. Jeder Screenshot darin = ein Schritt. Dicke Pfeile mit Text = Seitenwechsel (der Text sagt, was ihn auslöst). Klick auf einen Screenshot → Titel, Notiz & Aktionen rechts.
    </div>
  </aside>
  <div id="sb-resizer" title="Seitenleiste verschieben"></div>
  <div style="position:relative"><div id="cy" style="position:absolute;inset:0"></div>
    <div class="hint">Ziehen zum Verschieben · Scrollen zum Zoomen · Knoten klicken für Details</div>
  </div>
  <div id="inspector"><div class="empty">Klicke eine <b>Seite</b> für alle Notizen dort, oder einen <b>Schritt</b> für Titel, Notiz und Aktionen.<br><br>Mehrere Flows kreuzen sich über dieselben Seiten — schalte links einzelne Flows ein/aus, um einen Pfad isoliert zu verfolgen.</div></div>
</div>
<script>
const GRAPH = ${DATA};
cytoscape.use(window.cytoscapeFcose);
const cy = cytoscape({
  container: document.getElementById('cy'),
  elements: GRAPH.elements,
  wheelSensitivity: 0.2,
  style: [
    { selector: 'node[kind="page"]', style: {
        'label':'data(label)','color':'#ffffff','font-size':18,'font-weight':700,
        'text-valign':'top','text-halign':'center','text-margin-y':-12,
        'background-color':'data(hue)','background-opacity':0.13,
        'border-width':2.5,'border-color':'data(hue)','border-opacity':0.95,
        'shape':'round-rectangle','padding':'34px','text-transform':'uppercase',
        'text-outline-color':'#11181f','text-outline-width':3 } },
    { selector: 'node[!kind][thumb]', style: {
        'label':'data(label)','color':'#e3edf3','font-size':13,
        'width':500,'height':320,'shape':'round-rectangle',
        'background-image':'data(thumb)','background-fit':'cover','background-color':'#11181f','background-image-crossorigin':'null',
        'border-width':3.5,'border-color':'data(color)',
        'text-valign':'bottom','text-halign':'center','text-margin-y':8,'text-wrap':'wrap','text-max-width':'380px',
        'text-outline-color':'#11181f','text-outline-width':2.5,'text-opacity':0.0 } },
    { selector: 'node[!kind][!thumb]', style: {
        'label':'data(label)','color':'#e3edf3','font-size':10,'width':18,'height':18,
        'background-color':'data(color)','border-width':2,'border-color':'#11181f',
        'text-valign':'bottom','text-halign':'center','text-margin-y':3,'text-wrap':'wrap','text-max-width':'130px',
        'text-outline-color':'#11181f','text-outline-width':2,'text-opacity':0.0 } },
    { selector: 'edge', style: {
        'width':2,'line-color':'data(color)','target-arrow-color':'data(color)',
        'target-arrow-shape':'triangle','curve-style':'bezier','arrow-scale':0.9,'opacity':0.85 } },
    { selector: 'edge[?crossing]', style: {
        'width':3.5,'label':'data(label)','font-size':10,'color':'#dfe9ef',
        'text-background-color':'#1c252d','text-background-opacity':0.92,'text-background-padding':3,
        'text-rotation':'autorotate','arrow-scale':1.2 } },
    { selector: '.hidden', style: { 'display':'none' } },
    { selector: '.show-label', style: { 'text-opacity':1 } },
    { selector: 'node:selected', style: { 'border-width':3,'border-color':'#ffffff' } },
  ],
  layout: { name:'preset' },
});
window.cy = cy; // expose for probing / debugging

// snapshot the baked grid positions so "Raster" can restore them after physics
function activeNodes(){
  const v = cy.nodes('[!kind][flow]').filter(e => !e.hasClass('hidden'));
  return v.nonempty() ? v : cy.nodes('[!kind]');
}
// default framing: bias toward LARGE screenshots (min zoom), pan to explore
function fitActive(dur){
  const eles = activeNodes(), bb = eles.boundingBox(), pad = 90;
  const fitZoom = Math.min((cy.width()-2*pad)/bb.w, (cy.height()-2*pad)/bb.h);
  cy.animate({ zoom: Math.max(fitZoom, 0.5), center:{ eles } }, { duration: dur ?? 0 });
}
// "Anpassen": true fit so all active content is visible at once (overview)
function fitVisible(dur){
  cy.animate({ fit:{ eles: activeNodes(), padding: 55 } }, { duration: dur ?? 0 });
}

// optional force pass — unconstrained (constrained fcose never terminates on
// this graph), seeded from the grid so it stays roughly columnar.
function runPhysics(){
  window.__layoutDone = false;
  const lo = cy.elements(':visible').layout({ name:'fcose', quality:'default', randomize:false, animate:true, animationDuration:600,
    nodeSeparation:100, idealEdgeLength: e => e.data('crossing')?260:55,
    nodeRepulsion:11000, gravity:0.1, gravityCompound:1.4, packComponents:false,
    nestingFactor:0.1, tile:false, fit:true, padding:55 });
  lo.one('layoutstop', ()=>{ window.__layoutDone=true; });
  lo.run();
}
function resetGrid(){ repack(); fitVisible(400); }

// ---- flow filter (Role → Category → workflow) ----
const flowsBox = document.getElementById('flows');
const state = new Map();
const byRole = new Map(GRAPH.roles.map(r => [r, new Map(GRAPH.categories.map(c => [c, []]))]));
GRAPH.flows.forEach(f => {
  state.set(f.name, f.on);
  if (!byRole.has(f.role)) byRole.set(f.role, new Map());
  const cats = byRole.get(f.role);
  if (!cats.has(f.cat)) cats.set(f.cat, []);
  cats.get(f.cat).push(f);
});
// Accordion-Zustand pro Role/Category in localStorage, Default = collapsed.
const ACCKEY = 'flowgraph.accordion';
const accState = JSON.parse(localStorage.getItem(ACCKEY) || '{}');
const saveAcc = () => localStorage.setItem(ACCKEY, JSON.stringify(accState));
const isOpen = (key) => accState[key] === true;

// Group-checkbox refs so we can update their tri-state when any child changes.
const groupRefs = []; // { input, names: [flowName, ...] }

function recomputeGroups() {
  for (const g of groupRefs) {
    const onCount = g.names.reduce((n, name) => n + (state.get(name) ? 1 : 0), 0);
    g.input.indeterminate = onCount > 0 && onCount < g.names.length;
    g.input.checked = onCount === g.names.length;
  }
}

function setFlowOn(name, on) {
  state.set(name, on);
  const cb = flowsBox.querySelector('input[data-flow="' + CSS.escape(name) + '"]');
  if (cb) cb.checked = on;
}

for (const [role, cats] of byRole) {
  const allRoleFlows = [...cats.values()].flat();
  if (!allRoleFlows.length) continue;

  const rgroup = document.createElement('div');
  rgroup.className = 'role-group';
  const rkey = 'role:' + role;
  const rhead = document.createElement('div');
  rhead.className = 'role-head'; rhead.dataset.role = role;
  rhead.setAttribute('role','button');
  rhead.setAttribute('aria-expanded', String(isOpen(rkey)));
  rhead.innerHTML =
    '<span class="chev">▶</span>' +
    '<input type="checkbox" class="group-toggle" title="Alle Workflows dieser Rolle ein-/ausschalten">' +
    '<span>'+role+'</span>' +
    '<span class="meta-count">'+allRoleFlows.length+'</span>';
  const rbody = document.createElement('div');
  rbody.className = 'role-body';
  rgroup.appendChild(rhead); rgroup.appendChild(rbody);
  // Clicks on the head expand/collapse; clicks on the checkbox toggle the group.
  const roleCb = rhead.querySelector('.group-toggle');
  rhead.addEventListener('click', (e) => {
    if (e.target === roleCb) return; // checkbox handles its own click
    const next = rhead.getAttribute('aria-expanded') !== 'true';
    rhead.setAttribute('aria-expanded', String(next));
    accState[rkey] = next; saveAcc();
  });
  roleCb.addEventListener('click', (e) => e.stopPropagation());
  roleCb.addEventListener('change', (e) => {
    const next = e.target.checked;
    allRoleFlows.forEach(f => setFlowOn(f.name, next));
    recomputeGroups();
    applyFilter(); fitActive(400);
  });
  groupRefs.push({ input: roleCb, names: allRoleFlows.map(f => f.name) });

  for (const [cat, flows] of cats) {
    if (!flows.length) continue;
    flows.sort((a, b) => (a.order ?? 999) - (b.order ?? 999) || a.label.localeCompare(b.label));
    const cgroup = document.createElement('div');
    cgroup.className = 'cat-group';
    const ckey = 'cat:' + role + '/' + cat;
    const chead = document.createElement('div');
    chead.className = 'cat-head';
    chead.setAttribute('role','button');
    chead.setAttribute('aria-expanded', String(isOpen(ckey)));
    chead.innerHTML =
      '<span class="chev">▶</span>' +
      '<input type="checkbox" class="group-toggle" title="Alle Workflows dieser Gruppe ein-/ausschalten">' +
      '<span>'+cat+'</span>' +
      '<span class="meta-count">'+flows.length+'</span>';
    const cbody = document.createElement('div');
    cbody.className = 'cat-body';
    cgroup.appendChild(chead); cgroup.appendChild(cbody);
    const catCb = chead.querySelector('.group-toggle');
    chead.addEventListener('click', (e) => {
      if (e.target === catCb) return;
      const next = chead.getAttribute('aria-expanded') !== 'true';
      chead.setAttribute('aria-expanded', String(next));
      accState[ckey] = next; saveAcc();
    });
    catCb.addEventListener('click', (e) => e.stopPropagation());
    catCb.addEventListener('change', (e) => {
      const next = e.target.checked;
      flows.forEach(f => setFlowOn(f.name, next));
      recomputeGroups();
      applyFilter(); fitActive(400);
    });
    groupRefs.push({ input: catCb, names: flows.map(f => f.name) });

    flows.forEach((f) => {
      const el = document.createElement('label'); el.className = 'flow';
      el.title = f.label;
      // seq = journey slot (order/10) — keeps gaps where planned-but-not-yet-recorded
      // flows will eventually slot in (e.g., Extrahieren shows 1 / 7 / 8 today).
      const seq = Math.round((f.order ?? 999) / 10);
      el.innerHTML = '<input type="checkbox" data-flow="'+f.name+'" '+(f.on?'checked':'')+'>'+
        '<span class="seq">'+seq+'.</span>'+
        '<span class="dot" style="background:'+f.color+'"></span>'+
        '<span class="lbl">'+f.label+'</span><span class="meta">'+f.pages+'·'+f.steps+'</span>';
      el.querySelector('input').addEventListener('change', e=>{
        state.set(f.name, e.target.checked);
        recomputeGroups();
        applyFilter(); fitActive(400);
      });
      cbody.appendChild(el);
    });
    rbody.appendChild(cgroup);
  }
  flowsBox.appendChild(rgroup);
}
recomputeGroups();
// re-pack only the VISIBLE steps of each page into a tight grid and re-stack
// the pages. Each flow's consecutive steps get their own row(s) so the
// storyboard reads slot-by-slot (Slot 1 row → Slot 7 row → Slot 8 row).
function repack(){
  const order = ['auth','hub','doc','role'];
  const COL_W = 2450, SDX = 580, SDY = 420, GAP = 460, TOP = 380, COLS = 4, base = 560;
  // Stable journey-order sort using the flowMeta order baked into GRAPH.flows.
  const FLOW_ORDER = Object.fromEntries(GRAPH.flows.map(f => [f.name, f.order ?? 999]));
  order.forEach((stage, ci) => {
    let y = TOP; const cx = ci * COL_W + base;
    cy.nodes('[kind="page"][stage="'+stage+'"]').forEach(pg => {
      const kidsRaw = pg.children().filter(c => !c.hasClass('hidden'));
      if (!kidsRaw.length) { pg.addClass('hidden'); return; }
      pg.removeClass('hidden');
      // Re-sort by journey order so flow-grouping is stable even after the
      // user has dragged things around.
      const kids = kidsRaw.toArray().sort((a, b) => {
        const oa = FLOW_ORDER[a.data('flow')] ?? 999;
        const ob = FLOW_ORDER[b.data('flow')] ?? 999;
        return oa - ob || (a.data('stepIndex') ?? 0) - (b.data('stepIndex') ?? 0);
      });
      // Group consecutive same-flow steps; each group gets its own row(s).
      const groups = [];
      let prev = null;
      for (const k of kids) {
        const f = k.data('flow');
        if (f !== prev) { groups.push([]); prev = f; }
        groups[groups.length - 1].push(k);
      }
      const rowsPer = groups.map(g => Math.ceil(g.length / COLS) || 1);
      const totalRows = rowsPer.reduce((a, b) => a + b, 0) || 1;
      const gridW = COLS * SDX, gridH = totalRows * SDY;
      let rowOffset = 0;
      groups.forEach((group, gi) => {
        group.forEach((s, gk) => {
          const col = gk % COLS;
          const rowInGroup = Math.floor(gk / COLS);
          s.position({
            x: cx - gridW/2 + col * SDX + SDX/2,
            y: y + (rowOffset + rowInGroup) * SDY + SDY/2,
          });
        });
        rowOffset += rowsPer[gi];
      });
      y += gridH + GAP;
    });
  });
}
function applyFilter(){
  cy.batch(()=>{
    cy.elements('[flow]').forEach(el=>{
      const on = state.get(el.data('flow'));
      el.toggleClass('hidden', !on);
      if(el.isNode()) el.toggleClass('show-label', !!on); // label active steps
    });
  });
  repack();
}
applyFilter();
fitActive(0);
window.__layoutDone = true;

// Sidebar width: persisted in localStorage, drag the splitter to resize.
const APP_EL = document.getElementById('app');
const SB_KEY = 'flowgraph.sb-w';
const savedSbW = localStorage.getItem(SB_KEY);
if (savedSbW) APP_EL.style.setProperty('--sb-w', savedSbW);
const sbResizer = document.getElementById('sb-resizer');
let sbDrag = null;
sbResizer.addEventListener('mousedown', (e) => {
  const aside = document.querySelector('aside');
  sbDrag = { sx: e.clientX, sw: aside.getBoundingClientRect().width };
  sbResizer.classList.add('dragging');
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
  e.preventDefault();
});
window.addEventListener('mousemove', (e) => {
  if (!sbDrag) return;
  const w = Math.max(180, Math.min(640, sbDrag.sw + (e.clientX - sbDrag.sx)));
  APP_EL.style.setProperty('--sb-w', w + 'px');
});
window.addEventListener('mouseup', () => {
  if (!sbDrag) return;
  sbDrag = null;
  sbResizer.classList.remove('dragging');
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
  localStorage.setItem(SB_KEY, APP_EL.style.getPropertyValue('--sb-w'));
  if (cy) cy.resize(); // tell cytoscape the canvas geometry changed
});
// double-click resets to default
sbResizer.addEventListener('dblclick', () => {
  APP_EL.style.removeProperty('--sb-w');
  localStorage.removeItem(SB_KEY);
  if (cy) cy.resize();
});

document.getElementById('all').onclick = ()=>{ GRAPH.flows.forEach(f=>state.set(f.name,true)); flowsBox.querySelectorAll('.flow input').forEach(i=>i.checked=true); recomputeGroups(); applyFilter(); fitVisible(400); };
document.getElementById('none').onclick = ()=>{ GRAPH.flows.forEach(f=>state.set(f.name,false)); flowsBox.querySelectorAll('.flow input').forEach(i=>i.checked=false); recomputeGroups(); applyFilter(); };
document.getElementById('fit').onclick = ()=>fitVisible(400);
document.getElementById('reset').onclick = resetGrid;
document.getElementById('physik').onclick = runPhysics;

// lock toggle — freezes node positions against manual dragging (pan/zoom/click stay on)
const LK='width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
const LOCK_ON='<svg '+LK+'><rect x="3" y="11" width="18" height="11" rx="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>Gesperrt';
const LOCK_OFF='<svg '+LK+'><rect x="3" y="11" width="18" height="11" rx="2"></rect><path d="M7 11V7a5 5 0 0 1 9.9-1"></path></svg>Frei';
let locked=false;
const lockBtn=document.getElementById('lock');
function renderLock(){
  lockBtn.innerHTML = locked ? LOCK_ON : LOCK_OFF;
  lockBtn.classList.toggle('on', locked);
  lockBtn.title = locked ? 'Knoten gesperrt — klicken zum Entsperren' : 'Knoten frei beweglich — klicken zum Sperren';
  cy.autoungrabify(locked);
  cy.autounselectify(locked);
  cy.boxSelectionEnabled(!locked);
  // Compound parents (the big role/category/page boxes) are the wide drag
  // surfaces. events:'no' on them while locked lets a drag on their empty
  // area fall through to the canvas so pan works. Leaf step nodes keep
  // events so tap-to-inspect stays functional.
  cy.nodes(':parent').forEach(n => {
    if (locked) n.style('events', 'no');
    else n.removeStyle('events');
  });
}
lockBtn.onclick = ()=>{ locked=!locked; renderLock(); };
renderLock();

// While locked, dragging a step thumbnail should pan the canvas (clicks still
// fall through to the tap-inspector handler below). autoungrabify alone makes
// the node un-movable but Cytoscape swallows the gesture without panning.
let _lockPan = null;
cy.on('tapstart', 'node[!kind][thumb]', (e) => {
  if (!locked) return;
  const o = e.originalEvent;
  if (!o || typeof o.clientX !== 'number') return;
  _lockPan = { sx: o.clientX, sy: o.clientY, px: cy.pan().x, py: cy.pan().y };
});
cy.on('tapdrag', (e) => {
  if (!_lockPan) return;
  const o = e.originalEvent;
  if (!o) return;
  cy.pan({ x: _lockPan.px + (o.clientX - _lockPan.sx), y: _lockPan.py + (o.clientY - _lockPan.sy) });
});
cy.on('tapend', () => { _lockPan = null; });

// ---- step labels appear on hover/zoom of a step's flow ----
cy.on('mouseover','node[!kind]', e=>e.target.addClass('show-label'));
cy.on('mouseout','node[!kind]', e=>e.target.removeClass('show-label'));

// Hover a step on the canvas → highlight that flow's row (+ ancestors) in the
// sidebar. Helps locate which sidebar entry a thumbnail belongs to, especially
// when many flows are active or the sidebar is scrolled.
function clearSidebarHover() {
  flowsBox.querySelectorAll('.canvas-hover').forEach(el => el.classList.remove('canvas-hover'));
}
function setSidebarHover(flowName) {
  // Always replace any previous highlight — at most one row is hovered at a time.
  clearSidebarHover();
  if (!flowName) return;
  const cb = flowsBox.querySelector('input[data-flow="' + CSS.escape(flowName) + '"]');
  const row = cb?.closest('.flow');
  if (!row) return;
  row.classList.add('canvas-hover');
  row.closest('.cat-group')?.querySelector('.cat-head')?.classList.add('canvas-hover');
  row.closest('.role-group')?.querySelector('.role-head')?.classList.add('canvas-hover');
  row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}
cy.on('mouseover', 'node[!kind]', e => setSidebarHover(e.target.data('flow')));
cy.on('mouseout',  'node[!kind]', () => clearSidebarHover());
// Mouse leaves the canvas entirely → cytoscape sometimes misses the final
// mouseout, so we also clear from the container-level mouseleave.
cy.container().addEventListener('mouseleave', clearSidebarHover);

// ---- inspector ----
const insp = document.getElementById('inspector');
const esc = s => (s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
cy.on('tap','node[kind="page"]', e=>{
  const d=e.target.data();
  const notes=d.notes||[], shots=d.shots||[];
  insp.innerHTML='<h3>'+esc(d.label)+'</h3><div class="where">'+d.flowCount+' Flows · '+notes.length+' Notizen · '+shots.length+' Screenshots im Graph</div>'+
    (notes.length?notes.map(n=>'<div class="note">'+esc(n.text)+'<span class="nf">'+esc(n.flow)+'</span></div>').join(''):'<div class="empty">Keine Notizen auf dieser Seite.</div>');
});
cy.on('tap','node[!kind]', e=>{
  const d=e.target.data();
  insp.innerHTML='<h3>'+esc(d.title)+'</h3>'+
    '<div class="where"><span class="badge" style="background:'+d.color+';color:#0b1117">'+esc(d.flow)+'</span><span class="badge">'+esc(d.page)+'</span></div>'+
    (d.notes.length?d.notes.map(n=>'<div class="note">'+esc(n)+'</div>').join(''):'<div class="empty">Keine Notiz an diesem Schritt.</div>')+
    (d.actions.length?'<div class="seclabel">Aktionen</div><div class="acts">'+d.actions.map(esc).join('\\n')+'</div>':'');
});
cy.on('tap', e=>{ if(e.target===cy){ insp.innerHTML='<div class="empty">Klicke eine <b>Seite</b> oder einen <b>Schritt</b>.</div>'; } });
</script>
</body></html>`;
}

// ---------------------------------------------------------------------------
console.log("Building walkthrough flow map…");
if (!selfTest()) process.exit(1);
const graph = build();
const pageCount = graph.elements.filter((e) => e.data.kind === "page").length;
const stepCount = graph.elements.filter((e) => e.data && !e.data.kind && e.data.parent).length;
const edgeCount = graph.elements.filter((e) => e.data.source).length;
console.log(`  ${graph.flows.length} flows · ${pageCount} pages · ${stepCount} steps · ${edgeCount} edges`);
const outFile = join(__dirname, "flow-graph.html");
writeFileSync(outFile, html(graph));
console.log(`  wrote ${outFile}`);
