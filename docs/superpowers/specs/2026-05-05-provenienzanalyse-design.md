# Provenienzanalyse — Design Spec

**Status:** Draft for review
**Date:** 2026-05-05
**Tab label:** Provenienz
**Depends on:** A.5 synthesise (LLM client abstraction), Vergleich (search-pipeline patterns, react-flow not yet — will add)

---

## 1. Goal

Given any extracted chunk, let a human + an agent collaboratively
trace the **provenance** of every claim it contains: where the claim
comes from, what supporting / contradicting evidence the corpus has,
how the agent reasoned at each step, and what the human decided.

The output is an **append-only knowledge graph** stored as an event
log. Every node and every edge is auditable: who created it (human
or which LLM), what the reasoning was, what alternatives were
proposed and rejected.

The system is opinionated only about *the auditing pattern*; the
*node kinds*, *edge kinds*, *search backend*, and *LLM provider* are
all extensible without core changes.

## 2. Non-goals

- **Automated truth-judging.** The agent never decides "this is the
  source"; it surfaces candidates with reasoning. Humans decide.
- **Cross-session collaboration.** Sessions are single-user for v1;
  no concurrent editing.
- **Real-time streaming UI.** Each step is a request/response.
  Long-running steps return a partial node and update on poll.
- **Migration story.** Schema is open by design; nothing to migrate.
- **Generic fact-checker over the open web.** Sources are within the
  configured corpus only.

## 3. Glossary

A **session** is one provenance investigation rooted at a chunk.

**Node kinds** (open string, but the v1 set is):

| Kind | Meaning | Example payload |
|---|---|---|
| `chunk` | A piece of source text the agent can reference | `{box_id, text, doc_slug, page}` |
| `claim` | A factual assertion extracted from a chunk | `{text, claim_type?, source_node_id}` |
| `task` | A verification question formulated to chase a claim | `{text, focus_claim_id}` |
| `search_result` | One candidate chunk surfaced by a search | `{box_id, text, score, doc_slug, searcher}` |
| `action_proposal` | LLM's suggested next move (recommended + alternatives + reasoning) | see §6 |
| `decision` | Human or LLM resolution of an action_proposal | `{accepted: "recommended"\|"alt_N"\|"override", reason?, override_text?}` |
| `evaluation` | LLM reasoning over candidates: "is this the source? why?" | `{verdict, confidence, reasoning, references: [node_ids]}` |
| `note` | Human-authored annotation attached to any node | `{text}` |
| `stop_proposal` | Agent thinks the trace is complete | `{reason}` |

**Edge kinds** (open string, v1):

| Kind | From → To | Meaning |
|---|---|---|
| `extracts-from` | claim → chunk | This claim was extracted from this chunk |
| `verifies` | task → claim | This task was formulated to verify this claim |
| `candidates-for` | search_result → task | This chunk was retrieved for this task |
| `proposes` | action_proposal → (claim \| task \| search_result) | The proposal applies to this anchor |
| `decided-by` | decision → action_proposal | The human/LLM resolution |
| `triggers` | decision → (any) | The next node spawned by this decision |
| `evaluates` | evaluation → search_result | LLM judgement of a candidate |
| `annotates` | note → (any) | Free-form attachment |
| `supersedes` | (any) → (any) | Re-run replaces a prior node; old retained for audit |

**Actor** is one of: `"human"`, `"llm:vllm"`, `"llm:azure"`,
`"llm:microsoft"`, `"system"`. Free-form so additional providers slot
in without enum churn.

## 4. Data model + storage

Two record types, both flat:

```python
class Node(BaseModel):
    node_id: str            # ulid
    session_id: str
    kind: str
    payload: dict[str, Any] # kind-specific; not validated at storage
    actor: str
    created_at: str         # iso utc

class Edge(BaseModel):
    edge_id: str
    session_id: str
    from_node: str
    to_node: str
    kind: str
    reason: str | None
    actor: str
    created_at: str
```

**Validation lives at the renderer + handler layers, not at storage.**
Adding a new node kind = ship one frontend renderer + one backend
handler. No schema migration.

**Persistence — event log per session:**

```
{LOCAL_PDF_DATA_ROOT}/{slug}/provenienz/{session_id}/
    events.jsonl       ← append-only; one event per line
    reasons.jsonl      ← override reasons (implicit guidance corpus)
    approaches.jsonl   ← named templates (explicit guidance library)
    meta.json          ← {root_chunk_id, status, created_at, last_touched_at}
```

