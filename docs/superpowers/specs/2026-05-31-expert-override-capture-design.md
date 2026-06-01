# Expert-Override Capture für plan_proposal

> **For agentic workers:** Dieser Spec wurde via multi-agent Pipeline (4× brainstorm-lens
> → synthesis → 2× plan agents → advisor) erzeugt. Spec-Status: **Approved by user
> 2026-05-31, ready for implementation**. Branch: `feat/expert-override-capture`.

**Goal (one sentence):** Wenn der LLM-Planer in Provenienz einen Step vorschlägt
(`plan_proposal`), soll der Admin die Korrektur strukturiert erfassen können —
auch wenn die richtige Methode noch nicht implementiert ist — damit der Agent
mittelfristig den Experten-Flow repliziert.

**Architektur in drei Sätzen:** `POST /sessions/{id}/decide` wird kind-widened
und akzeptiert auch `plan_proposal` mit neuem optionalen `expert_correction`-Block.
Persistenz erfolgt als `expert_correction`-Node (Audit), NOTE-Skill (Korpus für
existierende Reason-Injection) und — wenn der gewählte Step nicht in der Registry
ist — zusätzlich als `capability_request`-Node (Human-Aktor). UI: der bestehende
Verwerfen-Button im `PlanProposalPanel` morpht beim ersten Klick in eine
Inline-Form (Step-Combobox + Reason-Textarea + Submit).

**Tech Stack:** Python 3.12 (FastAPI, Pydantic v2), TypeScript/React + react-query
(existing). Storage: JSONL append-only (existing pattern).

---

## 1. Motivation & Anti-Goals

### Was treibt diesen Spec

Heute landet jede Override-Entscheidung auf `action_proposal`-Knoten via
`/decide`, schreibt eine NOTE-Skill ins Korpus und wird vom Planer beim nächsten
Lauf via `_gather_reason_guidance` als „Frühere Korrekturen"-Block in den Prompt
injiziert. Die Pipeline existiert — sie funktioniert nur **nicht für
`plan_proposal`**: das `/decide`-Guard wirft 400 (`kind != "action_proposal"`).

Konsequenz: wenn der LLM einen Step vorschlägt, kann der Admin heute nur:
- **Anwenden** (= Step ausführen wie vorgeschlagen)
- **Verwerfen** (= Tile löschen, keine Kapitalisierung)
- frei `considered_alternatives` lesen, aber nicht auswählen (Read-only-Anzeige)

Es gibt also genau drei verlorene Lerngelegenheiten:
1. „Lieber Step X statt Y" mit existierendem Step
2. „Lieber Methode X — die's noch gar nicht gibt"
3. „Der Vorschlag ist falsch — hier ist warum" (nur Reason, kein Alternativ-Step)

### Vision: Replicate the expert flow

Goal-of-goals: wenn der Experte einen Override macht, soll der Agent bei der
nächsten ähnlichen Anker-Lage spontan **den Experten-Pfad** wählen. Heutige
NOTE-Skill-Injection schiebt das in die richtige Richtung — wir füttern sie
jetzt mit strukturierten Daten statt rohem free-text.

### Dual Purpose — zwei Loops, zwei Konsumenten

Overrides bedienen ZWEI distinct Downstream-Loops mit verschiedenen Zeitskalen
und verschiedenen Konsumenten. Phase 1 hat beide implementiert, aber Purpose 2
als Side-Effect einer Override-Branch behandelt; die Phasen-Roadmap macht den
Split explizit:

| Purpose | Zeitskala | Mechanismus | Konsument |
|---|---|---|---|
| **1. Agent lernen lassen** (Korrekturen-Korpus) | Nächster Run | NOTE-Skill → `_gather_reason_guidance` → Planer-Prompt | Der Agent selbst |
| **2. Capability-Gap markieren** (Build-this-Tool-Wunschliste) | Tage / Wochen / Monate | `capability_request`-Node (Phase 1, Human-Aktor) → Phase 3: gesplittet als `expert_method_request` | Zukünftiger Capability-Wishlist-Workflow (Dev-Review-Board / Digest / Auto-Mint / Sub-Agent) |

