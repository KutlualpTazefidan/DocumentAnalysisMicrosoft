# Knowledge Tab + Open Knowledge Format (OKF) Integration — Design

**Date:** 2026-06-25
**Status:** Design — awaiting user review
**Branch:** `feat/agent-tab-deepagents-spike`

## Goal

Capture expert-interview knowledge as a **Google Open Knowledge Format (OKF)**
knowledge base, browsable in a new global **Knowledge** tab, and lay the seam so
our deepagents can later *choose* an OKF base as their retrieval base — all
additively, without touching the proven Azure-AI-Search retrieval path.

## Scope

This design covers the **whole structure** (both halves), but only **Part A** is
built first. Part B is designed here and deferred to a follow-up plan.

- **Part A — Produce & view OKF knowledge (BUILD FIRST).** Convert the LM
  interview to text → an extraction agent drafts OKF concept files → a read-only
  Knowledge tab browses the resulting concept graph.
- **Part B — Choosable agent base (DESIGN NOW, BUILD LATER).** An additive
  `build_kb_agent(base)` variant + three file-reading OKF tools, with base
  selection via an endpoint/UI param. The existing `build_agent` / `azure_ai_search`
  path stays byte-unchanged.

### Decisions locked with the user (2026-06-25)

1. **Altitude:** first slice ends at "LM interview is real OKF files, browsable
   in the Knowledge tab." Agent-uses-OKF is Part B (next plan).
2. **Tab placement:** global / top-level nav (knowledge is cross-document, not
   scoped to one Versandstück).
3. **Authoring:** agent-assisted extraction → human review.
4. **Storage (D1):** gitignored `data/knowledge/` — not committed.
5. **Editing (D2):** read-only viewer; edits happen directly in the files.
6. **Trigger (D3):** no extraction-trigger UI.
7. **Extraction reuse (D4):** one-off *orchestration* for this interview, **but
   the extraction principles + OKF schema are persisted as a reusable, versioned
   prompt artifact** (`OKF_EXTRACTION` in `local_pdf/agent/extract_prompts.py`,
   mirroring `verify_prompts.py`) so every future interview is extracted
   consistently. The reusable *runner/CLI* waits for interview #2.

## Background

### Google OKF v0.1 (the format we adopt)

Source: [Google Cloud Blog — How the Open Knowledge Format can improve data
sharing](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing)
(published 2026-06-12).

OKF is intentionally minimal:

- A knowledge base is a **directory of markdown files**; **one concept per file**.
- The **file path is the concept's identity** (e.g. `/regelwerk/r003.md`).
- Each file starts with **YAML frontmatter**. The **only required field is
  `type`** (a producer-defined classifier). Recommended optional fields:
  `title`, `description`, `resource` (a URL), `tags` (array), `timestamp`
  (ISO 8601).
- Concepts link to each other with **ordinary markdown links** using
  root-relative paths (`[BAM](/behoerden/bam.md)`). Those links turn the folder
  into a **graph** richer than the directory hierarchy.
- Reserved filenames: **`index.md`** (per-directory navigation / progressive
  disclosure) and **`log.md`** (optional change history).

Consequence for us: **no graph database, no triple-store, no embeddings, no SDK**
is required. An OKF base is plain files read off disk.

### The source interview

`data/interview/Text-Int-BAM3.3-LM_26.06.23.docx` — a transcript of Dr. Lars
Müller (Bauprüfer, BAM Fachbereich 3.3) describing the *Bauartprüfung* process
for radioactive-transport packages (Versandstücke): the BAM/BASE division of
responsibility, the R 003 directive, the PDSR Guide (IAEA SSG-66), the
application/assessment workflow, the Nachweiskonzept, document structures
(PDSR vs GNS), and the BAM GGR rules. It is the **first** of several planned
interviews.

## Architecture overview

```
                          Part A (build first)
  data/interview/*.docx ──► docx_to_text ──► extraction agent ──► data/knowledge/<base>/*.md
   (gitignored source)        (helper)      (deepagents, GPT-4.1)   (OKF concept graph, gitignored)
                                                                          │
                                                       knowledge reader (pure file I/O)
                                                                          │
                                              /api/admin/knowledge/*  ◄────┤
                                                      │                    │
                                              Knowledge tab (global) ──────┘  validator / linter
                                              browse base → concept → graph

                          Part B (design now, build later)
  data/knowledge/<base>/  ──► OKF agent tools (list/read/search) ──► build_kb_agent(base)
                                                                   selected via endpoint/UI param
                              (existing build_agent / azure_ai_search untouched)
```

**Non-invasive guarantee:** every new artifact is *additive*. No edits to
`features/pipelines/microsoft/retrieval/`, ingestion, the existing Agent path,
or any Azure infra. Savepoint tag before starting (`pre-knowledge-okf`) and after
each milestone, mirroring the verifier spike.