`events.jsonl` carries three event types: `node_added`, `edge_added`,
`session_status_changed`. Reload = replay events into nodes+edges.
Branching = appending more events; nothing is ever deleted.

## 5. Searcher abstraction

Searchers find candidate chunks for a `task`. v1 ships **same-doc**;
the Protocol exists from day one so other backends slot in:

```python
class Searcher(Protocol):
    name: str   # "in_doc" / "cross_doc" / "azure"
    def search(self, query: str, *, top_k: int) -> list[SearchHit]: ...

@dataclass
class SearchHit:
    box_id: str
    text: str
    score: float
    doc_slug: str
    searcher: str   # which Searcher produced this hit
```

Planned implementations:

| Stage | Searcher | Backed by |
|---|---|---|
| **v1** | `InDocSearcher` | Hand-rolled BM25 from `local_pdf.comparison.bm25` over the active session's slug's `mineru.json` |
| **v2** | `CrossDocSearcher` | Same BM25 over every slug in `LOCAL_PDF_DATA_ROOT` |
| **v3** | `AzureSearcher` | Existing `query_index.search.hybrid_search` against the user's `kb-*` indexes |

A session has a list of active searchers (default: just `in_doc`).
The `/search` step round-robins or fan-outs (TBD per session config),
tagging each hit with its origin so the UI can colour-code them.

## 6. LLM-step pattern

Every step where the LLM makes a decision emits an
**action_proposal** node, NOT a final action. Schema:

```json
{
  "kind": "action_proposal",
  "payload": {
    "step_kind": "search" | "extract_claims" | "evaluate" | "propose_stop" | …,
    "anchor_node_id": "<the node this proposal acts on>",
    "recommended": {
      "label": "in_doc search 'Gesamtwärmeleistung 5.6 kW'",
      "args": { ... step-specific ... }
    },
    "alternatives": [
      { "label": "azure search same query", "args": { ... } },
      { "label": "ask human to identify the table", "args": { ... } }
    ],
    "reasoning": "claim mentions kW which usually points to a calculation; …",
    "guidance_consulted": [
      { "kind": "reason", "id": "reason#42", "summary": "user previously preferred …" },
      { "kind": "approach", "id": "approach#3", "name": "numerical-claim-v1" }
    ]
  }
}
```

Human resolves via a `decision` node:

| accepted | meaning |
|---|---|
| `"recommended"` | Run the recommended action |
| `"alt_N"` | Run alternative N |
| `"override"` | Don't run any of the proposals; do `override_text` instead, with `reason` |

Both the choice and the (optional) reason persist. Reasons feed
back into future ActionProposals — see §7.

The step routes (`/extract-claims`, `/search`, `/evaluate`, …) all
**produce** an `action_proposal` and DO NOT mutate further state.
A separate route (`/run-decision`) consumes a decision and spawns the
triggered child node.

## 7. Guidance mechanisms

Two mechanisms run side-by-side; per-step the user picks which to
consult.

### 7.1 Implicit — reason corpus

Every `decision` with `accepted="override"` plus a reason writes to
`reasons.jsonl`:

```json
{
  "reason_id": "ulid",
  "session_id": "ulid",
  "anchor_kind": "claim",
  "step_kind": "search",
  "rejected_label": "in_doc search 'Gesamtwärmeleistung'",
  "override_label": "search referenced table 'Wärmebilanz §3.2' first",
  "reason_text": "numerical claims usually live in calculation tables",
  "created_at": "..."
}
```

When the next ActionProposal is generated, the prompt loader filters
the reason corpus by `(anchor_kind, step_kind)` (and later by
`claim_type` once we have it), takes the most recent N, and inserts
them as in-context examples before the LLM call. Implicit because the
user never opts in — the system "learns" from past overrides
silently.

### 7.2 Explicit — approach library

A user can promote a recurring pattern to a named **Approach**:

```json
{
  "approach_id": "ulid",
  "name": "numerical-claim-v1",
  "step_kind": "search",
  "claim_kind_filter": "numerical",
  "instruction": "First search the chunk's referenced table. Fall back to literature only if no table.",
  "version": 1,
  "promoted_from_reasons": ["reason#42", "reason#71"],
  "created_at": "..."
}
```

Stored at `approaches.jsonl`, applied via per-session pinning:
`session.pinned_approaches: [approach_id]`. Pinned approaches are
embedded into the system-prompt for every relevant ActionProposal —
overrides the implicit corpus when both apply.

### 7.3 Determinism dial — the research goal

The two mechanisms are research instruments. We measure:

- How often does the LLM's recommendation already match the override?
- How often does the user accept-recommended (high agreement) vs
  override (low agreement)?
- Does explicit pinning shift agreement noticeably for the same
  cohort of claims?

Findings drive when (and whether) a step graduates from
"freedom + recommendation" to "scripted with LLM only at sub-decisions".

## 8. API surface

Session CRUD:

```
POST   /api/admin/provenienz/sessions                  body: {slug, root_chunk_id} → {session_id}
GET    /api/admin/provenienz/sessions                  → list (filtered by slug optionally)
GET    /api/admin/provenienz/sessions/{id}             → {meta, nodes[], edges[]}
DELETE /api/admin/provenienz/sessions/{id}             → 204 (rmtree the dir)
```

LLM steps (each produces an `action_proposal`):

```
POST   /api/admin/provenienz/sessions/{id}/extract-claims    body: {chunk_node_id, provider?}
POST   /api/admin/provenienz/sessions/{id}/formulate-task    body: {claim_node_id, provider?}
POST   /api/admin/provenienz/sessions/{id}/search            body: {task_node_id, searchers?[], provider?}
POST   /api/admin/provenienz/sessions/{id}/evaluate          body: {search_result_node_id, against_claim_id, provider?}
POST   /api/admin/provenienz/sessions/{id}/propose-stop      body: {anchor_node_id, provider?}
```

Decision execution (consumes an `action_proposal`, spawns child):

```
POST   /api/admin/provenienz/sessions/{id}/decide            body: {proposal_node_id, accepted, reason?, override?}
```

Generic node ops:

```
POST   /api/admin/provenienz/sessions/{id}/note              body: {target_node_id, text}
```

Approach library:

```
GET    /api/admin/provenienz/approaches                      ← list (across all sessions)
POST   /api/admin/provenienz/approaches                      body: see §7.2
POST   /api/admin/provenienz/sessions/{id}/pin-approach      body: {approach_id}
DELETE /api/admin/provenienz/sessions/{id}/pin-approach/{approach_id}
```

Reason corpus (read-only; written automatically by `/decide`):

```
GET    /api/admin/provenienz/reasons                         ← list (filterable by kind, step_kind)
```

## 9. Frontend layout

New tab `Provenienz` between **Vergleich** and the curator routes
(if any) — fits the doc-tab strip.

**Three-pane layout** matching the rest of the SPA:

```
┌── DocStepTabs ──────────────────────────────────────────────────────┐
├──────────────────────────┬───────────────────────┬─────────────────┤
│ Sessions list (300px)    │ React Flow canvas      │ Side panel      │
│  • Session A — chunk p7   │ (flex)                 │ (340px)         │
│    ┌─ chunk             │   chunk → claim → task   │                 │
│    │  status: in-progress│         ↓                │ Selected node:  │
│    │  3 claims found    │      action_proposal     │  - full payload │
│  • Session B — chunk p3   │         ↓                │  - actor + ts   │
│    closed                │      decision            │  - actions:     │
│                          │         ↓                │     extract     │
│  ➕ New session          │      search_result(s)    │     formulate   │
│    pick chunk in modal   │                          │     search      │
│                          │                          │     evaluate    │
│                          │                          │     note        │
│                          │                          │     pin appr.   │
└──────────────────────────┴───────────────────────┴─────────────────┘
```

**Canvas:** `react-flow` (declared as a runtime dep, lazy-imported).
Each node-kind has its own component under
`frontend/src/admin/provenienz/nodes/`:

```
nodes/
  ChunkNode.tsx        ← rounded rect, slug + box_id + first 80 chars
  ClaimNode.tsx        ← diamond, claim text wrapped to 4 lines
  TaskNode.tsx         ← orange card, "Aufgabe: …"
  SearchResultNode.tsx ← purple card, score + searcher name
  ActionProposalNode.tsx ← yellow card, recommended label + chevron to expand alternatives
  DecisionNode.tsx     ← green check / red x, reason inline
  EvaluationNode.tsx   ← blue card, verdict + confidence bar
  NoteNode.tsx         ← yellow sticky-note look
  StopProposalNode.tsx ← grey octagon
```

A central registry `nodeTypes` maps `kind` → component. New kinds
require adding one file + one registry entry.

**Side panel** is kind-aware: when a node is selected, it loads the
panel registered for that kind. Same registry pattern as nodes —
adding a kind = adding a panel component.

**Layouting:** auto-layout via `dagre` or `elk` on first render of a
session; persisted positions later (TBD).

