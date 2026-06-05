---
title: Cookie-curator empty-list gap + two auth/UI notes
date: 2026-06-05
status: captured (1 live gap documented, 2 design notes) — salvaged from the obsolete feat/ui-walkthrough branch before deletion
---

# Cookie-curator gap + auth/UI notes

Three findings surfaced while auditing the (now-obsolete) `feat/ui-walkthrough`
branch. Captured here so the branch can be deleted without losing them. Item 1
is a live gap; items 2–3 are design rationale worth recording.

## 1. Cookie-login curators see an empty doc list (live, backend half)

A tenant user with `role=curator` who logs in via the **cookie** flow gets an
empty "Meine Dokumente" list. Two reinforcing causes:

- **Frontend — FIXED in `main`.** The React-Query hooks for the curator doc /
  element lists (and Provenienz / Skills) were gated on `enabled: !!token`.
  Cookie sessions carry `token === ""` (falsy), so the queries never fired and
  the surface rendered *nothing* — not even the "Keine Dokumente zugewiesen."
  empty-state. The `!!token` conjunct has since been dropped everywhere
  (`useProvenienz.ts`, `useSkills.ts`, `curator/routes/Docs.tsx` + `DocPage.tsx`);
  genuine data guards (`!!slug`, `!!sessionId`, `!!skillId`) remain. *(No
  `enabled: …!!token` gate is left in `frontend/src`.)*

- **Backend — STILL LIVE.** `features/pipelines/local-pdf/src/local_pdf/api/routers/curate/docs.py`
  resolves the caller's assignments by matching the legacy curators-JSON id:

  ```python
  me = next((c for c in cf.curators if c.id == ident.curator_id), None)  # docs.py:21
  ```
  …and the same match in `_curator_can_see` (docs.py:37). For a **cookie**
  session `ident.curator_id is None` (the identity carries `user_id` +
  `pseudonym`, not a curators-JSON id — see `auth.py:lookup_session_cookie`),
  so `me is None` → `list_assigned_docs` returns `[]` and `get_assigned_doc`
  404s. Only **legacy X-Auth-Token** curators (real token → `curator_id`) work
  end-to-end. (`curate/questions.py:59` shows the same seam: `curator_id =
  ident.curator_id or ""` attributes cookie-curator questions to `""`.)

  **Why not fixed here:** there is no data linking a tenant `user_id` to
  `assigned_slugs` — the assignment model lives entirely in `curators.json`,
  keyed by the legacy id. Bridging it (assign-by-`user_id`, or map tenant users
  into the curators model) is a schema/design decision, and curator identity is
  explicitly provisional pending the IT/DSGVO review. **Fix direction:** when
  that review lands, resolve assignments by `user_id` for cookie sessions (or
  give tenant-curators a stable curators-JSON id at user-create time), and add a
  seeded `open_for_curation` doc to the dev fixture so the flow is testable.

## 2. The login 401 is deliberately generic

`POST /api/auth/login` collapses every failure mode (unknown tenant, unknown
user, wrong password) into a single `401 "invalid credentials"`:

> Failure modes are deliberately collapsed into one 401 from the client's
> perspective so an attacker can't probe which usernames exist. The server log
> keeps the distinction for forensics. — `routers/auth.py` login docstring

Don't "improve" the client-facing error to name which field was wrong — that's
a username-enumeration oracle. The forensic detail stays server-side. (Rate-
limit lockout is the one distinguishable response: `429` + `locked_until`.)

## 3. "Diese Seite sperren" diverges between Extrahieren and Synthese

The same affordance persists differently in the two tabs:

- **Extrahieren** — server-backed. `usePageStatus` / `done_pages` sidecar
  (`/api/admin/docs/{slug}/pages/status`); the lock survives across browsers /
  machines and is the authoritative "abgeschlossen" state.
- **Synthese** — `localStorage` only. `loadApprovedPages` / `saveApprovedPages`
  (`admin/lib/currentPage.ts`, `approvedPages` Set); per-browser-profile, lost
  on a different machine or a storage clear.

Same label, same intent ("don't let auto-runs overwrite curated work"), but a
curator who locks a Synthese page on one machine sees it unlocked on another.
**Fix direction:** mirror the Synthese lock onto the server `PageStatus` sidecar
(as the Extrahieren path already does) so the two converge.