## Components

### A1. Storage layout & location

OKF bases live under **`data/knowledge/<base>/`** — gitignored runtime content,
consistent with the source interview's own treatment in `data/` and avoiding a
premature commit of DSGVO-relevant, expert-attributed content (see Open
Decision D1).

First base: **`bauartpruefung-lm`**.

```
data/knowledge/bauartpruefung-lm/
├── index.md                       # root: overview + entry points + provenance
├── behoerden/{bam,base}.md        # type: Behörde
├── regelwerk/
│   ├── r003.md                    # type: Richtlinie
│   ├── pdsr-guide.md              # type: Richtlinie  (Package Design Safety Report)
│   ├── ssg-66.md                  # type: Richtlinie  (IAEA)
│   ├── ggr-008.md                 # type: Regelwerk   (numerische Berechnungen)
│   ├── ggr-011.md                 # type: Regelwerk   (Qualitätsmanagement)
│   ├── ggr-023.md                 # type: Regelwerk   (Alterungsmanagement)
│   └── iso-17025.md               # type: Norm
├── verfahren/
│   ├── bauartpruefung.md          # type: Verfahren
│   └── antragsverfahren.md        # type: Verfahren
├── rollen/{antragfuehrer,antragsteller,experten}.md   # type: Rolle
├── konzepte/{nachweiskonzept,managementsystem}.md     # type: Konzept
├── pruefthemen/                   # type: Prüfthema
│   ├── mechanische-auslegung.md / thermische-auslegung.md
│   ├── aktivitaetsrueckhaltung.md / abschirmung.md / kritikalitaet.md
├── strukturen/                    # type: Dokumentstruktur
│   ├── pdsr-struktur.md / gns-struktur.md
│   └── package-performance-characteristics.md
├── artefakte/assessment-chart.md  # type: Artefakt
├── begriffe/versandstueck-typen.md# type: Begriff  (B(U), B(M), C, UF6, …)
└── log.md
```

### A2. OKF schema for our domain

Producer-defined `type` vocabulary (starter set, extensible):
`Behörde`, `Richtlinie`, `Regelwerk`, `Norm`, `Verfahren`, `Rolle`, `Konzept`,
`Prüfthema`, `Dokumentstruktur`, `Artefakt`, `Begriff`.

Frontmatter we use: `type` (required), `title`, `description`, `tags`,
`timestamp`. `resource` only where a real canonical URL exists (most domain
concepts have none — omit rather than fake).

Example concept (`verfahren/bauartpruefung.md`):

```markdown
---
type: Verfahren
title: Bauartprüfung
description: Prüfung zulassungspflichtiger Versandstücke für den Transport radioaktiver Stoffe.
tags: [bauartpruefung, versandstueck, zulassung]
timestamp: 2026-06-25T00:00:00Z
---

Die Bauartprüfung wird von [BAM](/behoerden/bam.md) (mechanische und thermische
Auslegung, [Aktivitätsrückhaltung](/pruefthemen/aktivitaetsrueckhaltung.md),
[Managementsystem](/konzepte/managementsystem.md)) und [BASE](/behoerden/base.md)
([Abschirmung](/pruefthemen/abschirmung.md), [Kritikalität](/pruefthemen/kritikalitaet.md))
durchgeführt. Grundlage ist die [R 003](/regelwerk/r003.md); zu beachten ist der
[PDSR-Guide](/regelwerk/pdsr-guide.md) (IAEA [SSG-66](/regelwerk/ssg-66.md)). Der
Nachweis erfolgt nach dem [Nachweiskonzept](/konzepte/nachweiskonzept.md).
```

### A3. Interview → text (`docx_to_text` helper)

A small helper converts a `.docx` to clean UTF-8 text (one paragraph per line).
Implementation: `python-docx` if importable, else an `unzip + strip-XML`
fallback (validated to work on this file). Output is fed to the extraction
agent. Lives in the knowledge module; no restricted imports.

### A4. Agent-assisted authoring (one-off pass)

We have exactly **one** interview, so the *orchestration* is a **one-off
agent-assisted authoring pass** — no CLI subcommand, no multi-interview runner
yet. But the **extraction principles + OKF schema are persisted as a reusable,
versioned prompt artifact** so every future interview is extracted the same way:
`OKF_EXTRACTION` in `local_pdf/agent/extract_prompts.py` (mirrors
`verify_prompts.py`). The one-off pass loads `OKF_EXTRACTION`, reads the
interview text, and emits OKF concept files into
`data/knowledge/bauartpruefung-lm/`; the controller persists them and a human
reviews them (A4-review below). The reusable *runner/CLI* is deferred until
interview #2 (YAGNI) — only the prompt is durable now.

