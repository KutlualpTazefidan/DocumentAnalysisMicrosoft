# Statistics-Tabs + Reviewer-Voting (Phase D) — Design

**Date**: 2026-06-03
**Status**: Approved for implementation
**Branch**: TBD (created at implementation start)

## Goal

Ship two related additions in one PR. (1) A new top-level **Statistik** tab
that gives operators a numerical lens on each document — extract diagnostics,
synthesise yield/acceptance, provenienz expert corrections, and a tenant-wide
Capability-Wünsche overview. (2) **Reviewer voting** on synthese questions
(Phase D), letting users register approval/disapproval per question with a
toggle UX, anti-anchoring count display, and a per-user state stripe — and
feeding that signal into the statistics tab as the "Vote-Approval Rate".

## Architecture overview

The Statistics tab is a thin read layer over data the system already
maintains: `mineru-out.json`/`segments.json` for extract diagnostics,
`datasets/events.jsonl` (goldens log) for synthese projections, the per-slug
session directory for provenienz expert corrections, and the existing
cross-session `list_capability_requests` aggregator for Wünsche. All four
endpoints are GETs in a new admin router; v1 is live-scan with no cache.
Reviewer voting reuses the existing JSONL append-only event store: votes are
`event_type="reviewed"` Events with `payload.action ∈ {approved, rejected,
revoked}`, last-event-per-(entry_id, actor.pseudonym) wins. The two features
intersect at metric #4 (vote-approval rate) and a per-question stacked-bar
chart in the Synthese stats sub-section.

## Tech stack

- **Frontend**: React 18.3, TypeScript 5.5, Tailwind 3.4, react-router-dom 6.26, @tanstack/react-query 5.51, framer-motion 11.18, lucide-react 0.477. New: **recharts 3.8.x** (`recharts` dep, latest stable).
- **Backend**: FastAPI, Pydantic v2, SQLite (auth.db only — events stay JSONL), goldens v1 event log via `goldens.storage.log.append_events/read_events` (fcntl.LOCK_EX cross-process locking).

## Decision Log