## 10. Worked example — "Gesamtwärmeleistung 5.6 kW"

Starting state: user opens chunk `p3-b4` containing
*"Die Gesamtwärmeleistung der Baugruppe beträgt 5.6 kW."*

```
[chunk p3-b4]
     │ extracts-from
     ▼
[claim: "Gesamtwärmeleistung = 5.6 kW"]    actor: llm:vllm
     │ verifies
     ▼
[task: "Find the calculation or measurement that yields 5.6 kW"]
     │ proposes
     ▼
[action_proposal]
     recommended: in_doc BM25 search "Wärmebilanz Gesamtleistung"
     alternatives: [azure-search same query, manual table search]
     reasoning: "Numeric kW claims typically resolve to either a
                 calculation table or a measured-data section."
     guidance_consulted: [reason#42 "tables first for numerical claims"]
     │ decided-by
     ▼
[decision: accepted=recommended]   actor: human
     │ triggers
     ▼
[search_result p7-b1, score 0.78]
[search_result p9-b3, score 0.62]
     │ proposes
     ▼
[action_proposal]
     recommended: evaluate p7-b1 first (higher score, contains "Wärmebilanz")
     │ decided-by
     ▼
[decision: accepted=recommended]   actor: human
     │ triggers
     ▼
[evaluation: verdict="likely-source"
             confidence=0.82
             reasoning="p7-b1 is a Wärmebilanz table whose row sum
                        matches 5.6 kW within rounding."]
     │ proposes
     ▼
[stop_proposal]: source identified
     │ decided-by
     ▼
[decision: accepted=recommended]   actor: human  → session.status=closed
```

Every node + edge is in `events.jsonl`. The graph renders front-to-back
identically on reload. The user can branch at any decision by
explicitly creating a new edge from a prior `action_proposal` (e.g.
"actually let's also try the alternative") — old branch is preserved.

## 11. Open questions / deferred decisions

- **Cross-session learning.** Reasons are per-slug today. Should the
  guidance corpus be slug-scoped or global? Likely depends on
  whether claim taxonomies generalise across documents — defer until
  we have ≥3 sessions of data.
- **Persistent layout.** First-render is auto-layouted; if the user
  drags nodes, we don't yet save those positions. Defer until users
  ask.
- **Multi-LLM ensembling.** Could ask two providers for the same
  ActionProposal and surface the diff. Interesting but increases
  cost and decision surface. Defer.
- **Export.** Markdown + image export of the final graph for sharing.
  Defer until v2.
- **Multi-user.** Read-only sharing of a closed session is easy
  (graph is just JSONL). Concurrent editing is hard (event-log
  conflicts). Defer.
- **Tests.** Unit tests for the searcher protocol + decision
  reduction live in v1. End-to-end Playwright tests of the canvas
  defer to v2.
- **`react-flow` license.** Free for non-commercial; need to confirm
  before shipping. Alternative: `vis-network` or hand-rolled SVG.

## 12. Smallest viable v1 — concrete cut

Backend:
- `local_pdf.provenienz/` package: storage (event log), searchers
  (just `InDocSearcher`), llm-step handlers (`extract_claims`,
  `formulate_task`, `search`, `evaluate`, `propose_stop`),
  decision executor.
- Routes under `/api/admin/provenienz/…` per §8.
- vLLM-only as default provider; one per-step `provider?` field for
  later.

Frontend:
- New `Provenienz` tab + route.
- Three-pane layout, react-flow canvas, sessions list, kind-aware
  side panel.
- Five node renderers (chunk, claim, task, search_result,
  action_proposal, decision) + the corresponding side-panel
  variants. Evaluation + stop_proposal + note are post-v1 — easy
  to land later as separate node-kind PRs.

Out of v1 scope:
- Cross-doc and Azure searchers (just the Protocol exists).
- Approach library UI (the persistence path exists; no creation
  flow).
- Layout persistence.
- Multi-provider per-step swap UI (default vLLM only).

After v1, the agreement-rate research (§7.3) can begin: log every
decision with a `agreement` field (recommended/alt-N/override) and
compute the rate after each session.

---

## Sign-off questions for the user

1. Does the §10 worked example match how you actually want to think
   through a claim? Anything I'd add or remove?
2. Are five v1 node renderers (chunk / claim / task / search_result /
   action_proposal / decision) enough to feel useful, or does
   evaluation belong in v1 too?
3. `react-flow` — happy to use it, or should I check the alternatives
   first?
4. Spec ready to graduate to a step-by-step implementation plan?