Curation principles encoded in `OKF_EXTRACTION` (the persisted, reusable
artifact — this is what makes extraction consistent across interviews):
- **Faithful to source.** Do not invent facts not in the transcript.
- **Normalize transcription noise.** Map obvious artifacts to correct domain
  terms (`Bauer Zulassung`→Bauartzulassung, `Bus`→BASE, `Bahn`/`Baum`→BAM,
  `PDS er`→PDSR, `GGR 0 11`→GGR 011, `besonderer Form`/`Strato aktive`→radioaktive
  Stoffe in besonderer Form).
- **Flag uncertainty.** Where the transcript is ambiguous or likely wrong (e.g.
  BASE expanded as "…nuklearen Erzeugung" vs the correct "…nuklearen Entsorgung"),
  record a `> [!review]` note in the body rather than silently guessing.
- **Link generously.** Cross-reference every concept it mentions.

**No extraction UI** in this slice. Human edits happen in the files; an in-tab
editor is out of scope (D2).

### A4-review. Faithfulness review — the semantic gate

`validate_base` (A6) is the **structural** gate (types present, links resolve) —
it cannot tell faithful from plausibly-wrong. Because the transcript is noisy,
the **semantic** gate is a **human reading 2–3 produced concepts for faithfulness
to the source** before any viewer is built. The plan front-loads this: author
the base → human faithfulness review → only then build reader/endpoint/tab. This
guards against a sloppy extraction making OKF look like a poor domain fit when
the real fault is extraction quality.

### A5. Knowledge reader (pure file I/O)

Module `local_pdf/knowledge/` (co-located with the api + agent; **no** Azure/
openai imports, so import-boundary-clean — promote to `features/core` later if
shared). Canonical read API:

- `list_bases() -> list[BaseSummary]` — directories under `data/knowledge/`.
- `list_concepts(base) -> list[ConceptSummary]` — path, type, title, tags.
- `read_concept(base, path) -> Concept` — frontmatter + raw body + parsed
  outgoing links (resolved + unresolved).
- `search_concepts(base, query) -> list[ConceptSummary]` — case-insensitive
  keyword match over title/body/tags (no embeddings; ~25 concepts).

**Link semantics (one source of truth).** OKF outgoing links are root-relative
with root = the base dir: `[BAM](/behoerden/bam.md)` → concept path
`behoerden/bam.md`. The reader strips the leading slash to produce the API's
`?path=` value and sets `resolved` by checking the target file exists. The
viewer (A8) reuses the **same** normalization for click-through, so reader and
tab never disagree — pinned by a click-through test (see Testing). Paths are
confined to the base dir (reject `..`/absolute escapes).

Frontmatter parsed with `pyyaml` (verify availability in Task 0; tiny
hand-rolled splitter fallback). Malformed frontmatter → concept surfaced with a
`malformed: true` flag, never a crash.

### A6. OKF validator / linter

`validate_base(base) -> list[Issue]`: every file has a `type`; every outgoing
markdown link resolves to an existing file; warns on orphans (no inbound links,
excluding `index.md`). Doubles as extraction QA and a test oracle.

### A7. Knowledge admin endpoint

`features/pipelines/local-pdf/src/local_pdf/api/routers/admin/knowledge.py`,
registered in `app.py` (`include_router`). Auto-gated by the existing
`/api/admin/*` ASGI auth middleware (no `Depends`). Read-only JSON:

- `GET /api/admin/knowledge/bases` → `[{name, title, concept_count}]`
- `GET /api/admin/knowledge/bases/{base}/concepts` → `[{path, type, title, tags}]`
- `GET /api/admin/knowledge/bases/{base}/concept?path=…` →
  `{type, title, description, tags, timestamp, body, links: [{text, path, resolved}]}`

### A8. Knowledge tab (global, read-only viewer)

- **Nav:** a top-level entry in the **global** admin rail `ADMIN_NAV`
  (`shell/AdminShell.tsx:12-18`, rendered by `<IconRail>`), alongside the
  existing global pages (Dokumente, Kuratoren, Fachbereiche, Pipelines,
  Übersicht) — **not** the doc-scoped `DocStepTabs.tsx`. New `RailItem`:
  `{ to: "/admin/knowledge", match: "/admin/knowledge", label: "Wissen", icon: <knowledge icon from ../shared/icons, e.g. Library/Network> }`,
  plus the icon import. Route `/admin/knowledge` registered in `App.tsx` under
  `<AdminShell>` next to the other global routes (`dashboard`, `pipelines`,
  `tenants`, `settings`). Label "Wissen" keeps the rail's German naming
  (override to "Knowledge" if preferred — trivial).