1. **Surface = D2 (top-level Statistik tab)**. Rationale: a sixth `DocStepTabs` entry mirrors the existing per-doc navigation and avoids fragmenting metrics across three other tabs. Capability-Wünsche stays embedded inside the Provenienz sub-section even though it is tenant-wide; the scope mismatch is acceptable for v1 and avoids a separate top-level "Operator Dashboard" page.
2. **Internal layout = 3 sub-sections (Extrahieren / Synthese / Provenienz)** matching the pipeline stages. Each renders its metrics as a small grid; the Provenienz sub-section embeds Capability-Wünsche as a tenant-wide widget.
3. **Compound cross-stage metric ("elements with synthese AND provenienz") = deferred to v1.1**. Single-stage metrics deliver enough operator value for v1; the cross-stage join requires a unified element-index that does not yet exist.
4. **Chart library = Recharts + custom navy theme wrapper**. Rationale: Recharts is React-idiomatic, ships TS types, is unstyled-by-default (so it cooperates with Tailwind), and has all primitives we need except true Sunburst. We wrap palette concerns in `<RechartsNavyTheme>` (a Context provider injecting the navy palette into chart components) so individual chart files stay declarative.
5. **Sunburst risk acknowledged**. Recharts 3.8 has no native `<Sunburst>` component. **Primary fallback: Recharts `<Treemap>`** rendering Capability-Wünsche as nested rectangles (Agent → Skill → Tool). Treemap is part of the Recharts dependency, no new packages. **Secondary fallback if Treemap nesting proves unfit**: nested concentric `<Pie>` rings (Recharts native — wrap two/three `<Pie>` components at different inner/outer radii). **Visx is NOT introduced** in v1 — see Risks for why.
6. **Other charts = lightweight polish**. Linear gradient fills (Recharts `<defs><linearGradient/></defs>` pattern), framer-motion `<motion.div>` mount transitions on chart containers, count-up animations on counter cards via framer-motion `animate` props on a `useMotionValue`.
7. **Data layer v1 = C1 live-scan**. No caching, no DuckDB. Reuse the existing aggregators (`list_capability_requests`, `iter_active_retrieval_entries`, `read_events`, `read_mineru`, `read_segments`).
8. **V2 escalation trigger (documented, not built)**: p95 aggregation latency > 500ms OR any `events.jsonl` > 50 MB. V2 strategy = read-only DuckDB layer querying JSONL directly via `read_json_auto`. This PR explicitly does not introduce DuckDB.
9. **fcntl.flock fix = separate PR**. The existing `append_events` calls fcntl.LOCK_EX per write; in NFS/macOS edge-cases this can no-op. Known tech-debt; tracked outside this PR.
10. **Vote schema = reuse `approved`/`rejected` + add `revoked`**. Rationale: the `Review.action` Literal already lists `approved` and `rejected` (currently unused at the API layer); adding `revoked` keeps the toggle UX honest (a user can un-vote) without inventing a new event_type. The `ReviewAction` alias gets the same extension.
11. **Vote storage = append-only Event**, `event_type="reviewed"`, `payload.actor = HumanActor`, `payload.action ∈ {approved, rejected, revoked}`, `payload.notes=null`. Last-event-per-(entry_id, actor.pseudonym) wins in aggregation. Crash-recovery and audit are free (same JSONL log as deprecate/refine).
12. **Toggle UX**: clicking the same vote a user already cast → append a `revoked` event for that user (their vote is removed). Clicking the opposite vote → append the new vote event; the previous one is superseded by last-event-wins. No client-side hide of the previous event.
13. **Weighting = unweighted MVP**. The `actor.level` field is captured on the event for forward-compatibility but is NOT used in v1 aggregation. Weighting math is out of scope.
14. **Aggregate display = counts only, anti-anchoring hidden until user voted**. Format `"N ✓ · M ✗"` rendered as a small inline element under the question card's footer toolbar. Hidden when `vote_summary.my_vote == null` to avoid biasing the reviewer.
15. **users.level migration = additive SQLite column** with default `'other'` and CHECK constraint matching the `HumanActor.level` Literal. New schema version `2`; existing rows get `'other'` retroactively.
16. **UI placement = footer-right of QuestionList card**, after the existing deprecate button. Icons `CheckCircle2` (einverstanden) + `XCircle` (disqualifizieren) from lucide-react. German tooltip labels.
17. **Per-user state badge = 3px left-border-stripe** on the question `<li>`. `emerald-500` on approved, `red-500` on rejected, none otherwise. Tailwind `border-l-[3px]` + dynamic color class.
18. **Vote endpoint = `POST /api/admin/docs/{slug}/questions/{question_id}/vote`** body `{ "action": "approved" | "rejected" | "revoked" }`. Returns the new Event. URL stem matches the existing `PATCH/DELETE /api/admin/docs/{slug}/questions/{question_id}` handlers in `synthesise.py:560,627`. Actor is hydrated from `request.state.identity` (the same path `_admin_actor` uses), with `level` read from the new `users.level` column.
19. **GET questions extended with `vote_summary`**: `{ approved_count: int, rejected_count: int, my_vote: "approved" | "rejected" | null }`. `my_vote` is the requesting user's latest non-revoked vote (null if revoked or never voted). Computed per request from the same event log.
20. **Stats integration**: Synthese stats sub-section gets metric #4 (vote-approval rate) ALONGSIDE #3 (curator survival) and a stacked-bar-per-question chart (`VoteDistributionBar`) sorted by controversy.

## Feature 1: Statistics-Tabs

### Surface

