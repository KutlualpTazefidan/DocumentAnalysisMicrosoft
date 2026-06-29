# Independent Workspace Tabs + Global File Selector — Design

**Date:** 2026-06-29
**Status:** Design — awaiting user review
**Branch:** `feat/agent-tab-deepagents-spike` (current working branch)

## Goal

Make the workflow tabs (Dateien, Extrahieren, Synthese, Vergleich, Provenienz,
Agent, Statistik) **top-level and independent** of the old document-first
navigation, driven by a **global file-selector dropdown** on the right of the
tab bar — and structured so **separate tabs can be built in parallel and
git-merged with no conflicts on shared files**.

## Scope

Two axes, both in scope (the user chose reading **(b)** — parallel code-dev):

1. **Runtime independence.** Tabs become top-level routes; a global file
   dropdown sets the active file (carried in the URL); a shared workspace shell
   renders the bar+dropdown once and shows a "pick a file" empty state for tabs
   that need one.
2. **Build-time modularity.** A feature-module registry with **auto-discovery**
   so adding/working a tab touches **zero shared files**.

**Frontend-only.** `useDocs`/upload/list/delete already exist; no backend, no
import-boundary exposure. (Richer "organize" — folders, grouping — is a
deferred slice that *would* touch backend; see Out of Scope.)

### Decisions locked with the user (2026-06-29)

- **Global active file** — one dropdown, one selected file shared across tabs
  (not a different file per tab).
- **Independent tabs** — a tab is usable on its own; you pick the file via the
  dropdown, not by entering through a document.
- **"Merge into one" = (b)** parallel code-dev → include the auto-discovery
  registry.
- **Left rail keeps** Kuratoren/Fachbereiche/Pipelines/Übersicht/Wissen; **drop
  "Dokumente"** (the Dateien tab replaces it).
- **Dateien = today's inbox** (upload/list/delete) as the file-agnostic first
  tab. Richer organize = later.
- Keep it light: **do not move/rewrite the existing big tab files**; descriptors
  wrap them in place.

## Background (current state)

- `DocStepTabs.tsx` already defines all 7 tabs, but is **rendered separately
  inside each of the 7 route pages** (extract.tsx:385, Synthesise.tsx:309,
  Comparison.tsx:341, Provenienz.tsx:79, Agent.tsx:113, Statistics.tsx:50,
  inbox.tsx:45). Each route reads the file via `useParams<{slug}>()` from the
  path `/admin/doc/:slug/<tab>`. There is **no global active-file state**.
- Routing: global routes (inbox, curators, tenants, pipelines, dashboard,
  knowledge, settings) + doc-scoped (`doc/:slug/{extract,synthesise,compare,
  provenienz,agent,statistics,curators}`) + legacy `/local-pdf/*`, `/docs/*`
  redirects. `AdminShell` renders the left `IconRail` (`ADMIN_NAV`) + `<Outlet/>`.
- File data layer: `useDocs(token)` → `GET /api/admin/docs` → `DocMeta[]`
  (`slug, filename, pages, status, last_touched_utc, box_count`); upload via
  `POST /api/admin/docs`. The dropdown reuses `useDocs` verbatim.
- Verified: the app uses `HashRouter`; `useSearchParams` already works under it
  (`auth/routes/Login.tsx:15`), so a `?file=` query param round-trips.

## Architecture

```
<AdminShell>                       (existing: BamHeader + left IconRail + Outlet)
  └─ <WorkspaceLayout>             (NEW layout route: tab bar + file dropdown + Outlet)
       routes derived from the registry:
       ├─ /admin/files       → TabRoute(Dateien)     requiresFile:false → inbox content
       ├─ /admin/extract     → TabRoute(Extrahieren)  requiresFile:true
       ├─ /admin/synthesise  → TabRoute(Synthese)     requiresFile:true
       ├─ /admin/compare     → TabRoute(Vergleich)    requiresFile:true
       ├─ /admin/provenienz  → TabRoute(Provenienz)   requiresFile:true
       ├─ /admin/agent       → TabRoute(Agent)        requiresFile:true
       └─ /admin/statistics  → TabRoute(Statistik)    requiresFile:true
  └─ other global routes (curators, tenants, pipelines, dashboard, knowledge, settings)
```

Active file is the `?file=<slug>` query param, shared by all tabs via
`useActiveFile()`. The dropdown writes it; `TabRoute` gates mounting on it.

## Components

### C1. `TabDescriptor` (the contract that makes parallel dev clean)

`admin/features/types.ts`:

```ts
import type { ComponentType } from "react";
import type { LucideIcon } from "lucide-react";  // icon VALUES still come from ../../shared/icons

export interface TabDescriptor {
  key: string;          // URL segment + identity, e.g. "extract"
  label: string;        // bar label, e.g. "Extrahieren"
  icon: LucideIcon;
  order: number;        // bar position (Dateien=0)
  requiresFile: boolean;// true → shell shows empty state until a file is picked
  Component: ComponentType;  // the tab UI; reads useActiveFile() when requiresFile
}
```

### C2. Feature modules + auto-discovery registry

- Each tab is a folder `admin/features/<key>/` exporting its descriptor as the
  default export of `tab.tsx`. New tabs put their whole UI here. The **existing
  six** descriptors are thin: `Component` points at the current route file
  (which is **not moved**), e.g. `admin/features/extract/tab.tsx`:

  ```tsx
  import { FileText } from "../../../shared/icons";
  import { Extract } from "../../routes/extract";
  import type { TabDescriptor } from "../types";
  export default {
    key: "extract", label: "Extrahieren", icon: FileText,
    order: 1, requiresFile: true, Component: Extract,
  } satisfies TabDescriptor;
  ```

- `admin/features/registry.ts` auto-collects them — **no shared file is edited
  to add a tab**:

  ```ts
  import type { TabDescriptor } from "./types";
  const mods = import.meta.glob("./*/tab.tsx", { eager: true });
  export const WORKSPACE_TABS: TabDescriptor[] = Object.values(mods)
    .map((m) => (m as { default: TabDescriptor }).default)
    .sort((a, b) => a.order - b.order);
  ```

  (`eager: true` so the array is available synchronously for route + bar
  construction. `vitest` resolves `import.meta.glob` natively.)

### C3. `useActiveFile()` — the global selector source of truth

`admin/hooks/useActiveFile.ts`:

```ts
import { useSearchParams } from "react-router-dom";
export function useActiveFile(): {
  file: string | null;
  setFile: (slug: string | null) => void;
} {
  const [params, setParams] = useSearchParams();
  const file = params.get("file");
  const setFile = (slug: string | null) => {
    setParams((p) => {
      const next = new URLSearchParams(p);
      if (slug) next.set("file", slug); else next.delete("file");
      return next;
    }, { replace: false });
  };
  return { file, setFile };
}
```

The file is preserved automatically when switching tabs because tab links keep
the current `?file=` (see C4). Existing tabs swap their `const { slug } =
useParams()` for `const { file } = useActiveFile()` (inside a `requiresFile`
tab, `file` is guaranteed non-null by the gate — see C5).

### C4. `WorkspaceLayout` — bar + dropdown, rendered once

`admin/components/WorkspaceLayout.tsx`: renders the tab bar from
`WORKSPACE_TABS` (active = `pathname.endsWith('/'+key)`), each tab link
preserving the current `?file=` query; on the right, the **file dropdown** (a
`<select>` over `useDocs(token)`, value = active `file`, onChange =
`setFile(slug)`), then `<Outlet/>`. Replaces the per-route bar renders.

### C5. `TabRoute` — shell-gated mount

`admin/components/TabRoute.tsx`: `requiresFile && !file` → a single
"Bitte wählen Sie oben rechts eine Datei." empty state; else `<descriptor.Component/>`.
This centralizes the empty state so each tab's internals can assume a file is
present.

### C6. Routing (App.tsx) — derived from the registry, edited once

```tsx
<Route path="/admin" element={<AdminShell />}>
  <Route element={<WorkspaceLayout />}>
    {WORKSPACE_TABS.map((d) => (
      <Route key={d.key} path={d.key} element={<TabRoute descriptor={d} />} />
    ))}
  </Route>
  {/* unchanged global routes */}
  <Route path="curators" element={<Curators />} />
  <Route path="curators/:id/activity" element={<CuratorActivity />} />
  <Route path="pipelines" element={<Pipelines />} />
  <Route path="dashboard" element={<Dashboard />} />
  <Route path="knowledge" element={<Knowledge />} />
  <Route path="tenants" element={<TenantsAdmin />} />
  <Route path="settings" element={<Settings />} />
  <Route path="doc/:slug/curators" element={<DocCurators />} />
  {/* index → files */}
  <Route index element={<Navigate to="files" replace />} />
</Route>
```

After this one-time setup, adding a tab never touches `App.tsx` again.

### C7. Migration / compatibility

- **Legacy redirects:** `/admin/doc/:slug/<tab>` → `/admin/<tab>?file=<slug>`
  for each of the 6 tabs (via a `RedirectWithSlug`-style element that maps the
  old path param to the new query param). `/admin/inbox` → `/admin/files`.
  Keep the existing `/local-pdf/*` and `/docs/*` redirects (retarget to the new
  forms).
- **`inbox.tsx` row link** (`→ /admin/doc/${slug}/extract`) becomes
  `→ /admin/extract?file=${slug}`.