**Konsequenz für die Phasen-Reihenfolge:**
- Phase 1 + Phase 2 schärfen Purpose 1 (Korpus-Aufbau, Anchor-Shape-Retrieval,
  Feedback-Loop-Sichtbarkeit, Post-hoc-Capture).
- Phase 3 (Sibling-Node-Kinds) macht Purpose 2 unblocked: cleanly-typed
  `expert_method_request`-Nodes statt einer polymorphen `expert_correction` mit
  `is_unimplemented`-Flag im Payload. Erst danach lohnt sich der
  Wishlist-Workflow im UI / als Digest / als Auto-Mint.
- Phase 4+ (Replikation) baut auf dem typed-Mark auf — Auto-Mint zählt
  `expert_method_request`-Frequenz pro `intended_step`, nicht Flag-Filter über
  alle `expert_correction`-Records.

### Anti-Goals (Phase 1)

- **Kein neues Endpoint** — wir widen `/decide`, ergänzen kein paralleles
  `/correct` oder `/overrides`. (Vergleich Backend-Brainstorm #2/#5).
- **Keine separate `overrides.jsonl`** — NOTE-Skill-Korpus reuse mit
  `correction_origin="plan_proposal"`-Marker als Migrations-Anker für Phase 2.
- **Kein Auto-Promote zu `PROMPT_OVERLAY`/`REACTIVE`-Skills** — bleibt Phase 3.
- **Keine anchor-shape Retrieval** — Phase 2.
- **Kein Stream-Phase-Event** „berücksichtigt deine frühere Korrektur" —
  Phase 2.
- **Kein UI-Filter Agent-vs-Human auf Wünsche-Tab** — Phase 2 (Daten landen
  korrekt getaggt, UI kommt später).

### Was wir aus den 4 Brainstorm-Linsen mitnehmen

- **UX:** Inline-Form auf Verwerfen (UX #1) — kleine UI-Änderung, hohe
  Capture-Rate.
- **Data Model:** strukturierte Capture statt free-text. Heute gibt's nur
  `DecideRequest.reason: str`; wir ersetzen das durch ein typed `expert_correction`-Block.
- **Backend:** kind-widen `/decide` (Backend #1) — minimal, backward-compat,
  null neue Endpoints.
- **Feedback-Loop:** bestehende `_gather_reason_guidance`-Pipeline pickt
  NOTE-Skills schon auf. Korpus-Reuse mit Marker-Field für Phase-2-Migration.

---

## 2. Scope

### In Scope (Phase 1)

| Komponente | Anforderung |
|---|---|
| API | `POST /sessions/{id}/decide` widen — akzeptiert auch `plan_proposal` |
| Schema | `ExpertCorrection` Pydantic-Modell + `DecideRequest.expert_correction` Field |
| Storage | Neuer Node-Kind `expert_correction` (Audit), Edge-Kind `overrides`, NOTE-Skill-Write mit Marker, bedingt `capability_request`-Node (Human-Aktor) |
| Aggregator | `/capability-requests` Items-Dict surface `actor`-Field |
| UI | `PlanProposalPanel.tsx` Verwerfen-Button morph → Inline-Form |
| Canvas | `expert_correction` Tile als Geschwister-Node am `plan_proposal`, dotted `stattdessen`-Edge |
| Tests | 7 Backend + 8 Frontend + 1 Walkthrough-Recording |

### Out of Scope (Phase 1, in Phase 2/3 erwartet)

- Anchor-shape Retrieval in `_gather_reason_guidance` (Phase 2)
- Post-hoc Korrektur-Schublade auch nach Akzeptieren (Phase 2)
- Stream-Phase-Event `prior_corrections` im `/next-step/stream` (Phase 2)
- Auto-mint `PROMPT_OVERLAY`-Skill ab N≥3 agreeing Overrides (Phase 3)
- Explicit „Promote to rule" → `REACTIVE`-Skill mit `TriggerConditions` (Phase 3)
- Separater `overrides.jsonl` Storage (Phase 3, falls Korpus-Split nötig)

---

## 3. Data Model

### 3.1 `ExpertCorrection` (Pydantic, new in `schemas.py`)

```python
class ExpertCorrection(BaseModel):
    model_config = ConfigDict(frozen=True)
    intended_step: str = Field(min_length=1, max_length=120)
    """The step the expert would do instead. May or may not be in _KNOWN_STEPS."""
    intended_args: dict[str, Any] = Field(default_factory=dict)
    """Optional args for the chosen step. Ignored when intended_step is unimplemented."""
    reason: str = Field(min_length=1, max_length=2000)
    """Why this is better. Required."""
```

### 3.2 `DecideRequest` widening (`provenienz.py:5548`)

```python
class DecideRequest(BaseModel):
    proposal_node_id: str
    accepted: Literal["recommended", "alt", "override"] | None = None  # widened: was required
    alt_index: int | None = None
    reason: str | None = None
    override: str | None = None
    expert_correction: ExpertCorrection | None = None  # NEW

    @model_validator(mode="after")
    def _shape_check(self):
        # Soft shape: action_proposal callers send accepted; plan_proposal
        # callers send expert_correction. Hard semantic check happens in route
        # because it depends on the resolved proposal kind.
        return self
```

**Backward-compat:** request-direction widening. Existing action_proposal
callers always send `accepted` → keep working. Plan-Branch akzeptiert
`accepted=None` mit gesetztem `expert_correction`.

### 3.3 Storage: neuer Node-Kind `expert_correction`

```python
# Constructor (called from _record_plan_expert_correction)
Node(
    node_id=ULID(),
    session_id=...,
    kind="expert_correction",
    payload={
        "intended_step": ec.intended_step,
        "intended_args": ec.intended_args,
        "reason": ec.reason,
        "target_proposal_node_id": proposal.node_id,
        "target_step_kind": proposal.payload["name"],   # e.g. "extract_claims"
        "is_unimplemented": ec.intended_step not in _KNOWN_STEPS,
    },
    actor="human",   # TOP-LEVEL field on Node, NOT in payload (storage.py:31)
)
```

**Kritischer Punkt aus Advisor-Pass:** `Node.actor` ist Top-Level
(`@dataclass(frozen=True)` in `storage.py:31`), nicht Sub-Field im payload.
Aggregator-Reads müssen `node.actor` lesen, nicht `payload.get("actor")`.

### 3.4 Storage: bestehende NOTE-Skill mit neuem Marker

```python
append_reason(
    cfg=cfg,
    session_id=session_id,
    step_kind=proposal.payload["name"],   # e.g. "extract_claims" — NOT "plan_override" meta-key
    proposal_summary=_synth_proposal_summary(proposal),
    override_summary=ec.intended_step[:200],
    reason=ec.reason,
    extra_payload={
        "correction_origin": "plan_proposal",   # NEW marker for Phase-2 migration
    },
)
```

**Begründung step_kind-Wahl (Advisor-Resolution):** matched bestehende
Action-Proposal-Pipeline 1:1. Surface die Korrektur in **zukünftigen
plan_proposals desselben Step-Kinds** = direkter Beitrag zu „expert flow
replizieren". Meta-Key `"plan_override"` wäre breiter aber schwächeres Signal
und bricht Symmetrie mit existierender `_gather_reason_guidance`.

### 3.5 Storage: bedingt `capability_request`-Node

Wenn `ec.intended_step not in _KNOWN_STEPS`:

```python
Node(
    node_id=ULID(),
    session_id=...,
    kind="capability_request",
    payload={
        "name": ec.intended_step,
        "description": ec.reason[:400],
        "target_expert_correction_node_id": ec_node.node_id,
        # NB: no "source" field in payload — see actor handling above
    },
    actor="human",   # distinguishes from agent-emitted CRs (actor="agent")
)
```

### 3.6 Edge

```python
Edge(
    from_node=ec_node.node_id,
    to_node=proposal.node_id,
    kind="overrides",          # NEW edge kind
    reason="stattdessen",      # label rendered in canvas
    actor="human",
)
```

---

## 4. API Contract

### 4.1 `POST /sessions/{session_id}/decide` (widened)

**Request, plan_proposal branch:**

```json
{
  "proposal_node_id": "01K...",
  "expert_correction": {
    "intended_step": "investigate_table",
    "intended_args": {"target_columns": ["col_a"]},
    "reason": "Chunk ist eine Tabelle — extract_claims wäre auf Spalten-Header verwirrt."
  }
}
```

`accepted` field MUST be omitted/null on plan_proposal branch.
`expert_correction` MUST be present.

**Response, plan_proposal branch:**

```json
{
  "decision": { /* decision node */ },
  "expert_correction": { /* the new expert_correction node */ },
  "capability_request": { /* the new CR node, OR null */ },
  "edges": [ { /* new "overrides" edge */ } ]
}
```

**Request, action_proposal branch (unchanged):**

```json
{
  "proposal_node_id": "01K...",
  "accepted": "recommended" | "alt" | "override",
  "alt_index": 0,           // when accepted="alt"
  "reason": "...",          // optional free-text
  "override": "..."         // when accepted="override"
}
```

Response shape unchanged for action_proposal.

### 4.2 Semantic Validation

| Bedingung | HTTP |
|---|---|
| `proposal.kind not in {action_proposal, plan_proposal}` | 400 `"unsupported proposal kind"` |
| `kind=action_proposal` + `accepted=None` | 400 (preserves today's contract) |
| `kind=plan_proposal` + `expert_correction=None` | 400 `"plan_proposal /decide requires expert_correction"` |
| `kind=plan_proposal` + `accepted not None` | 400 `"accepted is forbidden for plan_proposal"` |

### 4.3 `/capability-requests` aggregator extension

Items-dict additive:

```python
items.append({
    ...,
    "actor": n.actor,  # top-level "agent" | "human" — see 3.3
})
```

Bestehende Konsumenten sehen ein extra Field; keine Breaking Change.

---

## 5. UI Behavior

### 5.1 PlanProposalPanel Verwerfen-Morph

**State machine:**

```
idle (default) ──click Verwerfen──> form
form ──click "Doch löschen"──> idle + delete node (existing useDeleteNode)
form ──Esc──> idle (no mutation)
form ──Submit (valid)──> closing + POST /decide
```

**Form-Felder (oben → unten):**

1. **Combobox** „Stattdessen…" — typeahead über `valid_steps_per_anchor[anchorKind]`
   und alle `_KNOWN_STEPS`. Free-text Enter akzeptiert beliebigen String.
   Lucide `Search`-Icon. Wenn String nicht in `_KNOWN_STEPS` → kleiner
   Amber-Hint „Neuer Skill — wird als Capability-Wunsch erfasst".
2. **Textarea** „Warum?" — `rows=1`, auto-grow. Required.
3. **Submit-Button** — primary tone, disabled bis `reason.trim()` ≠ "".
4. **„Doch löschen"** — Text-Link, ruft existing `useDeleteNode`.

### 5.2 Combobox-Source

`useAgentInfo()` (existing oder neu — grep zuerst, `apiBase + "/api/admin/provenienz/agent-info"`,
react-query mit 5-min `staleTime` da Daten statisch per Deploy). Liefert
`valid_steps_per_anchor` (= Single Source of Truth für `_KNOWN_STEPS` im
Frontend). `STEP_LABEL` als Anzeige-Mapping bleibt; was nicht im Map ist wird
roh dargestellt.

### 5.3 Visible artifact nach Submit

- `plan_proposal` Tile **bleibt sichtbar** (kein tombstone — Audit-Trail).
- Neues `expert_correction` Tile erscheint als Geschwister, verbunden via
  dashed Edge mit Label „stattdessen".
- Submit-Button geht zurück auf `idle`-State, Form kollabiert.
- Bei Submit-Error: Toast, Form bleibt offen mit eingegebenen Werten.

### 5.4 ExpertCorrectionPanel (right inspector, read-only Phase 1)

Bei Klick auf `expert_correction`-Tile zeigt SidePanel:
- Header: „Korrektur" + `target_step_kind` (z.B. „extract_claims" als Pill)
- Block 1: `intended_step` (mono, mit „nicht implementiert"-Badge wenn
  `is_unimplemented`)
- Block 2: `intended_args` (falls non-empty, als `<pre>`)
- Block 3: Reason-Text
- Footer: Link zum Source-Plan-Proposal („zum ursprünglichen Vorschlag"),
  falls `is_unimplemented` zusätzlich „Auch als Wunsch hinterlegt" + Link
  zum Wünsche-Tab.

Keine Edit/Delete-Buttons in Phase 1.

---

## 6. Canvas / Layout Changes

### 6.1 Node-Kind erweitern

`frontend/src/admin/provenienz/layout.ts:28` — `ViewNodeKind`-Union um
`"expert_correction"` ergänzen. `NODE_DIMS.expert_correction = { w: 256, h: 120 }`
(line 245).

### 6.2 Layout-Walker (plan_proposal branch, line ~826)

Wenn ein `plan_proposal` einen eingehenden Edge `kind:"overrides"` hat:
emit einen `expert_correction` View-Node mit demselben Parent-Anchor → dagre
positioniert ihn als Sibling, nicht Downstream-Child.

### 6.3 Tile-Komponente

Neue Datei `frontend/src/admin/provenienz/nodes/ExpertCorrectionTile.tsx`.
Styling: `bg-rose-900/40 border-rose-500/60 text-rose-200`, Lucide
`AlertTriangle`-Icon, single-line `intended_step` in mono, truncated Reason
darunter.

### 6.4 Edge-Variante

`Canvas.tsx` braucht zwei additive Erweiterungen:
- Edge-View bekommt optionales `label?: string` Field
- Edge-Style-Switch: bei `kind:"overrides"` → dashed Stroke + Label rendered
  am Midpoint

Beide minimal-invasiv; bestehende Edges bekommen `label=undefined`.

### 6.5 SidePanel routing

`SidePanel.tsx`: `case "expert_correction":` returns `<ExpertCorrectionPanel />`.

---

## 7. Implementation Steps (ordered)

| # | File | Was | Effort |
|---|---|---|---|
| 1 | `schemas.py` + `provenienz.py:5548` | `ExpertCorrection` Pydantic + `DecideRequest.expert_correction` field + soft validator | S |
| 2 | `provenienz.py:~4814` | `_KNOWN_STEPS = frozenset(s for steps in _VALID_STEPS_FOR_KIND.values() for s in steps)` | S |
| 3 | `provenienz.py:~5562` | `_record_plan_expert_correction()` — Node-Write + `append_reason` + bedingt CR-Node + Edge | M |
| 4 | `provenienz.py:6207` (`decide()`) | `kind`-Guard widen → plan-Branch mit semantischem Guard + Helper + early return | M |
| 5 | `provenienz.py:419` aggregator | Items-Dict: `"actor": n.actor` (Top-Level) | S |
| 6 | `useProvenienz.ts` | TS-Typen + `useAgentInfo` (falls fehlt) | M |
| 7 | `PlanProposalPanel.tsx` | Verwerfen-Morph + Inline-Form + Submit-Handler | M |
| 8 | `layout.ts` + `Canvas.tsx` + `nodes/ExpertCorrectionTile.tsx` + `SidePanel.tsx` | Tile + Edge + Panel | M/L |
| 9 | tsc sweep | Exhaustive-Switch-Audit, Type-Union-Updates | S |

**Gesamt:** 4×S + 4×M + 1×M/L ≈ 2-3 fokussierte Tage Implementation +
1 Tag Tests + ½ Tag Walkthrough-Recording.

---

## 8. Test Plan

### 8.1 Backend (`features/pipelines/local-pdf/tests/test_router_provenienz_decide.py`)

Neue Helper-Fixture: `_plan_propose(client) → (sid, chunk_id, plan_proposal_id)`
(monkeypatch LLM-Planer → deterministischer `executable_step`-payload).

| Test | Assert |
|---|---|
| `test_decide_plan_proposal_known_step_spawns_expert_correction` | 201, `expert_correction` Node mit `actor="human"`, Edge `overrides`, plan_proposal nicht tombstoned |
| `test_decide_plan_proposal_unknown_step_spawns_capability_request` | 2 Sibling-Nodes (EC + CR), `CR.payload.name == intended_step` |
| `test_decide_plan_proposal_reason_only` | EC ohne CR, **kein** Reason/NOTE-Write (kein Override-Target) |
| `test_decide_plan_proposal_persists_note_skill` | `read_session` zeigt NOTE mit `correction_origin="plan_proposal"`, kein Duplikat |
| `test_decide_action_proposal_backcompat` | Bestehende 3 Tests unverändert grün |
| `test_decide_plan_proposal_empty_expert_correction_400` | 400 mit präziser detail-message |
| `test_decide_concurrent_overrides_last_write_wins` | 2 EC-Nodes, beide via `decided-by`, latest-write-wins-Marker korrekt |

### 8.2 Frontend (`frontend/tests/admin/provenienz/PlanProposalPanel.test.tsx`)

Vitest + MSW. Wrap mit `QueryClientProvider`.

| Test | Assert |
|---|---|
| `renders Akzeptieren and Verwerfen initially` | Beide Buttons + Begründung-Section sichtbar, keine Form |
| `first Verwerfen click morphs button into inline form` | Combobox + Textarea + Submit + „Doch löschen" sichtbar |
| `combobox accepts free-text for unknown step` | Input behält rohen String |
| `Submit fires POST /decide with expert_correction body` | MSW-Capture: exakter Body-Shape; `invalidateQueries` lief |
| `empty reason inline-error, no POST` | Inline-Error, MSW-Handler **nicht** gerufen |
| `Akzeptieren still routes to step endpoint (regression)` | `/extract-claims` calling, NICHT `/decide` |
| `Esc collapses form back to Verwerfen button` | Form weg, Original-Buttons zurück |
| `keyboard tab order` | Verwerfen → Combobox → Textarea → Submit |

### 8.3 Manuelles Walkthrough-Recording

Neues File: `frontend/tests/walkthrough/record/provenienz-plan-override.mjs`
(Pattern wie `provenienz-iterate.mjs` — API-Setup + UI-Capture + API-Cleanup,
vLLM up vorausgesetzt).

6 Schritte, <5 min replayable: session create → next-step → Verwerfen-click →
inline-form → submit known-step → submit unknown-step → empty-reason-reject →
Esc-collapse.

### 8.4 Veto-Kriterien (Ship-Stop-Signale)

Beim Walkthrough abbrechen wenn:
1. `/capability-requests`-Aggregator sammelt >5 Typo-Phantom-Requests in 1h
   normaler Nutzung — Eingangs-Filter vor Launch nötig
2. Planer-Re-Run zeigt vLLM-Context-Window-Truncation — Reason-Injection-Cap
   fehlt
3. `read_session` auf Pre-Change-Fixture wirft — Replay-Tolerance gebrochen

---

## 9. Observability

- Existing `events.jsonl` append-only Log fängt alle Node/Edge-Writes auf —
  keine Schema-Migration. `expert_correction`/`capability_request` Nodes
  landen als `_event:"node"`-Lines, von bestehenden Konsumenten als unbekannter
  Kind toleriert.
- Neuer Log-Line in `decide()` plan-Branch:

```python
_log.info("decide.plan_override", extra={
    "step_kind": proposal.payload["name"],
    "intended_step": ec.intended_step,
    "known_step": ec.intended_step in _KNOWN_STEPS,
    "reason_len": len(ec.reason),
})
```

- Dev-Metrik (kein Dashboard, `grep` reicht): override-per-session-Rate,
  known-vs-unknown-Split.

---

## 10. Rollout

- **Feature-Flag:** keine (additive Änderung). Kill-Switch-Fallback:
  `LOCAL_PDF_PLAN_OVERRIDE_ENABLED` env-var um den plan-Branch in `decide()`
  herum, fällt zurück auf heutigen 400.
- **Migration:** keine. `events.jsonl` append-only, alte Sessions enthalten
  nur action_proposal-Decisions, neuer Code dispatcht sie über unchanged-Branch.
  `read_session` toleriert unbekannte Node-Kinds bereits → frontend Layout
  fällt durch zu generischem Tile wenn der neue Kind nicht erkannt wird.
- **Doc-Updates:**
  - Addendum in `docs/superpowers/specs/2026-05-05-provenienzanalyse-design.md`
    nennt `/decide`-kind-widening und neue Node/Edge-Kinds
  - `docs/phases-overview.md` markiert Phase-1 als merged wenn live

---

## 11. Risk Register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Reason-Korpus bläst next-step-Prompt auf | med | `last_n=3` cap für NOTE-Skills mit `correction_origin="plan_proposal"` in `reasons.py:get_last_reasons` |
| 2 | Capability-Request-Spam durch Typo-Step-Names | med | server-side normalize lowercase + 200-char cap, optional Phase-2 Levenshtein-Hint client-side |
| 3 | UI-Scope-Creep in Phase 2 (Args-Editor, Preview, Autocomplete) | med | strikt: Phase-1 ships text-only Combobox + free-text Textarea, explicit Phase-2-Callout im Spec |
| 4 | Agent-vs-Human-Aktor-Drift in CR-Consumern | high | `Node.actor` ist Top-Level (verified), Aggregator surface `actor`-Field ab Tag 1, Vitest-Regression auf Aggregator-Response |
| 5 | NOTE-Skill-Consumer kennt `expert_correction`-Sibling nicht | med | grep `kind == "claim"` für hardcoded consumers im frontend; misses = Phase-1-Blocker |
| 6 | Concurrent-Override append-only Ambiguität | low | append-only semantics dokumentieren; single-tenant macht Risiko ≈0 |
| 7 | Akzeptieren-Regression durch Verwerfen-Morph-Refactor | med | explizite Vitest-Regression in 8.2 |

---

## 12. Open Design Tensions (resolved)

| Tension | Resolution |
|---|---|
| Combobox-Source: `/agent-info` vs hardcoded `STEP_LABEL`-map | `/agent-info` — single source of truth, neue Steps ohne Frontend-Redeploy |
| EC als separate Tile vs Decoration auf plan_proposal | Separate Tile — skaliert auf multi-EC, scrollable Reason-Text |
| `accepted`-Widening: Optional-Field vs Pydantic-Tagged-Union | Optional-Field — smallest diff, kein Frontend-Type-Union-Churn |
| Step-Picker: Strict-Select vs Free-text-Fallback | Free-text baked in (typeahead mit raw-string-Enter) — direkt für unimplemented-Branch |
| `step_kind` für NOTE-Write: proposal.name vs meta-key `plan_override` | `proposal.payload["name"]` — matched bestehende Pipeline, „expert flow"-Replikation pro Step-Kind |
| Korpus-Strategie: NOTE-reuse vs separates `overrides.jsonl` | NOTE-reuse **mit `correction_origin`-Marker** — Phase-2-Migration = 10-Zeilen-Filter-Skript |
| Actor-Field-Naming | `Node.actor` (Top-Level Dataclass-Field), nicht `payload.actor`/`payload.source` |

---

## 13. Future Phases (referenz only)

### Phase 2 — Strukturierung

- Sibling-Node-Kinds: `expert_step_override` + `expert_method_request` für
  schärfere Provenance (Data-Brainstorm #2)
- Anchor-Shape-Retrieval in `_gather_reason_guidance` — match nach
  `anchor_fingerprint`, nicht nur `step_kind` (Feedback-Brainstorm #1)
- Stream-Phase-Event `prior_corrections` im `/next-step/stream` — UI zeigt
  „Agent hat 3 frühere Korrekturen berücksichtigt"
- Post-hoc Korrektur-Schublade im PlanProposalPanel auch nach Akzeptieren
  (UX-Brainstorm #2 — „I realised too late"-Case)

### Phase 3 — Replikation

- Auto-mint `PROMPT_OVERLAY`-Skill ab N≥3 agreeing Overrides (Feedback #2)
- Explicit „Promote to rule" → `REACTIVE`-Skill mit `TriggerConditions`
  (Feedback #3)
- RAG über typed-override-Records via lokalen Embedding-Model
  (Feedback #6, wenn Corpus ≥30)
- Separater `overrides.jsonl`-Store (Backend #5), wenn Korpus-Split-UX nötig

---

## 14. Acknowledgments

Plan via multi-agent Pipeline (4× brainstorm-lens UX/Data/Backend/Feedback →
synthesis → 2× plan-agents Implementation/Test → advisor-stress-test → user
approval). Advisor-flagged 3 echte Inkonsistenzen pre-implementation:
`step_kind`-Wahl, Actor-Field-Naming, Korpus-Reuse-vs-Split — alle resolved
in Section 12.

Brief-Frictions discovered durch UX-Agent:
- „select an alt button" — existiert heute gar nicht; alts sind Read-only
- „file-lock pattern für alle writes" — gilt nur für `sidecar.py`/`curators.py`;
  `events.jsonl` + `skills.jsonl` sind append+tombstone ohne fcntl