- **Tab**: 6th entry in `frontend/src/admin/components/DocStepTabs.tsx`. Label `Statistik`, icon `BarChart3` from lucide-react, href `(slug) => /admin/doc/${slug}/statistics`.
- **Route**: `/admin/doc/:slug/statistics`, registered in `frontend/src/App.tsx` (NOT `admin/App.tsx` — there is no such file) alongside the other `doc/:slug/*` routes.
- **Page file**: `frontend/src/admin/routes/Statistics.tsx`. Renders a shell with three `<section>` blocks: `Extrahieren`, `Synthese`, `Provenienz`. Each section pulls its data via its own react-query hook.
- **Provenienz section** embeds `<CapabilityWishesSunburst>` (tenant-wide) as a "Über alle Dokumente" card alongside the per-doc Expert-Correction-Rate gauge.

### Metric catalogue (v1)

| # | Stage | Metric | Source | Chart | Scope |
|---|-------|--------|--------|-------|-------|
| 1 | Extract | Diagnostic flag rate | `mineru-out.json` → `diagnostics[].kind` | Stacked bar (split / no-decomposition / clean) | per-doc |
| 2 | Extract | Register auto-detection rate | `segments.json` boxes where `kind ∈ {toc, list_of_tables, list_of_figures, bibliography}` divided by total boxes | Counter card with count-up | per-doc |
| 3 | Synthese | Curator survival rate | goldens events: `(created - deprecated) / created` over event log | Radial-bar gauge | per-doc |
| 4 | Synthese | Vote approval rate | aggregate `reviewed` events from Feature 2: `approved_count / (approved_count + rejected_count)`, where each `(entry_id, actor.pseudonym)` collapses to the latest non-`revoked` event | Radial-bar gauge | per-doc |
| 5 | Provenienz | Expert correction rate | session events: count Nodes with `kind ∈ {expert_step_override, expert_method_request}` divided by `plan_proposal` count | Radial-bar gauge | per-doc |
| 6 | Provenienz | Capability-Wünsche (tenant-wide) | `list_capability_requests` aggregator over ALL slugs | **Sunburst (Treemap fallback)** Agent → Skill → Tool | tenant-wide |

Edge cases: any divisor of 0 → return `{numerator: 0, denominator: 0, rate: null}`. The gauge component shows "–" for `rate=null`. Empty `vote_summary` (no votes yet) → metric #4 is `0/0`.

### Backend endpoints

New router file `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/statistics.py`. Pydantic response models defined in `features/pipelines/local-pdf/src/local_pdf/api/models/statistics.py`. All endpoints are tenant-aware via the same `_tr(request)` helper used by `synthesise.py` (calls `tenant_data_root(raw, tenant_slug_from_request(request))`).

```
GET /api/admin/statistics/extract/{slug}     → ExtractStats
GET /api/admin/statistics/synthese/{slug}    → SyntheseStats
GET /api/admin/statistics/provenienz/{slug}  → ProvenienzStats
GET /api/admin/statistics/capability-wishes  → CapabilityWishes (tenant-wide, no slug)
```

Response model shapes (also describe the TypeScript types — keep names identical):

```python
class DiagnosticCounts(BaseModel):
    split: int
    no_decomposition: int
    clean: int  # = (elements_total - split - no_decomposition)
    total: int

class ExtractStats(BaseModel):
    slug: str
    diagnostics: DiagnosticCounts
    register_boxes: int       # boxes with kind ∈ {toc, list_of_tables, ...}
    total_boxes: int
    register_rate: float | None  # register_boxes / total_boxes, None if total==0

class SyntheseStats(BaseModel):
    slug: str
    questions_created: int
    questions_deprecated: int
    survival_rate: float | None
    vote_approved: int
    vote_rejected: int
    vote_approval_rate: float | None
    vote_distribution: list[VoteDistributionRow]  # per-question stacked bar input

class VoteDistributionRow(BaseModel):
    entry_id: str
    text_short: str  # first 60 chars of the question
    approved: int
    rejected: int

class ProvenienzStats(BaseModel):
    slug: str
    plan_proposals: int
    expert_overrides: int     # expert_step_override + expert_method_request
    correction_rate: float | None

class CapabilityWish(BaseModel):
    name: str
    count: int
    by_actor: dict[str, int]   # {"human": n, "agent": m}
    # for the Sunburst: group "name" by a coarse Skill bucket (heuristic
    # below); Tool is the literal name. Agent ring is constant
    # "Provenienz-Agent" in v1 — see Risks.
    skill_bucket: str

class CapabilityWishes(BaseModel):
    wishes: list[CapabilityWish]
```

