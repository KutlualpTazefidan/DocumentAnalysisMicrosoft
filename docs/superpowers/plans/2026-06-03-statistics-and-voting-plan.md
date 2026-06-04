# Statistics + Voting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Statistics-Tabs + Phase-D Reviewer-Voting in one PR.

**Architecture:** Statistics-Tabs is a new top-level `Statistik` `DocStepTabs` entry with 3 sub-sections (Extrahieren / Synthese / Provenienz), each pulling from a thin GET endpoint that live-scans existing JSONL + sidecar data via Recharts charts wrapped in a navy theme. Reviewer-Voting reuses the goldens append-only event log: votes are `event_type="reviewed"` Events with `payload.action ∈ {approved, rejected, revoked}`, surfaced via a toggle UX in `QuestionList` and aggregated into Synthese stats metric #4.

**Tech Stack:** React 18.3 + TS 5.5 + Tailwind 3.4 + Recharts 3.8 + framer-motion 11.18 + lucide-react 0.477 (frontend); FastAPI + Pydantic v2 + SQLite + JSONL (backend).

**Reference spec:** `docs/superpowers/specs/2026-06-03-statistics-and-voting-design.md`

---

## Task 1: Install Recharts + create RechartsNavyTheme wrapper

**Files**:
- Modify: `frontend/package.json`
- Create: `frontend/src/admin/components/charts/RechartsNavyTheme.tsx`
- Create: `frontend/src/admin/components/charts/__tests__/RechartsNavyTheme.test.tsx`

**Steps**:

1. Install Recharts.
   ```bash
   cd frontend && npm install recharts@^3.8.0
   ```
   Expected: `package.json` and `package-lock.json` updated; `node_modules/recharts` present.

2. Verify Recharts exports for sunburst (locks in the Treemap fallback).
   ```bash
   cd frontend && node -e "const r=require('recharts'); console.log(['Sunburst','Treemap','Pie','RadialBar','BarChart'].map(k=>[k,typeof r[k]]))"
   ```
   Expected: `Sunburst` is `undefined`, `Treemap`, `Pie`, `RadialBar`, `BarChart` are all `'function'`. Document the result inline in step 3's comment.

3. Create the theme wrapper.
   ```tsx
   // frontend/src/admin/components/charts/RechartsNavyTheme.tsx
   //
   // Recharts is unstyled by default. This wrapper provides a Context
   // with the navy palette so chart components stay declarative.
   //
   // Verified 2026-06-03 (recharts 3.8.x): Sunburst is NOT exported.
   // CapabilityWishesSunburst falls back to <Treemap>; see Task 5.
   import { createContext, useContext, type ReactNode } from "react";
   import { ResponsiveContainer } from "recharts";

   export interface NavyPalette {
     bg: string;
     text: string;
     accent: string;
     success: string;
     danger: string;
     warn: string;
     grid: string;
     gradientStops: { from: string; to: string };
   }

   export const DEFAULT_NAVY_PALETTE: NavyPalette = {
     bg: "#1e293b",        // navy-800
     text: "#cbd5e1",      // navy-200
     accent: "#3b82f6",    // brand-500
     success: "#10b981",   // emerald-500
     danger: "#ef4444",    // red-500
     warn: "#f59e0b",      // amber-500
     grid: "#475569",      // navy-600
     gradientStops: { from: "#3b82f6", to: "#1d4ed8" },
   };

   const PaletteCtx = createContext<NavyPalette>(DEFAULT_NAVY_PALETTE);

   export function useChartPalette(): NavyPalette {
     return useContext(PaletteCtx);
   }

   interface Props {
     children: ReactNode;
     height?: number;
     palette?: NavyPalette;
   }

   /** Wraps a chart in a ResponsiveContainer + navy palette context. */
   export function RechartsNavyTheme({ children, height = 240, palette = DEFAULT_NAVY_PALETTE }: Props): JSX.Element {
     return (
       <PaletteCtx.Provider value={palette}>
         <div className="rounded bg-navy-800 p-3">
           <ResponsiveContainer width="100%" height={height}>
             {children as any}
           </ResponsiveContainer>
         </div>
       </PaletteCtx.Provider>
     );
   }
   ```

4. Test the wrapper renders without crashing.
   ```tsx
   // frontend/src/admin/components/charts/__tests__/RechartsNavyTheme.test.tsx
   import { render } from "@testing-library/react";
   import { describe, expect, it } from "vitest";
   import { BarChart, Bar } from "recharts";
   import { RechartsNavyTheme, useChartPalette, DEFAULT_NAVY_PALETTE } from "../RechartsNavyTheme";

   describe("RechartsNavyTheme", () => {
     it("renders children inside a ResponsiveContainer", () => {
       const { container } = render(
         <RechartsNavyTheme height={200}>
           <BarChart data={[{ x: 1, y: 2 }]}>
             <Bar dataKey="y" />
           </BarChart>
         </RechartsNavyTheme>
       );
       expect(container.querySelector(".recharts-responsive-container")).not.toBeNull();
     });

     it("exposes the palette via useChartPalette", () => {
       function Probe(): JSX.Element {
         const p = useChartPalette();
         return <span data-testid="bg">{p.bg}</span>;
       }
       const { getByTestId } = render(
         <RechartsNavyTheme>
           <Probe />
         </RechartsNavyTheme>
       );
       expect(getByTestId("bg").textContent).toBe(DEFAULT_NAVY_PALETTE.bg);
     });
   });
   ```

5. Run the test.
   ```bash
   cd frontend && npm run test -- RechartsNavyTheme
   ```
   Expected: 2 passing tests.

6. Commit.
   ```bash
   git add frontend/package.json frontend/package-lock.json frontend/src/admin/components/charts/RechartsNavyTheme.tsx frontend/src/admin/components/charts/__tests__/RechartsNavyTheme.test.tsx
   git commit -m "feat(stats): add recharts dependency and navy theme wrapper"
   ```

---

## Task 2: Statistics backend — Pydantic models

**Files**:
- Create: `features/pipelines/local-pdf/src/local_pdf/api/models/__init__.py` (if absent)
- Create: `features/pipelines/local-pdf/src/local_pdf/api/models/statistics.py`
- Create: `features/pipelines/local-pdf/tests/api/test_statistics_models.py`

**Steps**:

1. Check whether the models package already exists.
   ```bash
   ls features/pipelines/local-pdf/src/local_pdf/api/models/ 2>/dev/null || echo "absent — create __init__.py too"
   ```

2. Create the models package init if needed.
   ```python
   # features/pipelines/local-pdf/src/local_pdf/api/models/__init__.py
   ```
   (Empty file is fine — Pydantic models import explicitly.)

3. Define the models.
   ```python
   # features/pipelines/local-pdf/src/local_pdf/api/models/statistics.py
   """Pydantic response models for /api/admin/statistics/*.

   Field names mirror the TypeScript shapes in
   ``frontend/src/admin/hooks/useStatistics.ts`` 1:1 (no camelCase
   rename — matches the existing /questions endpoint style).
   """
   from __future__ import annotations

   from pydantic import BaseModel


   class DiagnosticCounts(BaseModel):
       split: int
       no_decomposition: int
       clean: int
       total: int


   class ExtractStats(BaseModel):
       slug: str
       diagnostics: DiagnosticCounts
       register_boxes: int
       total_boxes: int
       register_rate: float | None


   class VoteDistributionRow(BaseModel):
       entry_id: str
       text_short: str
       approved: int
       rejected: int


   class SyntheseStats(BaseModel):
       slug: str
       questions_created: int
       questions_deprecated: int
       survival_rate: float | None
       vote_approved: int
       vote_rejected: int
       vote_approval_rate: float | None
       vote_distribution: list[VoteDistributionRow]


   class ProvenienzStats(BaseModel):
       slug: str
       plan_proposals: int
       expert_overrides: int
       correction_rate: float | None


   class CapabilityWish(BaseModel):
       name: str
       count: int
       by_actor: dict[str, int]
       skill_bucket: str


   class CapabilityWishes(BaseModel):
       wishes: list[CapabilityWish]
   ```

4. Smoke-test the models construct cleanly.
   ```python
   # features/pipelines/local-pdf/tests/api/test_statistics_models.py
   from local_pdf.api.models.statistics import (
       CapabilityWish,
       CapabilityWishes,
       DiagnosticCounts,
       ExtractStats,
       ProvenienzStats,
       SyntheseStats,
       VoteDistributionRow,
   )


   def test_extract_stats_round_trip():
       m = ExtractStats(
           slug="doc-a",
           diagnostics=DiagnosticCounts(split=1, no_decomposition=0, clean=10, total=11),
           register_boxes=2,
           total_boxes=20,
           register_rate=0.1,
       )
       assert m.model_dump()["register_rate"] == 0.1


   def test_synthese_stats_allows_null_rates():
       m = SyntheseStats(
           slug="doc-a",
           questions_created=0,
           questions_deprecated=0,
           survival_rate=None,
           vote_approved=0,
           vote_rejected=0,
           vote_approval_rate=None,
           vote_distribution=[],
       )
       assert m.survival_rate is None
       assert m.vote_distribution == []


   def test_capability_wishes_carries_actor_split():
       w = CapabilityWishes(
           wishes=[
               CapabilityWish(
                   name="RegisterLookup",
                   count=5,
                   by_actor={"human": 1, "agent": 4},
                   skill_bucket="register",
               )
           ]
       )
       assert w.wishes[0].by_actor == {"human": 1, "agent": 4}


   def test_provenienz_stats_zero_proposals_is_null_rate():
       m = ProvenienzStats(
           slug="doc-a",
           plan_proposals=0,
           expert_overrides=0,
           correction_rate=None,
       )
       assert m.correction_rate is None


   def test_vote_distribution_row():
       r = VoteDistributionRow(entry_id="q1", text_short="Was ist der Registersatz?", approved=3, rejected=1)
       assert r.approved == 3
   ```

5. Run the tests.
   ```bash
   cd features/pipelines/local-pdf && uv run pytest tests/api/test_statistics_models.py -v
   ```
   Expected: 5 passing.

6. Commit.
   ```bash
   git add features/pipelines/local-pdf/src/local_pdf/api/models/__init__.py features/pipelines/local-pdf/src/local_pdf/api/models/statistics.py features/pipelines/local-pdf/tests/api/test_statistics_models.py
   git commit -m "feat(stats): pydantic response models for statistics endpoints"
   ```

---

## Task 3: Statistics backend — extract endpoint

**Files**:
- Create: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/statistics.py`
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/app.py` (register router)
- Create: `features/pipelines/local-pdf/tests/api/admin/test_statistics_extract.py`

**Steps**:

1. Write the failing test first.
   ```python
   # features/pipelines/local-pdf/tests/api/admin/test_statistics_extract.py
   import json
   from pathlib import Path

   import pytest
   from fastapi.testclient import TestClient
   from local_pdf.api.app import create_app


   @pytest.fixture
   def app_client(tmp_path: Path):
       slug = "doc-a"
       doc = tmp_path / slug
       doc.mkdir()
       # mineru-out.json with two diagnostics
       (doc / "mineru-out.json").write_text(
           json.dumps({
               "elements": [{"id": f"e{i}"} for i in range(10)],
               "diagnostics": [
                   {"kind": "split"},
                   {"kind": "no_decomposition"},
               ],
           })
       )
       # segments.json with 5 boxes, 2 are register-type
       (doc / "segments.json").write_text(
           json.dumps({
               "boxes": [
                   {"box_id": "b1", "kind": "toc"},
                   {"box_id": "b2", "kind": "paragraph"},
                   {"box_id": "b3", "kind": "list_of_tables"},
                   {"box_id": "b4", "kind": "paragraph"},
                   {"box_id": "b5", "kind": "paragraph"},
               ]
           })
       )
       app = create_app(data_root=tmp_path)
       return TestClient(app), slug


   def test_extract_stats_counts_diagnostics_and_register(app_client):
       client, slug = app_client
       r = client.get(f"/api/admin/statistics/extract/{slug}")
       assert r.status_code == 200
       body = r.json()
       assert body["slug"] == slug
       assert body["diagnostics"] == {
           "split": 1,
           "no_decomposition": 1,
           "clean": 8,
           "total": 10,
       }
       assert body["register_boxes"] == 2
       assert body["total_boxes"] == 5
       assert body["register_rate"] == pytest.approx(0.4)


   def test_extract_stats_zero_boxes_returns_null_rate(tmp_path: Path):
       slug = "empty"
       (tmp_path / slug).mkdir()
       (tmp_path / slug / "mineru-out.json").write_text(json.dumps({"elements": [], "diagnostics": []}))
       (tmp_path / slug / "segments.json").write_text(json.dumps({"boxes": []}))
       client = TestClient(create_app(data_root=tmp_path))
       r = client.get(f"/api/admin/statistics/extract/{slug}")
       assert r.status_code == 200
       assert r.json()["register_rate"] is None


   def test_extract_stats_404_when_doc_missing(tmp_path: Path):
       client = TestClient(create_app(data_root=tmp_path))
       r = client.get("/api/admin/statistics/extract/nonexistent")
       assert r.status_code == 404
   ```

2. Run the test — expect failure (no router yet).
   ```bash
   cd features/pipelines/local-pdf && uv run pytest tests/api/admin/test_statistics_extract.py -v
   ```
   Expected: 3 failures with 404 or import errors.

3. Implement the router stub + extract handler.
   ```python
   # features/pipelines/local-pdf/src/local_pdf/api/routers/admin/statistics.py
   """Statistics — read-only aggregators powering the Statistik tab.

   v1 is C1 live-scan: every request walks the on-disk artifacts. See
   docs/superpowers/specs/2026-06-03-statistics-and-voting-design.md
   for the V2 (DuckDB) trigger.
   """
   from __future__ import annotations

   from pathlib import Path

   from fastapi import APIRouter, HTTPException, Request

   from local_pdf.api.models.statistics import (
       DiagnosticCounts,
       ExtractStats,
   )
   from local_pdf.auth.tenant_root import tenant_data_root, tenant_slug_from_request
   from local_pdf.storage.sidecar import doc_dir, read_mineru, read_segments

   router = APIRouter()

   _REGISTER_KINDS = {"toc", "list_of_tables", "list_of_figures", "bibliography"}


   def _tr(request: Request) -> Path:
       raw = request.app.state.config.data_root
       return tenant_data_root(raw, tenant_slug_from_request(request))


   def _count_diagnostics(mineru: dict | None) -> DiagnosticCounts:
       diags = (mineru or {}).get("diagnostics") or []
       elements = (mineru or {}).get("elements") or []
       split = sum(1 for d in diags if d.get("kind") == "split")
       nodecomp = sum(1 for d in diags if d.get("kind") == "no_decomposition")
       total = len(elements)
       clean = max(total - split - nodecomp, 0)
       return DiagnosticCounts(split=split, no_decomposition=nodecomp, clean=clean, total=total)


   def _count_register_boxes(segments: dict | None) -> tuple[int, int]:
       boxes = (segments or {}).get("boxes") or []
       total = len(boxes)
       reg = sum(1 for b in boxes if b.get("kind") in _REGISTER_KINDS)
       return reg, total


   @router.get("/api/admin/statistics/extract/{slug}", response_model=ExtractStats)
   async def extract_stats(slug: str, request: Request) -> ExtractStats:
       data_root = _tr(request)
       if not doc_dir(data_root, slug).exists():
           raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
       mineru = read_mineru(data_root, slug)
       segments_file = read_segments(data_root, slug)
       segments_dict = segments_file.model_dump() if segments_file is not None else None
       reg, total_boxes = _count_register_boxes(segments_dict)
       diag = _count_diagnostics(mineru)
       rate = (reg / total_boxes) if total_boxes > 0 else None
       return ExtractStats(
           slug=slug,
           diagnostics=diag,
           register_boxes=reg,
           total_boxes=total_boxes,
           register_rate=rate,
       )
   ```

4. Register the router in `app.py`.
   ```python
   # features/pipelines/local-pdf/src/local_pdf/api/app.py — add to imports near other admin routers
   from local_pdf.api.routers.admin.statistics import router as statistics_router
   # ...and in the include_router block (after provenienz_router for proximity):
   app.include_router(statistics_router)
   ```

5. Re-run the test.
   ```bash
   cd features/pipelines/local-pdf && uv run pytest tests/api/admin/test_statistics_extract.py -v
   ```
   Expected: 3 passing.

6. Commit.
   ```bash
   git add features/pipelines/local-pdf/src/local_pdf/api/routers/admin/statistics.py features/pipelines/local-pdf/src/local_pdf/api/app.py features/pipelines/local-pdf/tests/api/admin/test_statistics_extract.py
   git commit -m "feat(stats): extract-stats endpoint with diagnostic + register counts"
   ```

---

## Task 4: Statistics backend — synthese endpoint (sans votes for now)

**Files**:
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/statistics.py`
- Create: `features/pipelines/local-pdf/tests/api/admin/test_statistics_synthese.py`

**Steps**:

1. Write the test exercising the curator-survival half (votes come in Task 11 once schema lands).
   ```python
   # features/pipelines/local-pdf/tests/api/admin/test_statistics_synthese.py
   from pathlib import Path

   import pytest
   from fastapi.testclient import TestClient
   from goldens.operations._time import now_utc_iso
   from goldens.schemas.base import Event, HumanActor
   from goldens.storage import GOLDEN_EVENTS_V1_FILENAME
   from goldens.storage.ids import new_entry_id, new_event_id
   from goldens.storage.log import append_event
   from local_pdf.api.app import create_app


   @pytest.fixture
   def populated_root(tmp_path: Path):
       slug = "doc-a"
       (tmp_path / slug).mkdir()
       (tmp_path / slug / "datasets").mkdir()
       (tmp_path / slug / "mineru-out.json").write_text('{"elements": [], "diagnostics": []}')
       events_path = tmp_path / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
       actor = HumanActor(pseudonym="reviewer-x", level="other")
       for _ in range(5):
           append_event(events_path, Event(
               event_id=new_event_id(),
               timestamp_utc=now_utc_iso(),
               event_type="created",
               entry_id=new_entry_id(),
               schema_version=1,
               payload={"action": "synthesised", "actor": actor.model_dump(mode="json"), "entry_data": {"task_type": "retrieval", "query": "q?", "expected_chunk_ids": [], "chunk_hashes": {}}},
           ))
       # deprecate one
       all_events = list(events_path.read_text().splitlines())
       import json as _json
       first_id = _json.loads(all_events[0])["entry_id"]
       append_event(events_path, Event(
           event_id=new_event_id(),
           timestamp_utc=now_utc_iso(),
           event_type="deprecated",
           entry_id=first_id,
           schema_version=1,
           payload={"actor": actor.model_dump(mode="json"), "reason": "test"},
       ))
       return tmp_path, slug


   def test_synthese_stats_survival_rate(populated_root):
       root, slug = populated_root
       client = TestClient(create_app(data_root=root))
       r = client.get(f"/api/admin/statistics/synthese/{slug}")
       assert r.status_code == 200
       body = r.json()
       assert body["questions_created"] == 5
       assert body["questions_deprecated"] == 1
       assert body["survival_rate"] == pytest.approx(4 / 5)
       # No votes yet → zero counts, null rate, empty distribution.
       assert body["vote_approved"] == 0
       assert body["vote_rejected"] == 0
       assert body["vote_approval_rate"] is None
       assert body["vote_distribution"] == []
   ```

2. Extend the router.
   ```python
   # Append to statistics.py — imports first
   from goldens.storage import GOLDEN_EVENTS_V1_FILENAME, iter_active_retrieval_entries
   from goldens.storage.log import read_events
   from local_pdf.api.models.statistics import (
       SyntheseStats,
       VoteDistributionRow,
   )


   def _events_path(data_root: Path, slug: str) -> Path:
       return data_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME


   def _collapse_votes(events) -> tuple[dict[tuple[str, str], str], dict[str, dict[str, int]]]:
       """Walk reviewed events; return (latest_per_pair, per_entry_counts).

       latest_per_pair maps (entry_id, pseudonym) → action.
       per_entry_counts maps entry_id → {"approved": n, "rejected": m}
       counting only non-revoked latest votes.
       """
       latest: dict[tuple[str, str], tuple[str, str]] = {}
       for ev in events:
           if ev.event_type != "reviewed":
               continue
           action = ev.payload.get("action")
           if action not in {"approved", "rejected", "revoked"}:
               continue
           actor = ev.payload.get("actor") or {}
           pseudo = actor.get("pseudonym")
           if not pseudo:
               continue
           key = (ev.entry_id, pseudo)
           prev = latest.get(key)
           if prev is None or ev.timestamp_utc >= prev[1]:
               latest[key] = (action, ev.timestamp_utc)
       latest_actions = {k: v[0] for k, v in latest.items()}
       per_entry: dict[str, dict[str, int]] = {}
       for (entry_id, _pseudo), action in latest_actions.items():
           if action == "revoked":
               continue
           bucket = per_entry.setdefault(entry_id, {"approved": 0, "rejected": 0})
           bucket[action] += 1
       return latest_actions, per_entry


   @router.get("/api/admin/statistics/synthese/{slug}", response_model=SyntheseStats)
   async def synthese_stats(slug: str, request: Request) -> SyntheseStats:
       data_root = _tr(request)
       if not doc_dir(data_root, slug).exists():
           raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
       path = _events_path(data_root, slug)
       events = read_events(path) if path.exists() else []
       created = sum(1 for ev in events if ev.event_type == "created")
       deprecated = sum(1 for ev in events if ev.event_type == "deprecated")
       survival = ((created - deprecated) / created) if created > 0 else None

       _, per_entry = _collapse_votes(events)
       total_approved = sum(v["approved"] for v in per_entry.values())
       total_rejected = sum(v["rejected"] for v in per_entry.values())
       denom = total_approved + total_rejected
       approval_rate = (total_approved / denom) if denom > 0 else None

       # Build short-text lookup for vote_distribution rows.
       text_by_entry: dict[str, str] = {}
       if path.exists():
           for entry in iter_active_retrieval_entries(path):
               text_by_entry[entry.entry_id] = (entry.query or "")[:60]

       rows = [
           VoteDistributionRow(
               entry_id=entry_id,
               text_short=text_by_entry.get(entry_id, entry_id),
               approved=counts["approved"],
               rejected=counts["rejected"],
           )
           for entry_id, counts in per_entry.items()
       ]
       rows.sort(key=lambda r: min(r.approved, r.rejected), reverse=True)
       rows = rows[:20]

       return SyntheseStats(
           slug=slug,
           questions_created=created,
           questions_deprecated=deprecated,
           survival_rate=survival,
           vote_approved=total_approved,
           vote_rejected=total_rejected,
           vote_approval_rate=approval_rate,
           vote_distribution=rows,
       )
   ```

3. Run the test.
   ```bash
   cd features/pipelines/local-pdf && uv run pytest tests/api/admin/test_statistics_synthese.py -v
   ```
   Expected: passing.

4. Commit.
   ```bash
   git add features/pipelines/local-pdf/src/local_pdf/api/routers/admin/statistics.py features/pipelines/local-pdf/tests/api/admin/test_statistics_synthese.py
   git commit -m "feat(stats): synthese-stats endpoint with curator-survival and vote aggregation"
   ```

---

## Task 5: Statistics backend — provenienz + capability-wishes endpoints

**Files**:
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/statistics.py`
- Create: `features/pipelines/local-pdf/tests/api/admin/test_statistics_provenienz.py`