- **`DocCurators`** (`doc/:slug/curators`) is not a workspace tab; it stays a
  doc-scoped route (linked from the Kuratoren area). Not orphaned.
- **`AdminShell.ADMIN_NAV`:** remove the "Dokumente" rail item (Dateien tab
  replaces it). Keep the rest.
- **Audit each per-route top bar before deleting it:** several routes wrap
  `<DocStepTabs>` in a `flex items-center` bar that may also hold tab-specific
  controls (buttons, status). Those controls move **into the tab's own body**
  (below the shared bar), not deleted. `DocStepTabs.tsx` is retired once all
  routes are converted.

## Data flow

1. User opens `/admin/files` (Dateien) → uploads / sees the doc list.
2. Picks a file (row action or the dropdown) → `?file=<slug>` set.
3. Clicks any tab → `/admin/<tab>?file=<slug>`; `TabRoute` sees a file → mounts
   the tab; the tab reads `useActiveFile().file`.
4. Switches file via the dropdown → same tab, new `?file=`; the tab re-queries.
5. Switches tab → `?file=` preserved; new tab mounts with the same file.

## Error handling / edge cases

- **No file + file-requiring tab** → empty state (C5), no broken data calls.
- **`?file=` points at a deleted/unknown slug** → tab's existing data hooks
  return their normal not-found/empty UI (unchanged); the dropdown shows no
  selection. Optional polish: the dropdown flags an unknown slug — deferred.
- **Direct deep link** `/admin/extract?file=x` works (URL is the source of
  truth).
- **Switching to a file-agnostic tab (Dateien)** keeps `?file=` in the URL but
  Dateien ignores it (so returning to a workflow tab keeps the selection).

## Testing strategy

- **`useActiveFile` (vitest):** render under `MemoryRouter initialEntries=['/admin/extract?file=a']`; assert `file==='a'`; `setFile('b')` updates the param; `setFile(null)` removes it.
- **Registry (vitest):** assert `WORKSPACE_TABS` is non-empty, sorted by `order`, Dateien first, and that each descriptor has the required fields. (Auto-discovery is exercised by the real folders.)
- **`TabRoute` (vitest):** `requiresFile:true` + no file → empty state; + file → renders the Component. `requiresFile:false` → always renders.
- **`WorkspaceLayout` (vitest + msw):** mock `GET /api/admin/docs`; assert the bar lists all tabs, the dropdown lists docs, selecting one sets `?file=`, and a tab link preserves `?file=`.
- **Per converted tab:** its existing tests keep passing after the
  `useParams→useActiveFile` swap (provide the file via `?file=` in the test
  router instead of a `:slug` path param).
- **Redirects (vitest):** `/admin/doc/x/extract` → `/admin/extract?file=x`.

## Sequencing (vertical slice first)

1. **Slice 1 (foundation + one tab):** `TabDescriptor`, `registry`,
   `useActiveFile`, `WorkspaceLayout` (bar + dropdown), `TabRoute`; registry
   routing in `App.tsx`; convert **Dateien** (inbox, `requiresFile:false`) **and
   one workflow tab** (e.g. **Statistik** — smallest, reads slug at
   Statistics.tsx:35) end-to-end; legacy redirect for that tab; drop "Dokumente"
   from the rail. Savepoint tag `pre-workspace-tabs` before, `workspace-tabs-v1`
   after. This proves the whole pattern.
2. **Slice 2..n:** mechanically convert the remaining tabs (Extrahieren,
   Synthese, Vergleich, Provenienz, Agent) one per task — each = add
   `features/<key>/tab.tsx`, swap `useParams→useActiveFile`, move tab-specific
   bar controls into the body, add the legacy redirect, retire that route's
   `DocStepTabs` render.
3. **Finalize:** retire `DocStepTabs.tsx`; confirm all redirects; savepoint.

## Out of scope (YAGNI)

Moving the big existing tab files into their feature folders (descriptors wrap
them in place); richer "organize" in Dateien (folders, drag-drop, grouping by
Fachbereich, rename) — a later, backend-touching slice; per-tab independent file
selection; an explicit "merge the features' results into one document" workflow
(that was reading (a), not chosen).

## Open decisions (for spec review)

- **D1 — First tab to convert.** Default: Statistik (smallest). Alternative:
  Agent (most recently built, already familiar).
- **D2 — Dateien path.** Default: `/admin/files` (uniform with other tabs),
  `/admin/inbox` redirects to it. Alternative: keep `/admin/inbox`.
- **D3 — Dropdown content.** Default: list `filename` (value=`slug`) from
  `useDocs`, no grouping. Alternative: group by Fachbereich/status (defer).