`skill_bucket` heuristic: starts with the leading word of `name` lowercased
(e.g. "RegisterLookup" → `register`, "FigureExtract" → `figure`); collapse
unknown buckets into `other`. v1 keeps this simple — a richer skill taxonomy
lands when the Provenienz tool registry exposes one.

The `synthese` endpoint reads the same goldens log path that
`synthesise.py::_events_path` uses (`{data_root}/{slug}/datasets/{GOLDEN_EVENTS_V1_FILENAME}`),
calls `read_events(path)`, then:

- `questions_created` = count of events where `event_type == "created"` AND `payload.entry_data.task_type == "retrieval"`.
- `questions_deprecated` = count of events where `event_type == "deprecated"`.
- For votes: walk events with `event_type == "reviewed"` AND `payload.action ∈ {"approved", "rejected", "revoked"}`. Group by `(entry_id, payload.actor.pseudonym)`, keep last by `timestamp_utc`. Count `approved` and `rejected` over the latest-per-pair set.
- `vote_distribution`: per `entry_id`, count of latest-per-(entry,user) votes. Sorted by `min(approved, rejected)` descending (most controversial first). Limit to top 20 to keep the chart legible.

`text_short` is read by also calling `iter_active_retrieval_entries` (already in scope) and matching `entry_id` to its `query`; truncated to 60 chars with no trailing whitespace.

`provenienz` endpoint walks `{data_root}/{slug}/provenienz/*/`, calls
`read_session(sd)` per session directory, and counts Nodes by kind.

`capability-wishes` endpoint reuses the existing aggregator — it imports
`list_capability_requests` from `provenienz.py` and post-processes its output
into `CapabilityWishes` (computes `skill_bucket`). It does NOT re-walk the
session tree.

Router registration: import `statistics_router` in
`local_pdf/api/app.py` and `app.include_router(statistics_router)` in the
same block as the other admin routers.

### Frontend components and hooks

```
frontend/src/admin/
├── routes/
│   └── Statistics.tsx                 # NEW — page shell, 3 sections
├── hooks/
│   └── useStatistics.ts               # NEW — useQuery hooks per endpoint
└── components/charts/
    ├── RechartsNavyTheme.tsx          # NEW — context + ResponsiveContainer wrapper
    ├── MetricGauge.tsx                # NEW — radial-bar wrapper
    ├── MetricCounter.tsx              # NEW — count-up card via framer-motion
    ├── DiagnosticBar.tsx              # NEW — stacked bar for #1
    ├── CapabilityWishesSunburst.tsx   # NEW — Treemap (primary) / nested Pie (fallback)
    └── VoteDistributionBar.tsx        # NEW — per-question stacked bar for #4 distribution
```

TypeScript response types live next to the hooks (`useStatistics.ts`) and use
field names IDENTICAL to the Pydantic models so the keys map 1:1 (no
camelCase rename — matches the existing `useSynthesise.ts` style of
`entry_id`/`box_id`).

`RechartsNavyTheme`:
- Context exposes `{ palette: { bg: "#1e293b", text: "#cbd5e1", accent: "#3b82f6", success: "#10b981", danger: "#ef4444", grid: "#475569" } }` (existing project navy/brand classes).
- Renders a `<ResponsiveContainer>` + children; child charts read palette via `useContext` and apply colors to `<XAxis stroke=…/>`, `<Tooltip contentStyle=…/>`, etc.

`MetricGauge` (`<RadialBarChart>`):
- Props: `value: number | null` (0..1), `label: string`, `subtitle?: string`.
- Renders a single `<RadialBar>` with `dataKey="value"` and `value` scaled to 0..100. Track is `palette.grid`, fill is `palette.success` if `value >= 0.7`, `palette.accent` if `>= 0.4`, `palette.danger` otherwise.
- `value === null` → text "–" centered, no bar.