**Steps**:

1. Write the test.
   ```python
   # features/pipelines/local-pdf/tests/api/admin/test_statistics_provenienz.py
   from pathlib import Path

   import pytest
   from fastapi.testclient import TestClient

   from local_pdf.api.app import create_app


   def _seed_session(root: Path, slug: str, session_id: str, nodes: list[dict]) -> None:
       sd = root / slug / "provenienz" / session_id
       sd.mkdir(parents=True)
       # Use the same writer the production code uses so the test isn't
       # coupled to an internal layout. Tests for read_session in the
       # provenienz module already pin the on-disk format.
       from local_pdf.provenienz.persistence import write_session
       write_session(sd, nodes=nodes, edges=[])


   def test_provenienz_stats_counts_overrides(tmp_path: Path):
       slug = "doc-a"
       (tmp_path / slug).mkdir()
       _seed_session(tmp_path, slug, "s1", [
           {"node_id": "n1", "session_id": "s1", "kind": "plan_proposal", "actor": "agent", "payload": {}, "created_at": "2026-06-01T00:00:00Z"},
           {"node_id": "n2", "session_id": "s1", "kind": "plan_proposal", "actor": "agent", "payload": {}, "created_at": "2026-06-01T00:01:00Z"},
           {"node_id": "n3", "session_id": "s1", "kind": "expert_step_override", "actor": "human", "payload": {}, "created_at": "2026-06-01T00:02:00Z"},
       ])
       client = TestClient(create_app(data_root=tmp_path))
       r = client.get(f"/api/admin/statistics/provenienz/{slug}")
       assert r.status_code == 200
       body = r.json()
       assert body["plan_proposals"] == 2
       assert body["expert_overrides"] == 1
       assert body["correction_rate"] == pytest.approx(0.5)


   def test_capability_wishes_endpoint_returns_skill_buckets(tmp_path: Path):
       slug = "doc-a"
       (tmp_path / slug).mkdir()
       _seed_session(tmp_path, slug, "s1", [
           {"node_id": "n1", "session_id": "s1", "kind": "capability_request", "actor": "agent", "payload": {"name": "RegisterLookup", "description": ""}, "created_at": "2026-06-01T00:00:00Z"},
           {"node_id": "n2", "session_id": "s1", "kind": "capability_request", "actor": "agent", "payload": {"name": "RegisterMatch", "description": ""}, "created_at": "2026-06-01T00:01:00Z"},
       ])
       client = TestClient(create_app(data_root=tmp_path))
       r = client.get("/api/admin/statistics/capability-wishes")
       assert r.status_code == 200
       wishes = r.json()["wishes"]
       names = {w["name"] for w in wishes}
       assert {"RegisterLookup", "RegisterMatch"} <= names
       for w in wishes:
           assert w["skill_bucket"] == "register"
   ```

2. Extend the router.
   ```python
   # Append to statistics.py
   from local_pdf.api.models.statistics import (
       CapabilityWish,
       CapabilityWishes,
       ProvenienzStats,
   )
   from local_pdf.api.routers.admin.provenienz import list_capability_requests
   from local_pdf.provenienz.persistence import read_session


   _EXPERT_OVERRIDE_KINDS = {"expert_step_override", "expert_method_request"}


   @router.get("/api/admin/statistics/provenienz/{slug}", response_model=ProvenienzStats)
   async def provenienz_stats(slug: str, request: Request) -> ProvenienzStats:
       data_root = _tr(request)
       if not doc_dir(data_root, slug).exists():
           raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
       prov_root = data_root / slug / "provenienz"
       plan_proposals = 0
       overrides = 0
       if prov_root.exists():
           for sd in sorted(prov_root.iterdir()):
               if not sd.is_dir():
                   continue
               try:
                   nodes, _ = read_session(sd)
               except Exception:
                   continue
               for n in nodes:
                   if n.kind == "plan_proposal":
                       plan_proposals += 1
                   elif n.kind in _EXPERT_OVERRIDE_KINDS:
                       overrides += 1
       rate = (overrides / plan_proposals) if plan_proposals > 0 else None
       return ProvenienzStats(
           slug=slug,
           plan_proposals=plan_proposals,
           expert_overrides=overrides,
           correction_rate=rate,
       )


   def _skill_bucket(name: str) -> str:
       """Heuristic: lowercased leading word (camelCase split on first uppercase).

       Falls back to 'other' for empty / unrecognised names so the
       Treemap always has a parent node.
       """
       name = name.strip()
       if not name:
           return "other"
       head = []
       for i, ch in enumerate(name):
           if i > 0 and ch.isupper():
               break
           head.append(ch)
       return "".join(head).lower() or "other"


   @router.get("/api/admin/statistics/capability-wishes", response_model=CapabilityWishes)
   async def capability_wishes(request: Request) -> CapabilityWishes:
       # Reuse the existing aggregator — same tenant-aware data_root walk.
       raw = await list_capability_requests(request)  # returns dict
       wishes = [
           CapabilityWish(
               name=item["name"],
               count=item["count"],
               by_actor=item.get("count_by_actor") or {"human": 0, "agent": item["count"]},
               skill_bucket=_skill_bucket(item["name"]),
           )
           for item in raw.get("requests", [])
       ]
       return CapabilityWishes(wishes=wishes)
   ```

3. Run the tests.
   ```bash
   cd features/pipelines/local-pdf && uv run pytest tests/api/admin/test_statistics_provenienz.py -v
   ```
   Expected: passing.

4. Commit.
   ```bash
   git add features/pipelines/local-pdf/src/local_pdf/api/routers/admin/statistics.py features/pipelines/local-pdf/tests/api/admin/test_statistics_provenienz.py
   git commit -m "feat(stats): provenienz and capability-wishes endpoints"
   ```

---

## Task 6: Frontend hooks for statistics

**Files**:
- Create: `frontend/src/admin/hooks/useStatistics.ts`
- Create: `frontend/src/admin/hooks/__tests__/useStatistics.test.tsx`

**Steps**:

1. Write the hook file.
   ```ts
   // frontend/src/admin/hooks/useStatistics.ts
   import { useQuery } from "@tanstack/react-query";
   import { apiBase } from "../api/adminClient";

   /** Field names mirror the Pydantic models in
    *  features/pipelines/local-pdf/src/local_pdf/api/models/statistics.py
    *  1:1. Do not rename without updating both ends. */

   export interface DiagnosticCounts {
     split: number;
     no_decomposition: number;
     clean: number;
     total: number;
   }

   export interface ExtractStats {
     slug: string;
     diagnostics: DiagnosticCounts;
     register_boxes: number;
     total_boxes: number;
     register_rate: number | null;
   }

   export interface VoteDistributionRow {
     entry_id: string;
     text_short: string;
     approved: number;
     rejected: number;
   }

   export interface SyntheseStats {
     slug: string;
     questions_created: number;
     questions_deprecated: number;
     survival_rate: number | null;
     vote_approved: number;
     vote_rejected: number;
     vote_approval_rate: number | null;
     vote_distribution: VoteDistributionRow[];
   }

   export interface ProvenienzStats {
     slug: string;
     plan_proposals: number;
     expert_overrides: number;
     correction_rate: number | null;
   }

   export interface CapabilityWish {
     name: string;
     count: number;
     by_actor: Record<string, number>;
     skill_bucket: string;
   }

   export interface CapabilityWishes {
     wishes: CapabilityWish[];
   }

   async function fetchOk(url: string, token: string): Promise<Response> {
     const r = await fetch(url, { headers: { "X-Auth-Token": token } });
     if (!r.ok) {
       let detail = `${r.status} ${r.statusText}`;
       try {
         const body = await r.json();
         if (body && typeof body.detail === "string") detail = body.detail;
       } catch {
         /* keep status fallback */
       }
       throw new Error(detail);
     }
     return r;
   }

   export function useExtractStats(slug: string, token: string) {
     return useQuery<ExtractStats>({
       queryKey: ["stats", "extract", slug],
       queryFn: async () => {
         const r = await fetchOk(`${apiBase()}/api/admin/statistics/extract/${encodeURIComponent(slug)}`, token);
         return r.json();
       },
       retry: false,
     });
   }

   export function useSyntheseStats(slug: string, token: string) {
     return useQuery<SyntheseStats>({
       queryKey: ["stats", "synthese", slug],
       queryFn: async () => {
         const r = await fetchOk(`${apiBase()}/api/admin/statistics/synthese/${encodeURIComponent(slug)}`, token);
         return r.json();
       },
       retry: false,
     });
   }

   export function useProvenienzStats(slug: string, token: string) {
     return useQuery<ProvenienzStats>({
       queryKey: ["stats", "provenienz", slug],
       queryFn: async () => {
         const r = await fetchOk(`${apiBase()}/api/admin/statistics/provenienz/${encodeURIComponent(slug)}`, token);
         return r.json();
       },
       retry: false,
     });
   }

   export function useCapabilityWishes(token: string) {
     return useQuery<CapabilityWishes>({
       queryKey: ["stats", "capability-wishes"],
       queryFn: async () => {
         const r = await fetchOk(`${apiBase()}/api/admin/statistics/capability-wishes`, token);
         return r.json();
       },
       retry: false,
     });
   }
   ```

