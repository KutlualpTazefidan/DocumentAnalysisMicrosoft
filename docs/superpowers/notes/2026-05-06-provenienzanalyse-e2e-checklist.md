# Provenienzanalyse — End-to-End Smoke Checklist

Manual walk-through to confirm the full Provenienz tab works against a real
backend + real LLM. Lives in `notes/` (not the phase index) because it's a
test recipe, not a status doc.

## Prerequisites

- Backend running (`uv run uvicorn local_pdf.api.app:create_app --factory --reload`)
- vLLM available (or `LLM_BACKEND=ollama_local` with ollama running)
- Frontend dev server (`cd frontend && npm run dev`)
- `GOLDENS_API_TOKEN` set in both processes; `LOCAL_PDF_DATA_ROOT` pointing at a
  real persistent directory (NOT `/tmp/...`)
- A PDF already extracted via the Extract tab so `mineru.json` exists with
  several elements

## Walk-through

1. Open `http://localhost:5173/admin/inbox`, click a slug.
2. In the doc page header, click **Provenienz**. Tab activates; left rail shows
   "Keine Sitzungen für dieses Dokument."
3. Click **+ Neu**, type a real `box_id` from the doc (e.g. `p1-b0`), press
   **Anlegen**.
4. New session selected. Canvas renders one `chunk` node centered, no edges.
5. Click the chunk node → side panel opens on the right.
   - Header: kind=chunk, node_id, actor=human, created_at.
   - Body: chunk text preview.
6. Click **Aussagen extrahieren**. Backend hits the LLM. Within a few seconds:
   - A new `action_proposal` node appears below the chunk, connected by
     `extracts-from`.
   - Side panel switches to the proposal automatically.
   - Proposal shows `step_kind = extract_claims`, recommended-claims label,
     guidance_consulted badges if any reasons/approaches exist.
7. Click **Empfehlung übernehmen** → **Entscheiden**.
   - A `decision` node appears, plus N `claim` nodes (one per recommended
     claim) connected to the chunk via `extracts-from` + `decided-by`.
   - Side panel switches to the decision node.
8. Click any newly-spawned claim node.
   - Panel shows the claim text + two buttons.
9. Click **Aufgabe formulieren**.
   - New `action_proposal` (step_kind=formulate_task) appears anchored to
     the claim.
   - Take recommended → `task` node spawns with `query` payload.
10. Click the new task node → **Suchen** (top_k=5).
    - `action_proposal` (step_kind=search) appears with N hits as recommended.
    - Take recommended → N `search_result` nodes spawn, each connected to the
      task via `candidates-for`.
11. Click any search_result node.
    - Panel shows `box_id`, score, candidate text.
    - Claim picker auto-selects the upstream claim.
12. Click **Bewerten**.
    - `action_proposal` (step_kind=evaluate) appears with verdict +
      confidence + reasoning.
    - Take recommended → `evaluation` node spawns connected via `evaluates`.
13. Back on the claim, click **Stopp vorschlagen** OR on the evaluation
    panel for a likely-source verdict.
    - `action_proposal` (step_kind=propose_stop) appears.
    - Take recommended → `stop_proposal` node spawns, session meta flips to
      `closed` (lock icon in left rail).
14. Reload the page (`F5`).
    - Same session is selected (or click it again from the rail).
    - Canvas re-renders identically — every node + edge persisted in
      `events.jsonl`.

## Override-and-learn

15. Repeat steps 5-7 on a fresh chunk, but choose **Eigene Eingabe** in the
    proposal panel. Provide:
    - Override text: a different list of claims
    - Reason: e.g. "Heuristik nimmt zu viel Boilerplate"
16. Click **Entscheiden** → claim nodes spawn from the override text.
17. Inspect `${LOCAL_PDF_DATA_ROOT}/provenienz/reasons.jsonl` — one new line
    matching the override.
18. Repeat step 5 on yet another chunk. Without any code change, the LLM
    system prompt now contains the prior override as an in-context example.
    The new proposal's `guidance_consulted` includes a `reason` ref pointing
    at the corpus entry from step 17.

## Approach-library smoke

19. `curl -X POST http://localhost:8000/api/admin/provenienz/approaches \
       -H 'X-Auth-Token: $GOLDENS_API_TOKEN' \
       -d '{"name":"thorough","step_kinds":["extract_claims"],
            "extra_system":"Sei besonders gründlich bei Zahlen und Einheiten."}'`
20. Note the returned `approach_id`. Pin it to the current session via
    `POST /api/admin/provenienz/sessions/<sid>/pin-approach`.
21. Run extract-claims again. The `guidance_consulted` on the new proposal
    includes an `approach` ref. Disable the approach via PATCH and confirm
    the next call no longer references it.

## Pass criteria

- All 21 steps complete without 5xx errors.
- Reload survives at every step.
- Override + reason produces an in-context example on the very next call to
  the same step_kind.
- Pinned-approach text is visible in `_FakeClient.captured_system` if you
  swap to a logging LLM client; otherwise inferable from the recorded
  `guidance_consulted` ref.

## Known limits (v1)

- No chunk picker — root_chunk_id is typed as text. Chunk picker is a
  follow-up if it sees use.
- No approach CRUD UI — curl-only for now.
- `provider` arg in step routes is plumbed-through but unused; per-step
  vLLM/Azure routing waits for a real cost-driven need.
- Override on `/search` is intentionally rejected (400) — manual-hits flow
  not in v1.