`MetricCounter`:
- Props: `value: number`, `label: string`, `suffix?: string`.
- framer-motion `useMotionValue(0)` with `animate(motionValue, value, { duration: 0.8 })` on mount/value-change.

`DiagnosticBar` (Recharts `<BarChart>`, stacked):
- Single bar (one document = one row) with three stacks: `split` (yellow), `no_decomposition` (red), `clean` (emerald). Tooltip shows the absolute counts.

`CapabilityWishesSunburst`:
- Primary impl: Recharts `<Treemap>` with `data = nested {name: bucket, children: [{name: tool, size: count}]}`. Click on a tile drills into examples via a side panel reused from the existing Provenienz capability-wishes UI.
- Fallback impl (commented in the file, switchable via a const): nested concentric `<Pie>` rings — outer ring = `skill_bucket`, inner ring = tool names. Use the recharts pattern `<PieChart>{<Pie data outerRadius={120}/>, <Pie data outerRadius={80}/>}</PieChart>`.

`VoteDistributionBar`:
- Recharts `<BarChart>` with `layout="vertical"`, `data = vote_distribution` rows. Two stacks per bar: `approved` (emerald) + `rejected` (red). `YAxis` labels `text_short`.

Hooks (matching `useSynthesise.ts` patterns):

```ts
export interface ExtractStats {
  slug: string;
  diagnostics: { split: number; no_decomposition: number; clean: number; total: number };
  register_boxes: number;
  total_boxes: number;
  register_rate: number | null;
}

export function useExtractStats(slug: string, token: string) {
  return useQuery<ExtractStats>({
    queryKey: ["stats", "extract", slug],
    queryFn: async () => {
      const r = await fetchOk(
        `${apiBase()}/api/admin/statistics/extract/${encodeURIComponent(slug)}`,
        { method: "GET" },
        token,
      );
      return r.json();
    },
  });
}
// useSyntheseStats, useProvenienzStats, useCapabilityWishes — analogous.
```

`fetchOk` lives in `useSynthesise.ts`; extract it once into a shared helper
in a small refactor task OR re-declare a copy in `useStatistics.ts`. The
plan picks the local-copy path to keep this PR's blast radius down (note
this as future-tech-debt).

### Data layer v1

All four endpoints scan from disk on every request. Live-scan only. No
caching layer. The aggregator functions live behind small private helpers
in `statistics.py` so a future v2 (DuckDB) can swap implementations without
changing the router signature.

### V2 escalation trigger

Document in this spec; do NOT build:

- **Trigger A**: p95 endpoint latency > 500ms (measured via the existing
  uvicorn access log).
- **Trigger B**: any `events.jsonl` file exceeds 50 MB.
- **V2 strategy**: introduce a read-only DuckDB layer that reads JSONL via
  `read_json_auto('{path}', format='newline_delimited')`. Migration is
  one-way (the JSONL stays the source of truth); DuckDB is a query cache.

## Feature 2: Reviewer-Voting Phase D

### Schema changes

`features/goldens/src/goldens/schemas/base.py`:

- Line ~124: extend `ReviewAction` from
  `Literal["accepted_unchanged", "approved", "rejected"]`
  to
  `Literal["accepted_unchanged", "approved", "rejected", "revoked"]`.
- Lines ~142–150: extend the `Review.action` inline Literal by appending `"revoked"` after `"rejected"`. Keep existing entries in the same order — order matters because some downstream `if action == X` chains test by string.
- Line ~127–135: extend `_REVIEW_ACTIONS` tuple with `"revoked"` (between `"rejected"` and `"deprecated"`).

No new field, no new Event subtype — re-use the existing `Event(event_type="reviewed", payload={...})` envelope.

### Storage

Append-only via existing `goldens.storage.log.append_events`. Vote event shape:

```python
Event(
    event_id=new_event_id(),
    timestamp_utc=now_utc_iso(),
    event_type="reviewed",
    entry_id=question_entry_id,
    schema_version=1,
    payload={
        "action": "approved",  # or "rejected" or "revoked"
        "actor": human_actor.model_dump(mode="json"),
        "notes": None,
    },
)
```

`HumanActor` carries `pseudonym` + `level`. `level` is read from the
`users.level` SQLite column (new — see Migration).

Aggregation rule: for each `(entry_id, actor.pseudonym)` pair, take the
event with the largest `timestamp_utc` (stable sort secondary key = event
file order). If that event's action is `revoked`, the vote is excluded
from counts. Otherwise it contributes 1 to `approved` or `rejected`.

### users.level migration

`features/pipelines/local-pdf/src/local_pdf/auth/db.py`:

- Bump `_SCHEMA_VERSION` from `1` to `2`.
- Add `_migrate_to_v2(conn)` that runs `ALTER TABLE users ADD COLUMN level TEXT NOT NULL DEFAULT 'other' CHECK (level IN ('expert','phd','masters','bachelors','other'))`.
- In `ensure_schema`, after the `current < 1` block, add `if current < 2: _migrate_to_v2(conn)`.
- `User` dataclass in `auth/users.py` gains a `level: Literal["expert","phd","masters","bachelors","other"]` field.
- `_row_to_user` reads `row["level"]`.
- `create_user` accepts a `level` kwarg with default `"other"` and writes it.

**Migration safety**: ALTER TABLE ADD COLUMN with `NOT NULL DEFAULT 'other'`
is additive in SQLite; existing rows get `'other'` retroactively at the
statement-level, no row rewrite required. Constraint-check is enforced for
new INSERTs only (SQLite limitation, acceptable here — existing rows are
trivially valid against the default).

### API

`features/pipelines/local-pdf/src/local_pdf/api/routers/admin/synthesise.py`:

1. **Extend GET `/api/admin/docs/{slug}/questions`** response to include
   `vote_summary` per question. Walk the events log once, build the
   `(entry_id, pseudonym) → latest action` map, then attach
   `{approved_count, rejected_count, my_vote}` to each `GeneratedQuestion`.
   `my_vote` is the requesting user's latest non-`revoked` vote OR null.
   The requesting user's pseudonym is read from `request.state.identity`
   (same path as `_admin_actor`).

2. **New POST `/api/admin/docs/{slug}/questions/{question_id}/vote`**.
   Body: `{"action": "approved" | "rejected" | "revoked"}`. Builds a
   `HumanActor` via a new helper `_admin_actor_with_level(request)` that
   reads `users.level` for the current pseudonym, defaulting to `"other"`
   if the SELECT misses. Appends a single Event via `append_events`.
   Returns the new Event as JSON.

URL stem matches the existing `PATCH/DELETE /api/admin/docs/{slug}/questions/{question_id}` handlers (synthesise.py:560, 627). The URL parameter is `question_id`; internally it is the goldens `entry_id`.

Auth: identical surface to the existing PATCH/DELETE — the admin auth
middleware already populates `request.state.identity`.

### UI

`frontend/src/admin/components/QuestionList.tsx`:

- Import `CheckCircle2`, `XCircle` from `lucide-react`.
- Extend the `Question` interface (in `useSynthesise.ts`) with
  `vote_summary?: { approved_count: number; rejected_count: number; my_vote: "approved" | "rejected" | null }`. Optional only to keep the type backward-compat for callers that might not pass it.
- Add two buttons to the existing footer-toolbar `<div className="flex gap-1 justify-end">` after the trash button:
  - Approve: title="Einverstanden", click handler `onVote(q.entry_id, "approved")`.
  - Reject: title="Disqualifizieren", click handler `onVote(q.entry_id, "rejected")`.
  - When `q.vote_summary?.my_vote === "approved"`, the approve button gets `text-emerald-600 bg-emerald-50` styling; clicking it again calls `onVote(q.entry_id, "revoked")` (toggle-off).
  - Mirror logic for the reject button (red).