2. Test with MSW.
   ```tsx
   // frontend/src/admin/hooks/__tests__/useStatistics.test.tsx
   import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
   import { renderHook, waitFor } from "@testing-library/react";
   import { setupServer } from "msw/node";
   import { http, HttpResponse } from "msw";
   import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

   import { useExtractStats, useSyntheseStats } from "../useStatistics";

   const server = setupServer(
     http.get("*/api/admin/statistics/extract/:slug", () =>
       HttpResponse.json({
         slug: "doc-a",
         diagnostics: { split: 1, no_decomposition: 0, clean: 9, total: 10 },
         register_boxes: 2,
         total_boxes: 4,
         register_rate: 0.5,
       })
     ),
     http.get("*/api/admin/statistics/synthese/:slug", () =>
       HttpResponse.json({
         slug: "doc-a",
         questions_created: 5,
         questions_deprecated: 1,
         survival_rate: 0.8,
         vote_approved: 3,
         vote_rejected: 1,
         vote_approval_rate: 0.75,
         vote_distribution: [
           { entry_id: "q1", text_short: "Was ist…", approved: 2, rejected: 1 },
         ],
       })
     ),
   );

   beforeAll(() => server.listen());
   afterEach(() => server.resetHandlers());
   afterAll(() => server.close());

   function wrapper({ children }: { children: React.ReactNode }) {
     const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
     return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
   }

   describe("useStatistics hooks", () => {
     it("fetches extract stats", async () => {
       const { result } = renderHook(() => useExtractStats("doc-a", "tok"), { wrapper });
       await waitFor(() => expect(result.current.isSuccess).toBe(true));
       expect(result.current.data?.register_rate).toBe(0.5);
     });

     it("fetches synthese stats", async () => {
       const { result } = renderHook(() => useSyntheseStats("doc-a", "tok"), { wrapper });
       await waitFor(() => expect(result.current.isSuccess).toBe(true));
       expect(result.current.data?.vote_approval_rate).toBe(0.75);
     });
   });
   ```

3. Run.
   ```bash
   cd frontend && npm run test -- useStatistics
   ```
   Expected: 2 passing.

4. Commit.
   ```bash
   git add frontend/src/admin/hooks/useStatistics.ts frontend/src/admin/hooks/__tests__/useStatistics.test.tsx
   git commit -m "feat(stats): react-query hooks and types for statistics endpoints"
   ```

---

## Task 7: MetricGauge + MetricCounter chart components

**Files**:
- Create: `frontend/src/admin/components/charts/MetricGauge.tsx`
- Create: `frontend/src/admin/components/charts/MetricCounter.tsx`
- Create: `frontend/src/admin/components/charts/__tests__/MetricGauge.test.tsx`
- Create: `frontend/src/admin/components/charts/__tests__/MetricCounter.test.tsx`

**Steps**:

1. MetricGauge.
   ```tsx
   // frontend/src/admin/components/charts/MetricGauge.tsx
   import { RadialBar, RadialBarChart, PolarAngleAxis } from "recharts";
   import { motion } from "framer-motion";

   import { RechartsNavyTheme, useChartPalette } from "./RechartsNavyTheme";
   import { T } from "../../styles/typography";

   interface Props {
     value: number | null;
     label: string;
     subtitle?: string;
   }

   function Inner({ value }: { value: number }): JSX.Element {
     const palette = useChartPalette();
     const pct = Math.round(value * 100);
     const fill = value >= 0.7 ? palette.success : value >= 0.4 ? palette.accent : palette.danger;
     return (
       <RadialBarChart
         innerRadius="70%"
         outerRadius="100%"
         data={[{ name: "v", value: pct, fill }]}
         startAngle={90}
         endAngle={-270}
       >
         <PolarAngleAxis type="number" domain={[0, 100]} angleAxisId={0} tick={false} />
         <RadialBar background dataKey="value" cornerRadius={6} />
       </RadialBarChart>
     );
   }

   export function MetricGauge({ value, label, subtitle }: Props): JSX.Element {
     return (
       <motion.div
         className="flex flex-col items-center"
         initial={{ opacity: 0, y: 8 }}
         animate={{ opacity: 1, y: 0 }}
         transition={{ duration: 0.3 }}
       >
         <div className={`${T.heading} text-navy-200 mb-1`}>{label}</div>
         <RechartsNavyTheme height={160}>
           {value === null ? (
             <div className="flex items-center justify-center h-full text-navy-200 text-2xl">–</div>
           ) : (
             <Inner value={value} />
           )}
         </RechartsNavyTheme>
         <div className={`${T.body} text-navy-200 mt-1`}>
           {value === null ? "Keine Daten" : `${Math.round(value * 100)} %`}
         </div>
         {subtitle && <div className={`${T.tiny} text-navy-300`}>{subtitle}</div>}
       </motion.div>
     );
   }
   ```

2. MetricCounter.
   ```tsx
   // frontend/src/admin/components/charts/MetricCounter.tsx
   import { motion, useMotionValue, useTransform, animate } from "framer-motion";
   import { useEffect } from "react";

   import { T } from "../../styles/typography";

   interface Props {
     value: number;
     label: string;
     suffix?: string;
   }

   export function MetricCounter({ value, label, suffix }: Props): JSX.Element {
     const mv = useMotionValue(0);
     const rounded = useTransform(mv, (v) => Math.round(v));
     useEffect(() => {
       const controls = animate(mv, value, { duration: 0.8, ease: "easeOut" });
       return () => controls.stop();
     }, [mv, value]);

     return (
       <motion.div
         className="rounded bg-navy-800 p-4 flex flex-col items-start"
         initial={{ opacity: 0, scale: 0.96 }}
         animate={{ opacity: 1, scale: 1 }}
         transition={{ duration: 0.25 }}
       >
         <div className={`${T.tinyBold} text-navy-300`}>{label}</div>
         <div className="text-3xl font-semibold text-white tabular-nums mt-1">
           <motion.span>{rounded}</motion.span>
           {suffix && <span className="text-navy-200 ml-1 text-base">{suffix}</span>}
         </div>
       </motion.div>
     );
   }
   ```

3. Tests.
   ```tsx
   // frontend/src/admin/components/charts/__tests__/MetricGauge.test.tsx
   import { render, screen } from "@testing-library/react";
   import { describe, expect, it } from "vitest";
   import { MetricGauge } from "../MetricGauge";

   describe("MetricGauge", () => {
     it("shows percent label when value is non-null", () => {
       render(<MetricGauge value={0.42} label="Test" />);
       expect(screen.getByText("Test")).toBeInTheDocument();
       expect(screen.getByText("42 %")).toBeInTheDocument();
     });

     it("shows en-dash when value is null", () => {
       render(<MetricGauge value={null} label="Empty" />);
       expect(screen.getByText("Keine Daten")).toBeInTheDocument();
       expect(screen.getByText("–")).toBeInTheDocument();
     });
   });
   ```

   ```tsx
   // frontend/src/admin/components/charts/__tests__/MetricCounter.test.tsx
   import { render, screen } from "@testing-library/react";
   import { describe, expect, it } from "vitest";
   import { MetricCounter } from "../MetricCounter";

   describe("MetricCounter", () => {
     it("renders label and suffix", () => {
       render(<MetricCounter value={42} label="Boxen" suffix="px" />);
       expect(screen.getByText("Boxen")).toBeInTheDocument();
       expect(screen.getByText("px")).toBeInTheDocument();
     });
   });
   ```

4. Run.
   ```bash
   cd frontend && npm run test -- MetricGauge MetricCounter
   ```
   Expected: 3 passing.

5. Commit.
   ```bash
   git add frontend/src/admin/components/charts/MetricGauge.tsx frontend/src/admin/components/charts/MetricCounter.tsx frontend/src/admin/components/charts/__tests__/MetricGauge.test.tsx frontend/src/admin/components/charts/__tests__/MetricCounter.test.tsx
   git commit -m "feat(stats): metric-gauge and metric-counter chart components"
   ```

---

## Task 8: DiagnosticBar component

**Files**:
- Create: `frontend/src/admin/components/charts/DiagnosticBar.tsx`
- Create: `frontend/src/admin/components/charts/__tests__/DiagnosticBar.test.tsx`

**Steps**:

1. Component.
   ```tsx
   // frontend/src/admin/components/charts/DiagnosticBar.tsx
   import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
   import { motion } from "framer-motion";

   import { RechartsNavyTheme, useChartPalette } from "./RechartsNavyTheme";
   import type { DiagnosticCounts } from "../../hooks/useStatistics";
   import { T } from "../../styles/typography";

   interface Props {
     data: DiagnosticCounts;
   }

   function Inner({ data }: Props): JSX.Element {
     const p = useChartPalette();
     const rows = [
       { name: "Diagnose", split: data.split, no_decomposition: data.no_decomposition, clean: data.clean },
     ];
     return (
       <BarChart data={rows} layout="vertical" margin={{ left: 16, right: 16 }}>
         <defs>
           <linearGradient id="gradClean" x1="0" y1="0" x2="1" y2="0">
             <stop offset="0%" stopColor={p.success} stopOpacity={0.9} />
             <stop offset="100%" stopColor={p.success} stopOpacity={0.6} />
           </linearGradient>
         </defs>
         <CartesianGrid strokeDasharray="3 3" stroke={p.grid} />
         <XAxis type="number" stroke={p.text} />
         <YAxis dataKey="name" type="category" stroke={p.text} />
         <Tooltip contentStyle={{ background: p.bg, border: `1px solid ${p.grid}`, color: p.text }} />
         <Bar dataKey="clean" stackId="d" fill="url(#gradClean)" />
         <Bar dataKey="no_decomposition" stackId="d" fill={p.danger} />
         <Bar dataKey="split" stackId="d" fill={p.warn} />
       </BarChart>
     );
   }

   export function DiagnosticBar({ data }: Props): JSX.Element {
     return (
       <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
         <div className={`${T.heading} text-navy-200 mb-1`}>Diagnose-Flags</div>
         <RechartsNavyTheme height={120}>
           <Inner data={data} />
         </RechartsNavyTheme>
       </motion.div>
     );
   }
   ```