- **Component** `frontend/src/admin/routes/Knowledge.tsx`: three-pane browse —
  base selector → concept list (grouped by `type`) → concept view. Concept view
  renders frontmatter as a header chip-row + the markdown body; **outgoing links
  are clickable** and navigate to the linked concept (this is how you walk the
  graph). Unresolved links render visually distinct (dead, non-clickable). A
  keyword filter box drives `search_concepts`.
- Streaming not needed (plain JSON). `bam-cyan` accent, consistent with Agent.

### Part B (designed, deferred)

- **OKF agent tools** (`local_pdf/agent/okf_tools.py`): `list_concepts`,
  `read_concept`, `search_concepts` — thin `@tool` wrappers over A5. Pure file
  reads → import-boundary-clean.
- **`build_kb_agent(base)`** in `build.py`: a new additive variant (mirrors
  `build_verifier_agent`) wiring `_build_model()` + the OKF tools + a
  graph-navigation system prompt. `build_agent` / `azure_ai_search` untouched.
- **Base selection:** `/api/admin/agent/ask` (or a new `/agent/ask-kb`) accepts a
  `base` param; absent/`"azure"` → existing Azure path; an OKF base name →
  `build_kb_agent`. UI: a base dropdown in the Agent tab. Existing default
  behavior unchanged.

## Data flow (Part A)

1. A one-off agent-assisted pass authors the base →
   `data/knowledge/bauartpruefung-lm/`.
2. **Semantic gate:** a human reads 2–3 concepts for faithfulness (A4-review).
   **Structural gate:** `validate_base` confirms types present + links resolve.
   Issues fixed by hand/agent — all before any viewer work.
3. Admin opens **Knowledge** tab → `GET /bases` → picks `bauartpruefung-lm`.
4. → `GET /concepts` lists concepts grouped by type.
5. → clicks a concept → `GET /concept?path=…` → renders frontmatter + body;
   clicking an outgoing link re-issues `GET /concept` for the target.

## Error handling

- Unknown base / concept path → 404. Path traversal (`..`, absolute escapes) →
  400 (reader confines reads to the base dir).
- Malformed frontmatter → `malformed: true`, file still listed/openable.
- Broken links → reader marks `resolved: false`; viewer shows them dead.
- docx parse failure in extraction → fail loudly with the offending file.

## Testing strategy

- **Reader (pytest):** tiny fixture base under `tmp_path` — assert
  `list_concepts`, `read_concept` (frontmatter + outgoing-link extraction),
  `search_concepts` keyword hit, malformed-file flag, traversal rejection.
- **Validator (pytest):** fixture with a broken link + a typeless file → exact
  Issue list.
- **Endpoint (httpx):** tmp base via dependency/env override — JSON shapes +
  `/api/admin/*` auth gating (401 without token).
- **Frontend (vitest + msw):** mock `**/api/admin/knowledge/**` (narrow glob, per
  the screenshot-mocking lesson) → base list → concept list → concept view →
  clicking an outgoing link loads the target.
- **Authored base:** `validate_base` is the *structural* gate (every file typed,
  links resolve). The *semantic* gate is the human faithfulness review
  (A4-review) — not an automated assertion, and front-loaded before viewer work.

## Non-invasive guarantees & savepoints

- Tag `pre-knowledge-okf` before Task 1; tag `knowledge-okf-view-v1` after Part A.
- Existing Agent / verifier / retrieval paths: zero edits (verified by diff).
- All new Python is import-boundary-clean (no openai/azure/langchain in the
  reader, validator, endpoint; the extraction + Part B agents import deepagents
  lazily, like the existing agent module).

## Out of scope (YAGNI)

Embeddings / vector index over OKF; graph database; in-tab concept editing;
extraction-trigger UI; multi-tenant/per-user bases; OKF *export* for external
consumers; automatic re-extraction on interview change.

## Decisions (resolved 2026-06-25)

- **D1 — Commit the base? → Gitignored.** `data/knowledge/` stays gitignored
  (matches the source interview, defers DSGVO exposure). Revisit a committed,
  pseudonymized base after DSGVO review (cf. pseudonym-provisional).
- **D2 — Editing? → Read-only.** Viewer only; edits happen directly in the
  files. An in-tab editor can be a later, separate UI tool.
- **D3 — Extraction trigger? → None.** No extraction-trigger UI; one-off
  authoring pass.
- **D4 — Extraction reuse? → Persist the prompt, defer the runner.** One-off
  *orchestration* now (no CLI / multi-interview runner), but persist the
  extraction principles + OKF schema as a reusable, versioned prompt
  (`OKF_EXTRACTION`, `extract_prompts.py`) so future interviews are extracted
  consistently. The reusable runner/CLI is deferred until interview #2.