- Add `onVote` to the `Props` interface: `onVote: (entryId: string, action: "approved"|"rejected"|"revoked") => Promise<void> | void`.
- Per-user state stripe: wrap the existing `<li>` className with `border-l-[3px]` and a dynamic color:
  - `border-l-emerald-500` if `q.vote_summary?.my_vote === "approved"`
  - `border-l-red-500` if `q.vote_summary?.my_vote === "rejected"`
  - `border-l-transparent` otherwise
- Anti-anchoring vote count display: render a small `<span className="text-[11px] text-slate-500">{N} ✓ · {M} ✗</span>` inside the footer toolbar **only when** `q.vote_summary?.my_vote != null`. When `my_vote` is null, the counts are hidden.

`frontend/src/admin/hooks/useSynthesise.ts`:

- Extend the `Question` interface with the optional `vote_summary` field above.
- Add `useVoteQuestion(slug, token)` mutation hook matching the refine/deprecate pattern. Invalidates `["questions", slug]` AND `["stats", "synthese", slug]` on success.

### Stats integration

The Synthese sub-section of the Statistics page renders:

- Two side-by-side `MetricGauge`s: "Curator-Überleben" (metric #3) and "Reviewer-Zustimmung" (metric #4).
- Below them, `VoteDistributionBar` rendering top-20 controversial questions (vote_distribution from the endpoint).
- When `vote_approval_rate === null` (no votes yet), the gauge shows "–" and the bar chart shows an empty-state hint "Noch keine Reviewer-Stimmen vorhanden."

## Out of scope

- Compound cross-stage metric ("elements with synthese AND provenienz") — deferred to v1.1.
- DuckDB query layer — deferred to v2; only ships when a trigger fires.
- `fcntl.flock` correctness fix on non-POSIX filesystems — separate PR.
- Level-weighted vote aggregation — deferred; `level` is stored but unused.
- Vote-history audit UI (list of who voted what when) — out of scope; the JSONL serves as audit, no UI surfacing in v1.
- Per-tenant Capability-Wünsche scope — v1 Capability-Wünsche is rendered tenant-wide as a single widget; per-doc filtering deferred.

## Risks and mitigations

- **Recharts Sunburst absence (decision 5)**. Primary mitigation is the Treemap fallback; secondary is nested Pie rings. The plan task that builds `CapabilityWishesSunburst.tsx` includes a **verification step** that boots the dev server and checks the Treemap rendering visually. Visx is NOT introduced because it would double the chart-library surface and Treemap already produces a defensible Agent → Skill → Tool hierarchy.
- **Agent ring is constant in v1**. Because Provenienz today emits capability_requests from a single agent ("Provenienz-Agent"), the outermost ring is degenerate. Documented as expected; the Treemap collapses it visually and the data shape is forward-compatible with a future multi-agent topology.
- **Live-scan latency**. Decision 8 sets the trigger; until then, response times for `/api/admin/statistics/*` will scale linearly with `events.jsonl` length. v1 is acceptable because the largest log in repo today is < 100 KB.
- **users.level default of 'other' is a v1 placeholder**. Per the project-pseudonym-provisional rule, this is acceptable. A future Phase E admin UI for editing levels will replace the all-other default; weighting math waits on it.
- **Anti-anchoring hide-counts UX**. Risk: a reviewer might forget the counts exist; mitigation = stripe + counts together signal "you have already voted" and the counts implicitly show "and here is the running tally". Counts stay hidden for first-vote experience.
- **Vote-event flood on toggle-spam**. A reviewer flipping back and forth produces multiple events. Acceptable: JSONL is append-only, last-event-wins drops them at projection time. Stats endpoints already do last-event collapse.
- **Schema-version 2 backward compat**. After the migration runs once, downgrading to v1 server code reads `users.level` as a spurious column; SQLite tolerates the extra column on `SELECT *`. No deployment-rollback risk noted.
