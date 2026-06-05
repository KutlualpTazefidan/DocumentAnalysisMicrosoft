---
title: Walkthrough Audit & Update Plan
date: 2026-06-05
status: executed (2026-06-05) — Phase 1 (note fixes) + Phase 2 (10 new scripts) landed; Phase 3 (re-record) deferred to when the backend is up
scope: tests/walkthrough/record/*.mjs — audit vs current (post-BAM-reskin) code, coverage gaps, 4 new scenarios
method: 24-agent workflow (19 per-script audits + coverage map + 4 scenario designs), each grounded by reading current src
---

# Walkthrough Audit & Update Plan

## TL;DR

- **Nothing is broken.** All 19 existing record scripts still resolve their selectors and drive valid flows. They use `data-testid` + visible German text, which the BAM re-skin did **not** change.
- **7 scripts need a cosmetic note touch-up** (stale colour words, one stale timing value, two stale button-label references, one hard-coded old-brand outline colour). No logic changes. 12 scripts are clean.
- **Coverage has real holes.** Seven user-facing features have **no** record script — most were once recorded (their `output/` dirs survive) but lost their scripts on the obsolete `feat/ui-walkthrough` branch.
- **4 new scenarios designed and selector-verified** (Vergleich, Login+auth+tenants, Statistik+Voting, end-to-end). Two corrections noted below before these get written.

## Execution status (2026-06-05)

Done on branch `chore/walkthrough-audit-update` (based on the re-skin branch, since the notes/selectors describe the post-#56 UI):

- **Phase 1** — 8 note fixes across 7 scripts (Part A table). `node --check` clean. *(commit: refresh notes for the BAM re-skin + label drift)*
- **Phase 2** — all 10 new scripts written (4 designed + 6 backlog), each authored against current src and adversarially selector-verified by a second agent; `node --check` clean. *(commits: "4 new high-priority scenarios", "6 backlog scripts …")*
  - `login-auth-tenants` required a real fix beyond authoring: TenantsAdmin is **cookie-only** (`apiFetch(path, "")` never sends `X-Auth-Token`), so Phase 3 now establishes a real `lpdf_session` via `POST /api/auth/login` (env-configurable creds, graceful skip if absent).
- **Phase 3** — re-recording deferred (needs `:8001` + a processed doc + valid creds). The scripts are static-verified but **not yet run** end-to-end.

Out-of-scope issue surfaced by the audit (noted, not fixed here): `DocCurators.tsx` assign-toast reads `data.name`, which the assign response doesn't return → renders "Assigned undefined". One-line frontend fix for a separate PR.

---

## Part A — Audit of the 19 existing scripts

`status`: **ok** = runs + notes accurate · **needs-update** = runs but a note/label is stale · **broken** = a selector/route/flow no longer exists.

| Script | Area | Status |
|---|---|---|
| extract-box-create | extract | ok |
| extract-box-edit | extract | needs-update |
| extract-box-merge | extract | needs-update |
| extract-export | extract | ok |
| extract-page-extract | extract | needs-update |
| extract-register-detect | extract | ok |
| extract-text-edit | extract | needs-update |
| synthese-box-select | synthese | ok |
| synthese-deprecate | synthese | ok |
| synthese-edit-answer | synthese | ok |
| synthese-generate | synthese | ok |
| synthese-page-lock | synthese | needs-update |
| provenienz-agent-tour | provenienz | ok |
| provenienz-iterate | provenienz | needs-update |
| provenienz-plan-override | provenienz | ok |
| provenienz-session-crud | provenienz | ok |
| provenienz-stage-tour | provenienz | ok |
| curator-add-question | curator | ok |
| upload-pdf | upload | ok* |

`*` upload-pdf runs fine; the one fix is a hard-coded outline colour (cosmetic, screenshots only).

### The 8 fixes (across 7 scripts)

Each is a one-line note/string edit — no flow or selector logic changes.

| # | Script:line | Issue | Fix |
|---|---|---|---|
| 1 | `extract-box-edit:65` | Note says reset button is `„Reset to YOLO"`; actual label is `Zurücksetzen` (German refactor) | → `„Zurücksetzen"` |
| 2 | `extract-page-extract:38` | `Alle Seiten extrahieren` described as `(oben, blau)`; re-skin made it BAM cyan | → `(oben, cyan)` |
| 3 | `extract-page-extract:62` | Note says StageIndicator is `oben rechts`; it renders bottom-left (`bottom-2 left-2`) | → `unten links` |
| 4 | `extract-text-edit:63` | Double-click window noted as `~500 ms`; `SECOND_CLICK_WINDOW_MS = 800` | → `~800 ms` |
| 5 | `synthese-page-lock:53` | Lock button noted as `(Blau-Variant)`; now `btn-primary` = BAM cyan | → `(BAM-Cyan-Variant)` or drop the parenthetical |
| 6 | `provenienz-iterate:140` | Proposal tile noted `hellblau`; re-skin made it amber (`border-amber-500 bg-amber-50`) | → `amber (golden/orange)` |
| 7 | `upload-pdf:89` | Injects `outline = "3px solid #1E7EB2"` (old brand blue) | → `#00aff0` (BAM cyan) |
| 8 | `extract-box-merge:72,76` | Notes call panel buttons `„Merge down"/„Merge up"`; visible labels are `Verbinden ↓/↑` (unmerge = `Trennen ↓/↑`, aria-label `Merge up/down`) | → reference `Verbinden ↓/↑` |

Items 2, 5, 6, 7 are direct BAM-re-skin artifacts; 1, 4, 8 are pre-existing drift (German refactor / constant change) surfaced by the audit; 3 is a layout-position drift.

---

## Part B — Coverage map

### Covered (19 features → 19 scripts)
Upload/Inbox, Extract (box create/edit/merge, export, page-extract, register-detect, text-edit), Synthese (box-select, deprecate, edit-answer, generate, page-lock), Provenienz (agent-tour, iterate, plan-override, session-crud, stage-tour), Curator add-question.

### Gaps — features with NO record script

| Priority | Feature | Route | Why it matters |
|---|---|---|---|
| **high** | Vergleich / Comparison | `/admin/doc/:slug/compare` | Core admin stage (Microsoft pipeline search + answer + compare). Heavily re-skinned, **zero** coverage. |
| **high** | Statistik + Voting | `/admin/doc/:slug/statistics` | Phase-D feature (PR #51): votes + weighted dashboards. No coverage. |
| **high** | Document-Curators assignment | `/admin/doc/:slug/curators` | Assign/unassign curators per doc. |
| **high** | Global Curators management | `/admin/curators` | Create/revoke curator accounts + tokens. |
| **high** | Tenants admin | `/admin/tenants` | Tenant + user CRUD (multi-tenant admin). |
| **high** | vLLM topbar control | `/admin` (BamHeader centerSlot) | Start/stop vLLM, pick model, view logs — gates all LLM features. |
| **high** | Login & auth gate | `/login` + shell role-redirect | Gates everything; the failure path (401→redirect) is untested. |
| medium | Settings / account / logout | `/admin/settings` | Basic user journey. |
| medium | Inbox file search | `/admin/inbox` filter | Live filename/slug filter. |
| medium | Curator journey (end-to-end) | `/curate/...` | Integrated curator flow. |
| low | Landing page | `/` | Entry + login modal. |
| low | Curator-activity / Pipelines / Dashboard | stubs | Not implemented yet — skip until built. |

### Lost scripts (orphaned `output/` with no `record/*.mjs`)
These flows were recorded before and lost their scripts (obsolete `feat/ui-walkthrough` branch):
`login-and-tenant-admin`, `auth-failure`, `tenant-edit-and-delete`, `vllm-topbar-inspect`, `curator-journey`, `curator-management`, `dateien-suche`, `admin-inbox-to-extract`, `extract-stage-tour`, `extrahieren-lock`.
→ The 4 new scenarios below re-establish the most valuable of these (login/auth/tenants, plus net-new Vergleich + Statistik/Voting); the rest are listed as a follow-up backlog.

---

## Part C — 4 new scenario designs

All selectors below were verified against current source unless flagged. Each becomes a `record/<name>.mjs` using the existing `Recorder`.

### C.1 `vergleich-microsoft-search` (high)
**Goal:** record the full Vergleich pipeline — pick a question → choose/upload a Microsoft source → search → review/toggle chunks → generate answer → compare (BM25/Cosine) → similar-questions.
**Steps (11):** load compare tab → select question (`compare-question-{id}`) → pick source (`ms-source-{slug}` / `ms-upload`) → pipeline check (`compare-pipeline-select`) → search (`compare-search`) → chunk cards (`chunk-checkbox-*`, `chunk-toggle-*`, `chunks-select-all`) → answer (`compare-answer`) → compare (`compare-compare`) → per-chunk metrics → similar block (`similar-card-{id}`) → page nav/lock.
**Selectors:** 22 verified, 0 missing.
**Prereqs:** doc with questions that have reference answers; a Microsoft source in `indexed` state (or a PDF to upload + wait for indexing); Azure Search + embeddings configured (else Cosine=0).
**Risks:** Azure latency 3–10s; LLM answer 5–15s; empty-chunks/embedder-off fallbacks; needs a populated source.

### C.2 `login-auth-tenants` (high)
**Goal:** three linked phases — successful login (GOLDENS lockup + dev banner), auth-failure (401), tenant CRUD + logout.
**Steps (14):** login card → fill `input[aria-label='Fachbereich'|'Benutzername'|'Passwort']` → submit → admin shell → wrong-password → `div[role='alert']` error → Tenants page → create tenant modal → create user → edit → delete (confirm) → logout→login redirect.
**Selectors:** 19 verified, 0 missing.
**Prereqs:** backend with ≥1 tenant + valid creds; clean session/cookies.
**Risks:** `window.confirm` on delete needs a dialog handler in headless; framer-motion modal timing; created test tenants/users need teardown.

### C.3 `statistik-voting` (high)
**Goal:** approve + reject votes in Synthese (emerald/red left-stripe + counts), then tour the Statistik dashboards (MetricGauge ×2 + VoteDistributionBar).
**Steps (9):** Synthese tab → approve Q1 (`aria-label='Einverstanden'`) → reject Q2 (`aria-label='Disqualifizieren'`) → Statistik tab → Curator-Überleben gauge → Reviewer-Zustimmung gauge → `Stimmen pro Frage (Top 20)` bar → light-theme check → persistence across tabs.
**Selectors:** 15 verified, **1 correction** ⚠ — there is **no** `h2:has-text('Statistik')` in `Statistics.tsx`. Anchor on the **tab** `nav[role='tablist'] a:has-text('Statistik')`, the section `h2:has-text('Synthese')`, and the MetricGauge labels (`Curator-Überleben`, `Reviewer-Zustimmung`).
**Prereqs:** published doc with ≥2 generated questions.
**Risks:** vote-count races if shared; small icon-button selectors; stats `useQuery` staleness.

### C.4 `e2e-real-case` (high)
**Goal:** one long thread Upload → Extrahieren → Synthese → Voting → Vergleich → Provenienz → Statistik, two sessions (admin + curator) for the anti-anchoring vote check.
**Steps (26):** login → inbox → upload → extract (box inspect, table-cell PR #52 check) → synthese (generate, edit) → 2nd session curator → anti-anchoring before/after vote → approve/reject/revoke cross-session → Vergleich → Provenienz → Statistik (3 sections + gauge reflects votes) → auth-gate logout check → re-login persistence → BAM-colour check.
**Selectors:** 20 verified, but **2 reconciliations** ⚠:
  - login selectors here were drafted as `input[name='username']` / `button:has-text('LOGIN')` — use the **C.2-verified** `input[aria-label='Fachbereich'|'Benutzername'|'Passwort']` + the real submit label (`Einloggen`) instead.
  - steps 24–25 reference `h2:has-text('Statistik')` — same non-existent anchor as C.3; use the tab + section anchors.
**Prereqs (heavy):** backend on :8001 + processed multi-page PDF (table+heading+bibliography); vLLM healthy; two non-cookie-sharing browser sessions; Azure source for Vergleich (stub with empty result if absent).
**Risks:** MinerU extraction 5–15 min (use a pre-extracted slug); cookie contamination breaks anti-anchoring; PDF canvas async (screenshot timing); Vergleich needs Azure or stub.

---

## Part D — Proposed execution plan

**Phase 1 — Fix the 8 stale notes (no backend).** Apply Part A's table verbatim across the 7 scripts. Pure note/string edits; verifiable by reading the diff. One commit: `chore(walkthrough): refresh notes for the BAM re-skin + label drift`.

**Phase 2 — Write the 4 new record scripts.** Author `record/{vergleich-microsoft-search,login-auth-tenants,statistik-voting,e2e-real-case}.mjs` using the existing `Recorder`, with the Part C corrections folded in. Scripts are static (don't run without a backend), so they're reviewable as code. One commit per script (or grouped by area).

**Phase 3 — (optional, needs you) Re-record.** Once a backend (`:8001`) + processed doc + token are available, run the updated + new scripts to regenerate `output/` screenshots against the BAM-skinned UI, then `node build-flow-graph.mjs` to refresh `flow-graph.html`. I can drive this if you bring the backend up, or you run it yourself.

**Backlog (not in this pass):** re-establish the remaining lost scripts (`vllm-topbar-inspect`, `curator-journey`, `dateien-suche`, doc/global-curators, settings) and refresh `docs/walkthroughs/end-to-end-smoke.md`'s `covers:`/`last_reviewed:` to include the re-skin.

### Open decisions for you
1. **Phases 1+2 now** (fix notes + write the 4 scripts, no backend), with Phase 3 re-recording deferred to when you can run the backend? (my recommendation)
2. Want the **backlog** lost-scripts (vLLM topbar, curator journey, doc/global curators, settings) folded into Phase 2, or kept as a separate follow-up?
3. For `e2e-real-case`: keep it as **one mega-script**, or split into per-stage scripts that share a setup helper (more robust, easier to re-record selectively)?