2. Test.
   ```tsx
   // frontend/src/admin/components/charts/__tests__/DiagnosticBar.test.tsx
   import { render, screen } from "@testing-library/react";
   import { describe, expect, it } from "vitest";
   import { DiagnosticBar } from "../DiagnosticBar";

   describe("DiagnosticBar", () => {
     it("renders the heading", () => {
       render(<DiagnosticBar data={{ split: 1, no_decomposition: 0, clean: 9, total: 10 }} />);
       expect(screen.getByText("Diagnose-Flags")).toBeInTheDocument();
     });
   });
   ```

3. Run.
   ```bash
   cd frontend && npm run test -- DiagnosticBar
   ```

4. Commit.
   ```bash
   git add frontend/src/admin/components/charts/DiagnosticBar.tsx frontend/src/admin/components/charts/__tests__/DiagnosticBar.test.tsx
   git commit -m "feat(stats): diagnostic stacked-bar chart"
   ```

---

## Task 9: CapabilityWishesSunburst (Treemap fallback, hard-locked at impl time)

**Files**:
- Create: `frontend/src/admin/components/charts/CapabilityWishesSunburst.tsx`
- Create: `frontend/src/admin/components/charts/__tests__/CapabilityWishesSunburst.test.tsx`

**Steps**:

1. Re-verify Recharts capabilities before writing code (the spec already
   states Sunburst is absent in 3.8.x; this step is the runtime double-check
   the spec's Risk-section calls for).
   ```bash
   cd frontend && node -e "const r=require('recharts'); ['Sunburst','Treemap','Pie','PieChart'].forEach(k=>console.log(k, typeof r[k]))"
   ```
   Expected output: `Sunburst undefined`, `Treemap function`, `Pie function`, `PieChart function`.

2. Implement using Treemap.
   ```tsx
   // frontend/src/admin/components/charts/CapabilityWishesSunburst.tsx
   //
   // Capability-Wünsche hierarchy chart. Recharts 3.8 has no native
   // Sunburst — we use <Treemap> with two levels (Skill → Tool) which
   // produces a defensible Agent → Skill → Tool reading because Agent
   // is constant ("Provenienz-Agent") in v1. A future multi-agent
   // topology can either (a) introduce a third Treemap level or (b)
   // swap to nested <Pie> rings (commented fallback below).
   import { Treemap, Tooltip } from "recharts";
   import { motion } from "framer-motion";

   import { RechartsNavyTheme, useChartPalette } from "./RechartsNavyTheme";
   import type { CapabilityWish } from "../../hooks/useStatistics";
   import { T } from "../../styles/typography";

   interface Props {
     wishes: CapabilityWish[];
   }

   interface TreeNode {
     name: string;
     size?: number;
     children?: TreeNode[];
   }

   function buildTree(wishes: CapabilityWish[]): TreeNode {
     const byBucket: Record<string, TreeNode[]> = {};
     for (const w of wishes) {
       (byBucket[w.skill_bucket] ??= []).push({ name: w.name, size: w.count });
     }
     return {
       name: "Provenienz-Agent",
       children: Object.entries(byBucket).map(([bucket, kids]) => ({
         name: bucket,
         children: kids,
       })),
     };
   }

   function Inner({ wishes }: Props): JSX.Element {
     const p = useChartPalette();
     const data = buildTree(wishes).children ?? [];
     return (
       <Treemap
         data={data}
         dataKey="size"
         stroke={p.bg}
         fill={p.accent}
         isAnimationActive
         animationDuration={500}
         content={undefined}
       >
         <Tooltip contentStyle={{ background: p.bg, border: `1px solid ${p.grid}`, color: p.text }} />
       </Treemap>
     );
   }

   export function CapabilityWishesSunburst({ wishes }: Props): JSX.Element {
     return (
       <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4 }}>
         <div className={`${T.heading} text-navy-200 mb-1`}>Capability-Wünsche (Über alle Dokumente)</div>
         <RechartsNavyTheme height={320}>
           {wishes.length === 0 ? (
             <div className="flex items-center justify-center h-full text-navy-200">Noch keine Wünsche</div>
           ) : (
             <Inner wishes={wishes} />
           )}
         </RechartsNavyTheme>
       </motion.div>
     );
   }
   ```

3. Test.
   ```tsx
   // frontend/src/admin/components/charts/__tests__/CapabilityWishesSunburst.test.tsx
   import { render, screen } from "@testing-library/react";
   import { describe, expect, it } from "vitest";
   import { CapabilityWishesSunburst } from "../CapabilityWishesSunburst";

   describe("CapabilityWishesSunburst", () => {
     it("renders empty-state when wishes is empty", () => {
       render(<CapabilityWishesSunburst wishes={[]} />);
       expect(screen.getByText("Noch keine Wünsche")).toBeInTheDocument();
     });

     it("renders heading when wishes are present", () => {
       render(
         <CapabilityWishesSunburst
           wishes={[
             { name: "RegisterLookup", count: 3, by_actor: { human: 0, agent: 3 }, skill_bucket: "register" },
           ]}
         />
       );
       expect(screen.getByText(/Capability-Wünsche/)).toBeInTheDocument();
     });
   });
   ```

4. Run.
   ```bash
   cd frontend && npm run test -- CapabilityWishesSunburst
   ```

5. Commit.
   ```bash
   git add frontend/src/admin/components/charts/CapabilityWishesSunburst.tsx frontend/src/admin/components/charts/__tests__/CapabilityWishesSunburst.test.tsx
   git commit -m "feat(stats): capability-wishes treemap (recharts sunburst fallback)"
   ```

---

## Task 10: Statistics route + tab registration

**Files**:
- Create: `frontend/src/admin/routes/Statistics.tsx`
- Modify: `frontend/src/admin/components/DocStepTabs.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/admin/routes/__tests__/Statistics.test.tsx`

**Steps**:

1. Add the tab in `DocStepTabs.tsx`.
   ```tsx
   // Edit imports
   import { BarChart3, FileText, Folder, GitCompare, GitMerge, Sparkles } from "lucide-react";
   // Add to TABS array (after "provenienz"):
   { key: "statistics", label: "Statistik", icon: BarChart3, href: (slug: string) => `/admin/doc/${slug}/statistics` },
   // Extend isActive:
   if (key === "statistics") return pathname.endsWith("/statistics");
   ```

2. Build the route shell.
   ```tsx
   // frontend/src/admin/routes/Statistics.tsx
   import { useParams } from "react-router-dom";
   import { useAuth } from "../../auth/AuthProvider";

   import {
     useCapabilityWishes,
     useExtractStats,
     useProvenienzStats,
     useSyntheseStats,
   } from "../hooks/useStatistics";
   import { CapabilityWishesSunburst } from "../components/charts/CapabilityWishesSunburst";
   import { DiagnosticBar } from "../components/charts/DiagnosticBar";
   import { MetricCounter } from "../components/charts/MetricCounter";
   import { MetricGauge } from "../components/charts/MetricGauge";
   import { VoteDistributionBar } from "../components/charts/VoteDistributionBar";
   import { T } from "../styles/typography";

   export function Statistics(): JSX.Element {
     const { slug = "" } = useParams<{ slug: string }>();
     const { token } = useAuth();
     const extract = useExtractStats(slug, token);
     const synthese = useSyntheseStats(slug, token);
     const provenienz = useProvenienzStats(slug, token);
     const wishes = useCapabilityWishes(token);

     return (
       <div className="p-4 space-y-6">
         <section>
           <h2 className={`${T.cardTitle} text-navy-100 mb-3`}>Extrahieren</h2>
           {extract.data && (
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
               <DiagnosticBar data={extract.data.diagnostics} />
               <MetricCounter
                 value={extract.data.register_boxes}
                 label="Register-Boxen"
                 suffix={`/ ${extract.data.total_boxes}`}
               />
             </div>
           )}
         </section>

         <section>
           <h2 className={`${T.cardTitle} text-navy-100 mb-3`}>Synthese</h2>
           {synthese.data && (
             <div className="space-y-4">
               <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                 <MetricGauge
                   value={synthese.data.survival_rate}
                   label="Curator-Überleben"
                   subtitle={`${synthese.data.questions_created - synthese.data.questions_deprecated} / ${synthese.data.questions_created}`}
                 />
                 <MetricGauge
                   value={synthese.data.vote_approval_rate}
                   label="Reviewer-Zustimmung"
                   subtitle={`${synthese.data.vote_approved} / ${synthese.data.vote_approved + synthese.data.vote_rejected}`}
                 />
               </div>
               <VoteDistributionBar rows={synthese.data.vote_distribution} />
             </div>
           )}
         </section>

         <section>
           <h2 className={`${T.cardTitle} text-navy-100 mb-3`}>Provenienz</h2>
           {provenienz.data && (
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
               <MetricGauge
                 value={provenienz.data.correction_rate}
                 label="Experten-Korrekturen"
                 subtitle={`${provenienz.data.expert_overrides} / ${provenienz.data.plan_proposals}`}
               />
             </div>
           )}
           {wishes.data && <CapabilityWishesSunburst wishes={wishes.data.wishes} />}
         </section>
       </div>
     );
   }
   ```

3. Register the route in `App.tsx`.
   ```tsx
   // Add to the imports block:
   import { Statistics } from "./admin/routes/Statistics";
   // Add inside the AdminShell Route block, after provenienz:
   <Route path="doc/:slug/statistics" element={<Statistics />} />
   ```

4. Smoke-test that the route mounts.
   ```tsx
   // frontend/src/admin/routes/__tests__/Statistics.test.tsx
   import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
   import { render, screen, waitFor } from "@testing-library/react";
   import { MemoryRouter, Route, Routes } from "react-router-dom";
   import { setupServer } from "msw/node";
   import { http, HttpResponse } from "msw";
   import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

   import { Statistics } from "../Statistics";

   // Mock useAuth — the real provider walks cookies/local storage and
   // would need a much larger context wrap.
   vi.mock("../../../auth/AuthProvider", () => ({ useAuth: () => ({ token: "tok" }) }));

   const server = setupServer(
     http.get("*/api/admin/statistics/extract/:slug", () =>
       HttpResponse.json({
         slug: "doc-a",
         diagnostics: { split: 0, no_decomposition: 0, clean: 0, total: 0 },
         register_boxes: 2,
         total_boxes: 5,
         register_rate: 0.4,
       })
     ),
     http.get("*/api/admin/statistics/synthese/:slug", () =>
       HttpResponse.json({
         slug: "doc-a",
         questions_created: 1,
         questions_deprecated: 0,
         survival_rate: 1,
         vote_approved: 0,
         vote_rejected: 0,
         vote_approval_rate: null,
         vote_distribution: [],
       })
     ),
     http.get("*/api/admin/statistics/provenienz/:slug", () =>
       HttpResponse.json({ slug: "doc-a", plan_proposals: 0, expert_overrides: 0, correction_rate: null })
     ),
     http.get("*/api/admin/statistics/capability-wishes", () => HttpResponse.json({ wishes: [] })),
   );

   beforeAll(() => server.listen());
   afterEach(() => server.resetHandlers());
   afterAll(() => server.close());

   describe("Statistics page", () => {
     it("renders three section headings", async () => {
       const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
       render(
         <QueryClientProvider client={qc}>
           <MemoryRouter initialEntries={["/admin/doc/doc-a/statistics"]}>
             <Routes>
               <Route path="/admin/doc/:slug/statistics" element={<Statistics />} />
             </Routes>
           </MemoryRouter>
         </QueryClientProvider>
       );
       await waitFor(() => {
         expect(screen.getByText("Extrahieren")).toBeInTheDocument();
         expect(screen.getByText("Synthese")).toBeInTheDocument();
         expect(screen.getByText("Provenienz")).toBeInTheDocument();
       });
     });
   });
   ```
   Note: This test will require `VoteDistributionBar` to exist (Task 13) before it passes; create a one-line stub component file early in step 2 above ("export function VoteDistributionBar(){ return null; }") then replace with the real implementation in Task 13. The test in this Task asserts only headings, so the stub is fine.

5. Stub VoteDistributionBar so the route renders without Task 13.
   ```tsx
   // frontend/src/admin/components/charts/VoteDistributionBar.tsx
   import type { VoteDistributionRow } from "../../hooks/useStatistics";
   interface Props { rows: VoteDistributionRow[] }
   export function VoteDistributionBar(_props: Props): JSX.Element { return <div /> }
   ```

6. Run.
   ```bash
   cd frontend && npm run test -- Statistics
   ```

7. Commit.
   ```bash
   git add frontend/src/admin/components/DocStepTabs.tsx frontend/src/App.tsx frontend/src/admin/routes/Statistics.tsx frontend/src/admin/routes/__tests__/Statistics.test.tsx frontend/src/admin/components/charts/VoteDistributionBar.tsx
   git commit -m "feat(stats): statistics route, sixth doc-step tab, route registration"
   ```

---

## Task 11: users.level SQLite migration

**Files**:
- Modify: `features/pipelines/local-pdf/src/local_pdf/auth/db.py`
- Modify: `features/pipelines/local-pdf/src/local_pdf/auth/users.py`
- Create: `features/pipelines/local-pdf/tests/auth/test_users_level_migration.py`

**Steps**:

1. Test the migration on a v1 DB.
   ```python
   # features/pipelines/local-pdf/tests/auth/test_users_level_migration.py
   import sqlite3
   from pathlib import Path

   from local_pdf.auth.db import _migrate_to_v1, ensure_schema, open_auth_db


   def test_migration_adds_level_column_to_existing_v1_db(tmp_path: Path):
       # Build a v1 DB directly so we can simulate an existing install.
       db_path = tmp_path / "_meta" / "auth.db"
       db_path.parent.mkdir(parents=True)
       conn = sqlite3.connect(db_path)
       conn.row_factory = sqlite3.Row
       _migrate_to_v1(conn)
       conn.execute("PRAGMA user_version = 1")
       # Seed one user.
       conn.execute("INSERT INTO tenants VALUES (?, ?, ?, ?)", ("t1", "default", "Default", "2026-01-01T00:00:00Z"))
       conn.execute(
           "INSERT INTO users (user_id, tenant_id, username, password_hash, pseudonym, role, active, created_at)"
           " VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
           ("u1", "t1", "alice", "h", "Alpha-Adler", "curator", "2026-01-01T00:00:00Z"),
       )
       conn.close()

       # Open via the public surface — this triggers v1 → v2.
       with open_auth_db(tmp_path) as conn:
           ensure_schema(conn)
           row = conn.execute("SELECT level FROM users WHERE user_id = 'u1'").fetchone()
           assert row["level"] == "other"

   def test_new_user_default_level(tmp_path: Path):
       from local_pdf.auth.users import create_user
       from local_pdf.auth.tenants import create_tenant

       with open_auth_db(tmp_path) as conn:
           ensure_schema(conn)
           tenant = create_tenant(conn, slug="default", name="Default")
           user = create_user(conn, tenant_id=tenant.tenant_id, username="bob", password="pw")
           assert user.level == "other"

   def test_create_user_with_explicit_level(tmp_path: Path):
       from local_pdf.auth.users import create_user
       from local_pdf.auth.tenants import create_tenant

       with open_auth_db(tmp_path) as conn:
           ensure_schema(conn)
           tenant = create_tenant(conn, slug="default", name="Default")
           user = create_user(conn, tenant_id=tenant.tenant_id, username="erin", password="pw", level="expert")
           assert user.level == "expert"
   ```

2. Run — expect failure (no migration yet).
   ```bash
   cd features/pipelines/local-pdf && uv run pytest tests/auth/test_users_level_migration.py -v
   ```

3. Bump schema version and add migration in `auth/db.py`.
   ```python
   # features/pipelines/local-pdf/src/local_pdf/auth/db.py
   _SCHEMA_VERSION = 2  # was 1
   # ...
   def ensure_schema(conn: sqlite3.Connection) -> None:
       current = int(conn.execute("PRAGMA user_version").fetchone()[0])
       if current >= _SCHEMA_VERSION:
           return
       if current < 1:
           _migrate_to_v1(conn)
       if current < 2:
           _migrate_to_v2(conn)
       conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


   def _migrate_to_v2(conn: sqlite3.Connection) -> None:
       """Add users.level column.

       Additive ALTER TABLE; existing rows backfill to 'other' via the
       NOT NULL DEFAULT clause at statement time. SQLite CHECK only
       enforces on new INSERTs — existing rows are valid against the
       default and stay valid.
       """
       conn.executescript(
           """
           BEGIN;
           ALTER TABLE users
             ADD COLUMN level TEXT NOT NULL DEFAULT 'other'
             CHECK (level IN ('expert', 'phd', 'masters', 'bachelors', 'other'));
           COMMIT;
           """
       )
   ```

4. Extend `User` dataclass + `create_user` + `_row_to_user` in `auth/users.py`.
   ```python
   # features/pipelines/local-pdf/src/local_pdf/auth/users.py
   Role = Literal["admin", "reviewer", "curator"]
   Level = Literal["expert", "phd", "masters", "bachelors", "other"]


   @dataclass(frozen=True)
   class User:
       user_id: str
       tenant_id: str
       username: str
       pseudonym: str
       role: Role
       active: bool
       created_at: str
       last_login_at: str | None
       level: Level = "other"


   def _row_to_user(row: sqlite3.Row) -> User:
       return User(
           user_id=row["user_id"],
           tenant_id=row["tenant_id"],
           username=row["username"],
           pseudonym=row["pseudonym"],
           role=row["role"],
           active=bool(row["active"]),
           created_at=row["created_at"],
           last_login_at=row["last_login_at"],
           level=row["level"] if "level" in row.keys() else "other",
       )


   def create_user(
       conn: sqlite3.Connection,
       *,
       tenant_id: str,
       username: str,
       password: str,
       role: Role = "curator",
       pseudonym: str | None = None,
       level: Level = "other",
   ) -> User:
       # ... existing body up through resolution of pseudonym_resolved + password_hash ...
       # Update the INSERT to include level:
       try:
           conn.execute(
               """
               INSERT INTO users
                 (user_id, tenant_id, username, password_hash, pseudonym, role, active, created_at, level)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
               """,
               (
                   user_id,
                   tenant_id,
                   username.strip(),
                   password_hash,
                   pseudonym_resolved,
                   role,
                   created_at,
                   level,
               ),
           )
       except sqlite3.IntegrityError as exc:
           raise ValueError(f"username or pseudonym already taken in tenant: {exc}") from exc

       return User(
           user_id=user_id,
           tenant_id=tenant_id,
           username=username.strip(),
           pseudonym=pseudonym_resolved,
           role=role,
           active=True,
           created_at=created_at,
           last_login_at=None,
           level=level,
       )
   ```

5. Re-run.
   ```bash
   cd features/pipelines/local-pdf && uv run pytest tests/auth/test_users_level_migration.py -v
   ```
   Expected: 3 passing.

6. Commit.
   ```bash
   git add features/pipelines/local-pdf/src/local_pdf/auth/db.py features/pipelines/local-pdf/src/local_pdf/auth/users.py features/pipelines/local-pdf/tests/auth/test_users_level_migration.py
   git commit -m "feat(auth): users.level column with additive v1->v2 migration"
   ```

---

## Task 12: goldens schema — add `revoked` ReviewAction

**Files**:
- Modify: `features/goldens/src/goldens/schemas/base.py`
- Create: `features/goldens/tests/schemas/test_review_action_revoked.py`

**Steps**:

1. Test the new action.
   ```python
   # features/goldens/tests/schemas/test_review_action_revoked.py
   from goldens.schemas.base import Event, HumanActor, Review


   def test_review_accepts_revoked_action():
       actor = HumanActor(pseudonym="Tester", level="other")
       r = Review(timestamp_utc="2026-06-03T00:00:00Z", action="revoked", actor=actor)
       assert r.action == "revoked"


   def test_event_carries_revoked_action_in_payload():
       actor = HumanActor(pseudonym="Tester", level="other")
       ev = Event(
           event_id="ev-1",
           timestamp_utc="2026-06-03T00:00:00Z",
           event_type="reviewed",
           entry_id="q-1",
           schema_version=1,
           payload={"action": "revoked", "actor": actor.model_dump(mode="json"), "notes": None},
       )
       assert ev.payload["action"] == "revoked"
   ```

2. Run — expect failure on `Review` strict validation.
   ```bash
   cd features/goldens && uv run pytest tests/schemas/test_review_action_revoked.py -v
   ```

3. Extend the Literal + tuple.
   ```python
   # features/goldens/src/goldens/schemas/base.py
   ReviewAction = Literal["accepted_unchanged", "approved", "rejected", "revoked"]

   _REVIEW_ACTIONS = (
       "created_from_scratch",
       "synthesised",
       "imported_from_faq",
       "accepted_unchanged",
       "approved",
       "rejected",
       "revoked",
       "deprecated",
   )


   class Review(BaseModel):
       model_config = ConfigDict(frozen=True)

       timestamp_utc: str
       action: Literal[
           "created_from_scratch",
           "synthesised",
           "imported_from_faq",
           "accepted_unchanged",
           "approved",
           "rejected",
           "revoked",
           "deprecated",
       ]
       actor: Actor
       notes: str | None = None

       @field_validator("timestamp_utc", mode="after")
       @classmethod
       def _ts_iso(cls, v: str) -> str:
           return _validate_iso_utc(v)
   ```

4. Re-run.
   ```bash
   cd features/goldens && uv run pytest tests/schemas/test_review_action_revoked.py -v
   ```

5. Commit.
   ```bash
   git add features/goldens/src/goldens/schemas/base.py features/goldens/tests/schemas/test_review_action_revoked.py
   git commit -m "feat(goldens): allow 'revoked' Review.action for vote toggle-off"
   ```

---

## Task 13: Backend vote endpoint + extend GET questions

**Files**:
- Modify: `features/pipelines/local-pdf/src/local_pdf/api/routers/admin/synthesise.py`
- Create: `features/pipelines/local-pdf/tests/api/admin/test_vote_endpoint.py`

**Steps**:

1. Test the vote POST and the extended GET.
   ```python
   # features/pipelines/local-pdf/tests/api/admin/test_vote_endpoint.py
   import json
   from pathlib import Path

   import pytest
   from fastapi.testclient import TestClient
   from goldens.operations._time import now_utc_iso
   from goldens.schemas.base import Event, HumanActor
   from goldens.storage import GOLDEN_EVENTS_V1_FILENAME
   from goldens.storage.ids import new_entry_id, new_event_id
   from goldens.storage.log import append_event

   from local_pdf.api.app import create_app


   @pytest.fixture
   def seeded(tmp_path: Path):
       slug = "doc-a"
       (tmp_path / slug).mkdir()
       (tmp_path / slug / "datasets").mkdir()
       (tmp_path / slug / "mineru-out.json").write_text('{"elements": [], "diagnostics": []}')
       (tmp_path / slug / "segments.json").write_text('{"boxes": []}')
       events_path = tmp_path / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
       actor = HumanActor(pseudonym="curator-x", level="other")
       entry_id = new_entry_id()
       append_event(events_path, Event(
           event_id=new_event_id(),
           timestamp_utc=now_utc_iso(),
           event_type="created",
           entry_id=entry_id,
           schema_version=1,
           payload={
               "action": "synthesised",
               "actor": actor.model_dump(mode="json"),
               "entry_data": {
                   "task_type": "retrieval",
                   "query": "Was ist X?",
                   "expected_chunk_ids": [],
                   "chunk_hashes": {},
                   "source_element": {
                       "document_id": slug,
                       "page_number": 1,
                       "element_id": "elem-1",
                       "element_type": "paragraph",
                   },
               },
           },
       ))
       return tmp_path, slug, entry_id


   def test_vote_endpoint_appends_event(seeded):
       root, slug, entry_id = seeded
       client = TestClient(create_app(data_root=root))
       r = client.post(
           f"/api/admin/docs/{slug}/questions/{entry_id}/vote",
           json={"action": "approved"},
       )
       assert r.status_code == 200
       body = r.json()
       assert body["event_type"] == "reviewed"
       assert body["payload"]["action"] == "approved"


   def test_questions_get_includes_vote_summary(seeded):
       root, slug, entry_id = seeded
       client = TestClient(create_app(data_root=root))
       client.post(f"/api/admin/docs/{slug}/questions/{entry_id}/vote", json={"action": "approved"})
       r = client.get(f"/api/admin/docs/{slug}/questions")
       assert r.status_code == 200
       body = r.json()
       q = next(iter(body.values()))[0]
       assert q["vote_summary"]["approved_count"] == 1
       assert q["vote_summary"]["rejected_count"] == 0
       assert q["vote_summary"]["my_vote"] == "approved"


   def test_toggle_off_via_revoked(seeded):
       root, slug, entry_id = seeded
       client = TestClient(create_app(data_root=root))
       client.post(f"/api/admin/docs/{slug}/questions/{entry_id}/vote", json={"action": "approved"})
       client.post(f"/api/admin/docs/{slug}/questions/{entry_id}/vote", json={"action": "revoked"})
       r = client.get(f"/api/admin/docs/{slug}/questions")
       q = next(iter(r.json().values()))[0]
       assert q["vote_summary"]["approved_count"] == 0
       assert q["vote_summary"]["my_vote"] is None
   ```

2. Extend `synthesise.py`.
   ```python
   # Add imports
   from local_pdf.auth.db import open_auth_db

   class VoteRequest(BaseModel):
       action: Literal["approved", "rejected", "revoked"]


   class VoteSummary(BaseModel):
       approved_count: int
       rejected_count: int
       my_vote: Literal["approved", "rejected"] | None = None


   class GeneratedQuestion(BaseModel):
       entry_id: str
       text: str
       box_id: str
       answer: str | None = None
       vote_summary: VoteSummary | None = None


   def _read_user_level(request: Request, pseudonym: str) -> str:
       """Read users.level by pseudonym from the auth DB; default 'other'.

       Uses ``cfg.data_root`` (the RAW base root) rather than ``_tr(request)``
       because the auth DB always sits at ``{data_root}/_meta/auth.db`` —
       tenant subdirs never carry their own auth DB. Matches the pattern
       used throughout ``admin/auth_mgmt.py``.
       """
       cfg = request.app.state.config
       try:
           with open_auth_db(cfg.data_root) as conn:
               row = conn.execute(
                   "SELECT level FROM users WHERE pseudonym = ?", (pseudonym,)
               ).fetchone()
               return row["level"] if row else "other"
       except sqlite3.OperationalError:
           # First-boot / fresh DB without ensure_schema yet → no users table.
           return "other"


   def _admin_actor_with_level(request: Request) -> HumanActor:
       ident = getattr(request.state, "identity", None)
       pseudonym = getattr(ident, "pseudonym", None) or getattr(ident, "name", None) or "admin"
       level = _read_user_level(request, pseudonym)
       return HumanActor(pseudonym=pseudonym, level=level)  # type: ignore[arg-type]


   def _collapse_votes_for_entries(
       events: list[Event],
       requesting_pseudonym: str | None,
   ) -> dict[str, VoteSummary]:
       latest: dict[tuple[str, str], tuple[str, str]] = {}
       for ev in events:
           if ev.event_type != "reviewed":
               continue
           action = ev.payload.get("action")
           if action not in {"approved", "rejected", "revoked"}:
               continue
           actor = ev.payload.get("actor") or {}
           pseudo = actor.get("pseudonym")
           if not pseudo:
               continue
           key = (ev.entry_id, pseudo)
           prev = latest.get(key)
           if prev is None or ev.timestamp_utc >= prev[1]:
               latest[key] = (action, ev.timestamp_utc)
       per_entry: dict[str, VoteSummary] = {}
       for (entry_id, pseudo), (action, _ts) in latest.items():
           summary = per_entry.setdefault(entry_id, VoteSummary(approved_count=0, rejected_count=0))
           if action == "approved":
               summary = summary.model_copy(update={"approved_count": summary.approved_count + 1})
           elif action == "rejected":
               summary = summary.model_copy(update={"rejected_count": summary.rejected_count + 1})
           # revoked → no count contribution
           if requesting_pseudonym and pseudo == requesting_pseudonym and action in {"approved", "rejected"}:
               summary = summary.model_copy(update={"my_vote": action})  # type: ignore[arg-type]
           per_entry[entry_id] = summary
       return per_entry


   @router.post("/api/admin/docs/{slug}/questions/{question_id}/vote")
   async def vote_question(
       slug: str,
       question_id: str,
       body: VoteRequest,
       request: Request,
   ) -> dict:
       # URL param ``question_id`` matches the existing PATCH/DELETE handlers
       # at lines 560 / 627. Internally this is the goldens ``entry_id``.
       data_root = _tr(request)
       if not doc_dir(data_root, slug).exists():
           raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
       events_path = _events_path(data_root, slug)
       actor = _admin_actor_with_level(request)
       ev = Event(
           event_id=new_event_id(),
           timestamp_utc=now_utc_iso(),
           event_type="reviewed",
           entry_id=question_id,
           schema_version=1,
           payload={"action": body.action, "actor": actor.model_dump(mode="json"), "notes": None},
       )
       append_events(events_path, [ev])
       return ev.model_dump(mode="json")


   # Update the existing list_questions handler to attach vote_summary.
   @router.get("/api/admin/docs/{slug}/questions")
   async def list_questions(slug: str, request: Request) -> dict[str, list[dict]]:
       data_root = _tr(request)
       if not doc_dir(data_root, slug).exists():
           raise HTTPException(status_code=404, detail=f"doc not found: {slug}")
       events_path = _events_path(data_root, slug)
       events = read_events(events_path) if events_path.exists() else []
       ident = getattr(request.state, "identity", None)
       requesting_pseudonym = getattr(ident, "pseudonym", None) or getattr(ident, "name", None)
       vote_summaries = _collapse_votes_for_entries(events, requesting_pseudonym)
       questions = _list_questions(data_root, slug)
       by_box: dict[str, list[dict]] = {}
       for q in questions:
           summary = vote_summaries.get(q.entry_id, VoteSummary(approved_count=0, rejected_count=0))
           dumped = q.model_dump(mode="json")
           dumped["vote_summary"] = summary.model_dump(mode="json")
           by_box.setdefault(q.box_id, []).append(dumped)
       return by_box
   ```

3. Run.
   ```bash
   cd features/pipelines/local-pdf && uv run pytest tests/api/admin/test_vote_endpoint.py -v
   ```

4. Commit.
   ```bash
   git add features/pipelines/local-pdf/src/local_pdf/api/routers/admin/synthesise.py features/pipelines/local-pdf/tests/api/admin/test_vote_endpoint.py
   git commit -m "feat(voting): vote POST endpoint and vote_summary on /questions GET"
   ```

---

## Task 14: Frontend voting hooks and QuestionList UI

**Files**:
- Modify: `frontend/src/admin/hooks/useSynthesise.ts`
- Modify: `frontend/src/admin/components/QuestionList.tsx`
- Modify (caller): `frontend/src/admin/routes/Synthesise.tsx`
- Create: `frontend/src/admin/components/__tests__/QuestionList.vote.test.tsx`

**Steps**:

1. Extend `useSynthesise.ts` with the vote_summary type and mutation hook.
   ```ts
   // Extend Question interface near the top
   export interface VoteSummary {
     approved_count: number;
     rejected_count: number;
     my_vote: "approved" | "rejected" | null;
   }

   export interface Question {
     entry_id: string;
     text: string;
     box_id: string;
     answer?: string | null;
     vote_summary?: VoteSummary;
   }

   // Add at end of file
   export function useVoteQuestion(slug: string, token: string) {
     const qc = useQueryClient();
     return useMutation({
       mutationFn: async (params: { entryId: string; action: "approved" | "rejected" | "revoked" }) => {
         const r = await fetchOk(
           `${apiBase()}/api/admin/docs/${encodeURIComponent(slug)}/questions/${encodeURIComponent(params.entryId)}/vote`,
           {
             method: "POST",
             headers: { "Content-Type": "application/json" },
             body: JSON.stringify({ action: params.action }),
           },
           token,
         );
         return r.json();
       },
       onSuccess: () => {
         qc.invalidateQueries({ queryKey: ["questions", slug] });
         qc.invalidateQueries({ queryKey: ["stats", "synthese", slug] });
       },
     });
   }
   ```

2. Extend `QuestionList.tsx`.
   ```tsx
   // Imports
   import { CheckCircle2, Edit3, Trash2, XCircle } from "lucide-react";  // CheckCircle2 + XCircle from lucide-react, others stay

   // Extend Props
   interface Props {
     questions: Question[];
     onRefine: (entryId: string, newText: string) => Promise<void> | void;
     onDeprecate: (entryId: string) => Promise<void> | void;
     onEditAnswer?: (entryId: string, newText: string) => Promise<void> | void;
     onVote?: (entryId: string, action: "approved" | "rejected" | "revoked") => Promise<void> | void;
     disabled?: boolean;
   }

   // Inside the map, compute stripe + visibility:
   const my = q.vote_summary?.my_vote ?? null;
   const stripeClass =
     my === "approved" ? "border-l-emerald-500"
     : my === "rejected" ? "border-l-red-500"
     : "border-l-transparent";

   // Replace the <li> className:
   <li
     key={q.entry_id}
     className={`rounded border border-slate-200 bg-white p-2 flex flex-col gap-1 border-l-[3px] ${stripeClass}`}
     data-testid={`question-${q.entry_id}`}
   >

   // Inside the existing footer-toolbar div, after the Trash2 button:
   {onVote && (
     <>
       <button
         type="button"
         title="Einverstanden"
         aria-label="Einverstanden"
         className={`p-1 rounded ${my === "approved" ? "text-emerald-700 bg-emerald-50" : "text-emerald-600 hover:bg-emerald-50"} disabled:opacity-40`}
         disabled={disabled}
         onClick={() => void onVote(q.entry_id, my === "approved" ? "revoked" : "approved")}
       >
         <CheckCircle2 size={14} aria-hidden="true" />
       </button>
       <button
         type="button"
         title="Disqualifizieren"
         aria-label="Disqualifizieren"
         className={`p-1 rounded ${my === "rejected" ? "text-red-700 bg-red-50" : "text-red-600 hover:bg-red-50"} disabled:opacity-40`}
         disabled={disabled}
         onClick={() => void onVote(q.entry_id, my === "rejected" ? "revoked" : "rejected")}
       >
         <XCircle size={14} aria-hidden="true" />
       </button>
     </>
   )}

   // Anti-anchoring count display — render only when my != null:
   {my != null && q.vote_summary && (
     <div className="text-[11px] text-slate-500 mt-1 text-right">
       {q.vote_summary.approved_count} ✓ · {q.vote_summary.rejected_count} ✗
     </div>
   )}
   ```

3. Wire the hook in `Synthesise.tsx` route — pass `onVote={(id, action) => voteMutation.mutateAsync({ entryId: id, action })}` to the `<QuestionList>`. The exact location follows the existing pattern used for `onRefine` / `onDeprecate`.

4. Test the toggle UX.
   ```tsx
   // frontend/src/admin/components/__tests__/QuestionList.vote.test.tsx
   import { render, screen, fireEvent } from "@testing-library/react";
   import { describe, expect, it, vi } from "vitest";

   import { QuestionList } from "../QuestionList";

   const baseQ = {
     entry_id: "q1",
     text: "Was ist X?",
     box_id: "b1",
     answer: null,
   } as const;

   describe("QuestionList vote UI", () => {
     it("does not render counts before user votes", () => {
       render(
         <QuestionList
           questions={[{ ...baseQ, vote_summary: { approved_count: 3, rejected_count: 1, my_vote: null } }]}
           onRefine={vi.fn()}
           onDeprecate={vi.fn()}
           onVote={vi.fn()}
         />
       );
       expect(screen.queryByText(/3 ✓/)).toBeNull();
     });

     it("renders counts and stripe once user votes approved", () => {
       const { container } = render(
         <QuestionList
           questions={[{ ...baseQ, vote_summary: { approved_count: 3, rejected_count: 1, my_vote: "approved" } }]}
           onRefine={vi.fn()}
           onDeprecate={vi.fn()}
           onVote={vi.fn()}
         />
       );
       expect(screen.getByText(/3 ✓ · 1 ✗/)).toBeInTheDocument();
       expect(container.querySelector(".border-l-emerald-500")).not.toBeNull();
     });

     it("clicking the active approve button toggles to revoked", () => {
       const onVote = vi.fn();
       render(
         <QuestionList
           questions={[{ ...baseQ, vote_summary: { approved_count: 1, rejected_count: 0, my_vote: "approved" } }]}
           onRefine={vi.fn()}
           onDeprecate={vi.fn()}
           onVote={onVote}
         />
       );
       fireEvent.click(screen.getByLabelText("Einverstanden"));
       expect(onVote).toHaveBeenCalledWith("q1", "revoked");
     });

     it("clicking approve when no vote yet sends 'approved'", () => {
       const onVote = vi.fn();
       render(
         <QuestionList
           questions={[{ ...baseQ, vote_summary: { approved_count: 0, rejected_count: 0, my_vote: null } }]}
           onRefine={vi.fn()}
           onDeprecate={vi.fn()}
           onVote={onVote}
         />
       );
       fireEvent.click(screen.getByLabelText("Einverstanden"));
       expect(onVote).toHaveBeenCalledWith("q1", "approved");
     });
   });
   ```

5. Run.
   ```bash
   cd frontend && npm run test -- QuestionList.vote
   ```

6. Commit.
   ```bash
   git add frontend/src/admin/hooks/useSynthesise.ts frontend/src/admin/components/QuestionList.tsx frontend/src/admin/routes/Synthesise.tsx frontend/src/admin/components/__tests__/QuestionList.vote.test.tsx
   git commit -m "feat(voting): QuestionList vote buttons, stripe, anti-anchoring counts"
   ```

---

## Task 15: VoteDistributionBar chart (replace stub from Task 10)

**Files**:
- Modify: `frontend/src/admin/components/charts/VoteDistributionBar.tsx`
- Create: `frontend/src/admin/components/charts/__tests__/VoteDistributionBar.test.tsx`

**Steps**:

1. Implement.
   ```tsx
   // frontend/src/admin/components/charts/VoteDistributionBar.tsx
   import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from "recharts";
   import { motion } from "framer-motion";

   import { RechartsNavyTheme, useChartPalette } from "./RechartsNavyTheme";
   import type { VoteDistributionRow } from "../../hooks/useStatistics";
   import { T } from "../../styles/typography";

   interface Props {
     rows: VoteDistributionRow[];
   }

   function Inner({ rows }: Props): JSX.Element {
     const p = useChartPalette();
     return (
       <BarChart data={rows} layout="vertical" margin={{ left: 16, right: 16 }}>
         <CartesianGrid strokeDasharray="3 3" stroke={p.grid} />
         <XAxis type="number" stroke={p.text} />
         <YAxis dataKey="text_short" type="category" stroke={p.text} width={180} />
         <Tooltip contentStyle={{ background: p.bg, border: `1px solid ${p.grid}`, color: p.text }} />
         <Bar dataKey="approved" stackId="v" fill={p.success} />
         <Bar dataKey="rejected" stackId="v" fill={p.danger} />
       </BarChart>
     );
   }

   export function VoteDistributionBar({ rows }: Props): JSX.Element {
     if (rows.length === 0) {
       return (
         <div className="rounded bg-navy-800 p-4 text-navy-200">
           Noch keine Reviewer-Stimmen vorhanden.
         </div>
       );
     }
     return (
       <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.3 }}>
         <div className={`${T.heading} text-navy-200 mb-1`}>Stimmen pro Frage (Top 20)</div>
         <RechartsNavyTheme height={Math.max(rows.length * 28, 200)}>
           <Inner rows={rows} />
         </RechartsNavyTheme>
       </motion.div>
     );
   }
   ```

2. Test.
   ```tsx
   // frontend/src/admin/components/charts/__tests__/VoteDistributionBar.test.tsx
   import { render, screen } from "@testing-library/react";
   import { describe, expect, it } from "vitest";
   import { VoteDistributionBar } from "../VoteDistributionBar";

   describe("VoteDistributionBar", () => {
     it("shows empty-state when rows are empty", () => {
       render(<VoteDistributionBar rows={[]} />);
       expect(screen.getByText("Noch keine Reviewer-Stimmen vorhanden.")).toBeInTheDocument();
     });

     it("renders heading when rows are present", () => {
       render(
         <VoteDistributionBar
           rows={[{ entry_id: "q1", text_short: "Was ist X?", approved: 2, rejected: 1 }]}
         />
       );
       expect(screen.getByText(/Stimmen pro Frage/)).toBeInTheDocument();
     });
   });
   ```

3. Run.
   ```bash
   cd frontend && npm run test -- VoteDistributionBar
   ```

4. Commit.
   ```bash
   git add frontend/src/admin/components/charts/VoteDistributionBar.tsx frontend/src/admin/components/charts/__tests__/VoteDistributionBar.test.tsx
   git commit -m "feat(stats): replace VoteDistributionBar stub with stacked bar chart"
   ```

---

## Task 16: End-to-end smoke pass

**Files**:
- No new files unless a regression is found.

**Steps**:

1. Run the full backend test suite.
   ```bash
   cd features/pipelines/local-pdf && uv run pytest -x --maxfail=3 -q
   ```
   Expected: all green, including the new statistics + vote tests.

2. Run the full goldens test suite.
   ```bash
   cd features/goldens && uv run pytest -x --maxfail=3 -q
   ```
   Expected: all green.

3. Run the full frontend test suite.
   ```bash
   cd frontend && npm run test
   ```
   Expected: all green.

4. Boot the API + SPA locally and execute the manual smoke flow.
   ```bash
   # Terminal A — backend
   cd features/pipelines/local-pdf && uv run uvicorn local_pdf.api.app:create_app --factory --reload --port 8000

   # Terminal B — frontend
   cd frontend && npm run dev
   ```
   Then in the browser, logged in as an admin/curator:
   - Open any doc → click the new `Statistik` tab.
   - Verify the three sub-section headings render and the gauges/counters animate in.
   - Go back to `Synthese`, click `Einverstanden` on a question — left stripe turns emerald, counts appear (`1 ✓ · 0 ✗`).
   - Click `Einverstanden` again — stripe and counts disappear (revoked).
   - Click `Disqualifizieren` — stripe turns red, counts re-appear.
   - Return to `Statistik` → confirm `Reviewer-Zustimmung` gauge updates and `Stimmen pro Frage` chart shows the question.

5. Run lint + typecheck.
   ```bash
   cd frontend && npm run lint && npm run build
   cd features/pipelines/local-pdf && uv run ruff check . && uv run pytest -q
   ```

6. No new commit unless a regression was found. If everything passes, the PR is ready for review.
