# Phase A.4 — `goldens/creation/curate` Design Spec

**Status:** Draft for review
**Date:** 2026-04-29
**Branch:** `feat/a4-curate`
**Parent specs:**
- `docs/superpowers/specs/2026-04-28-goldens-restructure-design.md` (§3 Architecture, §7 Phase A.4)
- `docs/superpowers/specs/2026-04-28-a2-goldens-schemas-design.md` (Event / RetrievalEntry / SourceElement consumed here)
- `docs/superpowers/specs/2026-04-29-a3-goldens-storage-design.md` (event log this CLI writes to)

---

## 1. Scope

A.4 reinstates the `query-eval curate` subcommand that Phase 0
deleted. The new implementation is an interactive, LLM-free CLI that
walks the structural elements of a single source document
(paragraphs / headings / tables / figures / list items extracted from
Document Intelligence `analyze.json`) and lets a human curator type a
question per element. Each saved question becomes one `created` event
appended to the dataset's event log via `goldens/storage/`.

A.4 owns three things:

- A shared **`creation/elements/` adapter** package
  (`ElementsLoader` Protocol + `AnalyzeJsonLoader` concrete impl)
  that A.5 (synthetic generation) will reuse unchanged.
- The **curator identity** layer
  (`~/.config/goldens/identity.toml`) and the **per-doc position
  cache** (`~/.config/goldens/positions.toml`).
- The **interactive curate loop** itself
  (`creation/curate.py` + the `cmd_curate` CLI handler).

A.4 is a writer of the event log; it does not read it back. The
read side stays with A.7 (chunk-match) and the operations layer.

## 2. Goals & Non-Goals

### Goals

- Element-based curation: one `DocumentElement` shown at a time, one
  question typed at most, one `created` event saved on confirm.
- Content-stable element-IDs of shape `p{page}-{first-8-of-sha256(content)}`
  so re-running `analyze.json` does not invalidate prior goldens.
- Pipeline-agnostic ground truth: every saved entry carries a
  `source_element` payload (document slug + page + element-hash +
  element-type); `expected_chunk_ids` ships empty `[]` (D13).
- Single-process safety via the existing `append_event` lock; no new
  locking concerns introduced here.
- Resume-where-you-left-off via the per-doc position cache, with
  silent-degrade on cache corruption.
- Hold `goldens/creation/` coverage at the **70 %** floor from
  `docs/evaluation/coverage-thresholds.md`. Helpers are unit-tested;
  the outer `input()/print()` loop is `# pragma: no cover`.

### Non-Goals

- No LLM-assisted answerability check, no heuristic question scoring
  beyond the legacy 30-character substring-overlap anti-paste warning
  (D8 / D10).
- No backwards-compatibility shim for the legacy curate writer
  (D12 — fresh-start writer; the legacy path was deleted in Phase 0).
- No multi-element entries; `source_element` is a single element per
  entry. Multi-element support is deferred to Phase F.
- No browser / HTTP UX. The combined curate+review browser UI is
  Phase A-Plus.
- No edit-existing-from-CLI. Refining or deprecating an entry uses
  the A.6 operations API; A.4 only creates.
- No element→chunk derivation. The `source_element → chunk_ids`
  match-type classifier (EXACT / CONTAINED / CONTAINS / OVERLAP /
  MISS) is the next architectural phase after A.4 / A.5 land.
- No Pseudonym escaping or sonderzeichen tests — the
  `HumanActor.pseudonym` field is provisional pending IT/DSGVO
  review (D17, `project_pseudonym_provisional.md`).
- No `--no-tty` opt-out, no random navigation, no element search.

## 3. Package Layout

New code under `features/goldens/src/goldens/creation/`:

```
creation/
├── __init__.py              ← re-exports the public A.4 + A.5 surface
├── elements/                ← shared loader package (consumed by a4 + a5)
│   ├── __init__.py
│   ├── adapter.py           ← ElementsLoader Protocol + DocumentElement dataclass
│   └── analyze_json.py      ← AnalyzeJsonLoader concrete impl
├── identity.py              ← curator profile (~/.config/goldens/identity.toml)
├── positions.py             ← per-doc position cache (~/.config/goldens/positions.toml)
└── curate.py                ← interactive loop + cmd_curate CLI handler
```

Public surface re-exported from `goldens.creation`:

```python
from goldens.creation import (
    DocumentElement, ElementsLoader, AnalyzeJsonLoader, ElementType,
    Identity, load_identity, cmd_curate,
)
```

`ElementType` is re-exported from `goldens.schemas` (already public)
so consumers do not need to know it lives there.

**Import boundary.** `goldens.creation` imports only from
`goldens.schemas` and `goldens.storage`. **No** imports from
`core/`, `pipelines/`, or `evaluators/`. The two new edges this
phase touches outside `creation/`:

- `features/evaluators/chunk_match/src/.../cli.py` — register the
  `curate` subcommand (one new import + one parser block).
- `goldens/storage/projection.py` — extend `_apply_created` to
  thread `source_element` from `entry_data` into `RetrievalEntry`
  (D18, §5.4). One block + one new import of `SourceElement`.

CLI shape:

```
query-eval curate
query-eval curate --doc <slug>
query-eval curate --doc <slug> --start-from <element-id-or-prefix>
```

## 4. Data Model

### 4.1 `DocumentElement`

```python
# goldens/creation/elements/adapter.py
from goldens.schemas import ElementType   # single source of truth

@dataclass(frozen=True)
class DocumentElement:
    element_id: str                            # "p{page}-{8-char-sha256-hex}"
    page_number: int                           # 1-indexed
    element_type: ElementType
    content: str                               # plain text, normalised whitespace
    table_dims: tuple[int, int] | None = None  # (rows, cols), only for tables
    caption: str | None = None                 # only for figures
```

`element_id` format: `p{page_number}-{first 8 hex chars of sha256(content)}`
(e.g. `p47-a3f8b2c1`). Constraints:

- **Content-stable.** Re-running `analyze.json` against the same PDF
  produces the same id for the same paragraph text, even if its
  positional rank shifts.
- **Page-prefixed for human scanability.** A curator can eyeball
  `p47-...` and know they are on page 47.
- **Hash collision behaviour.** SHA-256 truncated to 8 hex chars =
  32 bits. Collision probability across N elements on the same page
  follows the birthday bound; for realistic page sizes
  (< ~10 paragraphs/page) collision is astronomically unlikely. We
  do not detect or special-case collisions in v1; if a collision
  ever surfaces in real data we widen the suffix.

### 4.2 `ElementsLoader` Protocol

```python
# goldens/creation/elements/adapter.py
class ElementsLoader(Protocol):
    def elements(self) -> list[DocumentElement]: ...
```

A.4 supplies `AnalyzeJsonLoader` (§4.3). A.5 will supply additional
loaders (e.g. for synthetic seed paragraphs) without changing the
curate code.

### 4.3 `AnalyzeJsonLoader`

```python
# goldens/creation/elements/analyze_json.py
class AnalyzeJsonLoader:
    slug: str  # public attribute, used by A.5 to construct SourceElement

    def __init__(self, slug: str, *, outputs_root: Path | None = None) -> None:
        ...

    def elements(self) -> list[DocumentElement]:
        ...

    def to_source_element(self, el: DocumentElement) -> SourceElement:
        return SourceElement(
            document_id=self.slug,
            page_number=el.page_number,
            element_id=el.element_id.split("-", 1)[1],   # hash portion only
            element_type=el.element_type,
        )
```

**Discovery.** `AnalyzeJsonLoader(slug=...)` walks
`{outputs_root or "outputs"}/{slug}/analyze/` and picks the
**lexicographically latest** `<ts>.json` file. (The ingest pipeline
writes ISO-8601 timestamps, which sort correctly as strings.)
Missing directory → `FileNotFoundError` with a message naming the
expected path.

**Filter rules** (`analyze.json` → `DocumentElement`):

| Source | Condition | element_type |
|---|---|---|
| `paragraphs[*]` | `role` ∈ `{pageHeader, pageFooter, pageNumber, footnote}` | **dropped** (matches legacy `SKIP_ROLES`) |
| `paragraphs[*]` | `role == "title"` | `heading` |
| `paragraphs[*]` | `role == "sectionHeading"` | `heading` |
| `paragraphs[*]` | otherwise | `paragraph` |
| `tables[*]` | always | `table` (content = compact stub from cell grid) |
| `figures[*]` | always | `figure` (caption captured, content = "") |
| any of the above | empty `content.strip()` AND no caption | **dropped** |

`role == "listItem"` is not a Document Intelligence native role for
v1 documents in scope; if encountered it falls through to the
"otherwise" bucket as `paragraph`. Promoting it to `list_item`
remains additive in a later spec.

**Page extraction.** Each element's `boundingRegions[0].pageNumber`
is the page. Elements without bounding regions are dropped (defensive
— no real source produces them).

**Ordering.** Elements are sorted by `(page_number, top_y)` where
`top_y = boundingRegions[0].polygon[1]` (y-coordinate of the first
polygon vertex). This places paragraphs and tables on the same page
in reading order.

**Table content stub.** A small textual representation of the cell
grid (e.g. up to 3 rows × 5 cols rendered as pipe-separated text,
truncated with `…`). The full cell grid is reachable interactively
via the `t` toggle (§5.2). `table_dims` carries `(row_count,
column_count)` from the source.

**`to_source_element` lives on the loader.** It is the
**Category-1** decision for A.5: A.5 needs a deterministic
`DocumentElement → SourceElement` mapping for synthetic entries, and
the loader is the only object that knows the document slug. Putting
the helper here means A.5 imports the loader and never re-derives
the mapping.

### 4.4 `Identity`

```python
# goldens/creation/identity.py
@dataclass(frozen=True)
class Identity:
    schema_version: int            # always 1 in v1
    pseudonym: str
    level: Literal["expert", "phd", "masters", "bachelors", "other"]
    created_at_utc: str            # ISO-8601 Z

def load_identity() -> Identity | None: ...
def prompt_and_save_identity() -> Identity: ...
def identity_to_human_actor(i: Identity) -> HumanActor: ...
```

`load_identity()` returns `None` when the file is absent (first-run
case). It **fails loud** with a clear error when the file exists but
is malformed (corrupt TOML, unknown level, missing required keys,
`schema_version != 1`). Identity is consent-bearing data; silent
defaults are wrong here. (D15.)

`prompt_and_save_identity()` first-run UX:

1. Print a one-paragraph note: "Wir speichern ein **Pseudonym**, keinen
   Klarnamen. Niveau-Selbsteinschätzung dient nur dem Gewichten der
   Reviews."
2. Prompt for `pseudonym` (non-empty after `.strip()`; re-prompt once
   on empty).
3. Prompt for `level`. Invalid input re-prompts **once**; second
   invalid attempt → `sys.exit(2)` with a clear message ("ungültiges
   Level zweimal eingegeben — Abbruch").
4. Atomically write the file (`tmp + os.replace`) to
   `${XDG_CONFIG_HOME or ~/.config}/goldens/identity.toml`.

### 4.5 Position cache

```python
# goldens/creation/positions.py
def read_position(slug: str) -> str | None: ...
def write_position(slug: str, element_id: str) -> None: ...
```

`read_position` returns `None` for any unreadable case (file missing,
file corrupt, key absent). It does **not** raise — the cache is a
navigation hint, never a blocker (D15).

`write_position` writes the file atomically (`tmp + os.replace`
within the same directory) so a crash during write cannot leave a
half-written file in place.

## 5. Curate Session Lifecycle

### 5.1 Top-level flow

```
parse args (--doc, --start-from)
        │
        ▼
resolve doc-slug:
    --doc set        → use it
    --doc unset      → scan {outputs_root}/* for dirs containing analyze/<ts>.json
                       1 match → auto-pick
                       0 or >1 → exit code 2 with a clear message
        │
        ▼
require_interactive_tty()      # exit cleanly if stdin/stdout not a TTY
        │
        ▼
identity = load_identity()
    None  → prompt_and_save_identity() and return (curator just configured profile)
    else  → loaded
        │
        ▼
loader = AnalyzeJsonLoader(slug)
elements = loader.elements()
        │
        ▼
resolve start position:
    --start-from <id-or-prefix>:
         exact id match  → start there
         prefix match    → start at first element whose id starts with prefix
         no match        → exit code 2
    --start-from absent:
         positions.toml[slug] points at an existing element → start there
         else                                               → start at element 0
        │
        ▼
print intro banner
        │
        ▼
loop over elements[start:]:
    render element block
    read user input
    apply input state machine (§5.2)
    on save / weiter:  write_position(slug, current.element_id) → next
    on quit:           write_position(slug, current.element_id), clean exit
    on end-of-list:    print "Du hast alle Elemente von <slug> durchgesehen."
```

`require_interactive_tty()` is the **verbatim legacy guard** — a hard
exit when `sys.stdin.isatty()` or `sys.stdout.isatty()` is False, with
an explicit message naming the missing side. No `--no-tty` opt-out
(D9).

### 5.2 Per-iteration UX

The prompt is constant text:

```
Frage zu diesem Absatz (oder ENTER für 'Weiter', 'q' zum Beenden, 't' für volle Tabelle):
> 
```

Input state machine:

| Input | Action |
|---|---|
| `q` | Quit. Write position, clean exit. |
| empty (just ENTER) | "Weiter" without confirmation prompt. Advance. |
| `t` (only on a `table` element) | Re-render with the **full** cell grid, then re-prompt. |
| any non-empty other text | Treat as a typed question. Run the save sub-flow. |

Save sub-flow on a typed question:

```
1. anti-paste check:
       overlap = query_substring_overlap(question, element.content, threshold=30)
       overlap is True  → warn, prompt "Trotzdem speichern? [j/N]"
                              n / empty → discard, ask "Weiter? [j/N]"  (Q6 confirm-if-typed)
                                              j      → next, no save
                                              else   → re-prompt question
                              j         → continue to step 2
       overlap is False → continue to step 2
2. prompt "Speichern? [J/n]"
       J / empty → save event (§5.3), write_position, advance
       n         → discard. Prompt "Weiter? [j/N]" as above.
```

The `Weiter? [j/N]` confirm exists only when the user has already
typed something. Pressing ENTER on a clean prompt advances directly
without confirmation (D7 / Q6).

Per-element-type rendering:

- `paragraph` / `heading` / `list_item`: print element type, page, id,
  then the content body with a wrap.
- `table`: header line ("Tabelle, p47, 5×3"), compact stub. The user
  pressing `t` re-renders the same element with the full cell grid.
  The toggle is one-shot per render — typing anything after the full
  view counts as a question.
- `figure`: header line, the caption verbatim, then a fixed line
  "(Bild kann im Terminal nicht angezeigt werden — siehe PDF Seite N)".

### 5.3 Saving = one `created` event

```python
event = Event(
    event_id=new_event_id(),
    timestamp_utc=now_utc_iso(),
    event_type="created",
    entry_id=new_entry_id(),
    schema_version=1,
    payload={
        "task_type": "retrieval",
        "actor": identity_to_human_actor(identity).to_dict(),
        "action": "created_from_scratch",
        "notes": None,
        "entry_data": {
            "query": typed_question,
            "expected_chunk_ids": [],          # D13: empty; source_element is the truth
            "chunk_hashes": {},
            "source_element": loader.to_source_element(current_element).to_dict(),
        },
    },
)
append_event(events_path, event)
```

`events_path = outputs_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME`.

The event-log filename constant is the one defined in
`goldens/storage/__init__.py` and re-exported from `goldens` (A.7
spec §4.1). A.4 imports it directly — no string-literal duplication.

`expected_chunk_ids: []` is **deliberate** (D13). The
`source_element → chunk_ids` translation belongs in a dedicated
match-type classifier (the next architectural phase). A.7's current
chunk-match evaluator cannot evaluate these entries yet; this is
called out in the PR description and tracked under "Known
Follow-ups" in §11.

`chunk_hashes: {}` mirrors the same: chunk-level integrity is a
match-time concern, not a curate-time one.

### 5.4 Projection thread-through (one-line storage edit)

`goldens/schemas/retrieval.py` already round-trips
`RetrievalEntry.source_element` through `to_dict` / `from_dict` (added
in A.3.1). The in-memory projection in `goldens/storage/projection.py`
does **not** yet read it: `_apply_created` constructs the
`RetrievalEntry` without threading `entry_data["source_element"]` in,
so today the field would land in the event log but emerge as `None`
from `build_state()`.

A.4 closes that gap, because D13 — "`source_element` is the ground
truth" — only holds end-to-end if the projection surfaces the field.
The change is one block in `_apply_created`:

```python
src_raw = entry_data.get("source_element")
src = SourceElement.from_dict(src_raw) if src_raw is not None else None
state[ev.entry_id] = RetrievalEntry(
    ...
    source_element=src,
)
```

Test: `test_storage_projection_threads_source_element` (created event
with `source_element` payload → projected `RetrievalEntry.source_element`
is the same dataclass, equal by value). This keeps `goldens/storage/`
above its 95 % floor.

The `_apply_reviewed` path is unchanged: review events do not carry
`source_element`; the field is set at creation time and inherited via
`replace(entry, ...)` in subsequent reviews.

## 6. File Formats

### 6.1 `~/.config/goldens/identity.toml`

```toml
schema_version = 1
pseudonym = "alice"
level = "masters"            # expert | phd | masters | bachelors | other
created_at_utc = "2026-04-29T14:32:00Z"
```

- Path: `${XDG_CONFIG_HOME}/goldens/identity.toml` if `XDG_CONFIG_HOME`
  is set and non-empty, else `~/.config/goldens/identity.toml`.
  (XDG semantics, matches `goldens` convention.)
- **Fail-loud** on any schema violation (corrupt TOML, missing key,
  unknown `level`, `schema_version != 1`).
- Reading uses stdlib `tomllib` (Python 3.11+).
- Writing uses the hand-rolled `_dump_toml` (D14).

### 6.2 `~/.config/goldens/positions.toml`

```toml
schema_version = 1

[positions]
"tragkorb-b-147-2001-rev-1" = "p47-a3f8b2c1"
```

- Path: same XDG resolution as identity.
- **Silent-degrade** on every error path. Any failure during read
  yields `None`; the curator simply restarts at element 0.
- Writes are atomic (`tmp + os.replace` in the same directory) so a
  concurrent crash cannot tear the file.
- Slug keys may contain hyphens and digits — round-tripped quoted to
  stay safe in TOML.

### 6.3 TOML writer

Hand-rolled `_dump_toml(d) -> str` of about 30 LOC, happy-path only
(D14). It supports exactly what these two files need: top-level
scalar keys (string, int) and one nested table (`[positions]` with
quoted string keys mapping to string values). Unsupported shapes
raise `TypeError` with a clear message — we surface bugs in the
caller rather than silently mis-encoding.

The reader is stdlib `tomllib`. Pulling in `tomli_w` for ~30 LOC of
emit logic is unjustified; pulling in a full third-party TOML lib for
two files is over-engineering.

### 6.4 Code layout

- `creation/identity.py` — `Identity` dataclass, `load_identity`,
  `prompt_and_save_identity`, `identity_to_human_actor`.
- `creation/positions.py` — `read_position`, `write_position`.
- A private `_config_dir() -> Path` helper lives **locally inside
  each module** (not shared). The two callers each have a one-line
  resolver; promoting it to a shared helper would couple two
  otherwise-independent files for no real gain.

## 7. Anti-Paste Heuristic

Reused verbatim from the legacy curate writer:

```python
def query_substring_overlap(query: str, source: str, *, threshold: int) -> bool:
    """True if any contiguous substring of `query` of length >= threshold
    appears in `source`. Both strings are normalised (lowercased,
    whitespace-collapsed) before comparison."""
```

`threshold = 30` characters (D8). The heuristic is intentionally
conservative — it catches obvious copy-pastes ("der Tragkorb wird in
zwei Hälften gefertigt …" pasted as a question) without flagging
short legitimate quotes ("§47 Abs. 2"). Lifting the threshold or
swapping the algorithm is a future tuning concern, not part of A.4.

The check is one of two safety nets (the other is the explicit
"Speichern? [J/n]" confirmation). No LLM-side validation in v1
(D10) — A.4 stays LLM-free, which keeps the curate loop offline,
fast, and free.

## 8. CLI Wiring

`cmd_curate` is registered as the `curate` subcommand of
`query-eval`. The wiring change is one new import + one new
`add_subparser` block in
`features/evaluators/chunk_match/src/.../cli.py` (or whichever module
hosts the `query-eval` argparser; the existing `eval` subcommand
neighbour is the reference).

```python
from goldens.creation import cmd_curate

def _build_curate_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("curate", help="Interactive goldset curation")
    p.add_argument("--doc", help="Document slug; auto-pick if exactly one exists")
    p.add_argument("--start-from", help="Element id or prefix to resume from")
    p.set_defaults(func=cmd_curate)
```

`cmd_curate(args: argparse.Namespace) -> int` returns:

- `0` on clean exit (`q`, end-of-list, identity just configured)
- `2` on usage errors (no doc / multiple docs / unknown `--start-from`)

## 9. Test Plan

| Module | Coverage | Strategy |
|---|---|---|
| `creation/elements/adapter.py` | 100 % | Pure dataclass + Protocol; trivial |
| `creation/elements/analyze_json.py` | 95+ % | Fixture-driven; two minimal `analyze.json` files |
| `creation/identity.py` | 90+ % | XDG monkeypatch; round-trip + corruption + first-run prompt |
| `creation/positions.py` | 100 % | XDG monkeypatch; tolerance + atomicity |
| `creation/curate.py` (helpers) | 70+ % | Helpers tested; outer `input()/print()` loop is `# pragma: no cover` |
| `storage/projection.py` (edit) | 95+ % | New test threads `source_element` through `_apply_created` |
| `evaluators/.../cli.py` (curate edge) | covered | One-line extension to existing `test_cli.py` |

Project-wide `--cov-fail-under=100` for `goldens` stays. The
per-module floor for `creation/` is the documented 70 % from
`docs/evaluation/coverage-thresholds.md`. The interactive-loop body
(`# pragma: no cover`) is the only uncovered region in `curate.py`;
all decision-bearing helpers (`resolve_slug`, `resolve_start`,
`build_event`, `query_substring_overlap`, …) are tested directly.

### 9.1 `test_creation_elements_analyze_json.py`

- `filter_noise_roles` — pageHeader / pageFooter / pageNumber / footnote
  paragraphs are dropped.
- `role_to_type_mapping` — title and sectionHeading become `heading`;
  generic paragraphs become `paragraph`.
- `element_id_stability` — same content under different file-positions
  returns the same id.
- `element_id_format` — every id matches `^p\d+-[0-9a-f]{8}$`.
- `ordering_by_page_then_y` — interleaved paragraphs and tables on the
  same page sort by top-y.
- `table_element_has_dims` — `table_dims == (rows, cols)` from source.
- `figure_caption_extracted` — caption set, content empty.
- `empty_content_dropped` — paragraph with only whitespace is dropped;
  figure with only a caption is kept.
- `picks_latest_analyze_json` — given two `<ts>.json`, the
  lexicographically latest one is loaded.
- `missing_outputs_dir_error` — `FileNotFoundError` names the path.
- `to_source_element_maps_correctly` — round-trip for each element
  type; `element_id` is the hash portion (no `p47-` prefix);
  `document_id == loader.slug`; `page_number` propagated.

### 9.2 `test_creation_identity.py` (happy path only — D17)

- `load_returns_none_when_file_absent`
- `load_round_trip_alice_no_special_chars`
- `load_raises_on_invalid_level`
- `load_raises_on_corrupt_toml`
- `load_raises_on_missing_schema_version`
- `xdg_config_home_respected` (env set vs. unset)
- `prompt_and_save_writes_atomically`
- `prompt_invalid_level_re_prompts_once`
- `prompt_double_invalid_exits_with_code_2`

No tests for pseudonym escaping, sonderzeichen, normalisation,
length limits, or unicode classes (D17).

### 9.3 `test_creation_positions.py`

- `read_returns_none_when_file_absent`
- `read_returns_none_when_file_corrupt`
- `read_returns_none_when_slug_absent`
- `write_creates_file`
- `write_updates_existing_slug`
- `write_atomic_under_concurrent_writers`
  — two `multiprocessing.Process` writing different slugs in a tight
  loop; final file parses and contains both keys with correct values.
  `@pytest.mark.skipif(sys.platform == "win32", reason="POSIX rename semantics")`.
- `xdg_config_home_respected`
- `slug_with_hyphens_round_trips`

### 9.4 `test_creation_curate.py` (helpers only)

- `resolve_slug_auto_picks_when_one_doc`
- `resolve_slug_errors_when_zero_docs` (exit code 2, message names path)
- `resolve_slug_errors_when_multiple_docs` (lists candidate slugs)
- `resolve_start_exact_id_wins`
- `resolve_start_prefix_match_when_no_exact`
- `resolve_start_unknown_id_errors_with_code_2`
- `resolve_start_falls_back_to_position_cache`
- `resolve_start_falls_back_to_zero_when_cache_misses`
- `query_substring_overlap_30_chars_true_for_paste`
- `query_substring_overlap_30_chars_false_for_short_quote`
- `build_event_shape` — every required key present, types correct
- `build_event_source_element_id_strips_page_prefix` — `p47-a3f8b2c1`
  becomes `a3f8b2c1` in `payload.entry_data.source_element.element_id`
- `build_event_chunk_ids_empty_and_chunk_hashes_empty`
- `require_interactive_tty_exits_when_not_tty`

### 9.5 `test_storage_projection_*.py` (extension)

- `test_projection_threads_source_element_through_created`
  — append a `created` event with a fully-formed `source_element` in
  `entry_data`, build state, assert
  `entry.source_element == SourceElement(...)` by value.
- `test_projection_source_element_absent_yields_none` — created event
  whose payload has no `source_element` key still projects (legacy
  pre-A.3.1 entries). `entry.source_element is None`.

### 9.6 Fixtures

Co-located under `features/goldens/tests/fixtures/`:

- `analyze_minimal.json` — single page, two paragraphs (one
  `pageHeader` to be dropped, one body), one table, one figure.
- `analyze_with_two_pages.json` — interleaves paragraphs and a table
  across two pages so the ordering test has something to bite on.

### 9.7 Deliberately not tested

- Outer interactive `input()/print()` loop (`# pragma: no cover`).
  All decision-bearing branches are extracted into helpers and
  tested there.
- Pseudonym sonderzeichen / escape rules (D17).
- Cross-machine clock skew on `created_at_utc`.
- Ingest-pipeline integration (different repo edge).

## 10. Decision Log

| # | Topic | Decision |
|---|---|---|
| D1 | Element source | Adapter `ElementsLoader` Protocol + `AnalyzeJsonLoader` concrete impl (Q1c) |
| D2 | Element ID format | `p{page}-{first 8 hex of sha256(content)}` — content-stable |
| D3 | Multi-doc selection | Auto-pick if exactly 1 candidate, else exit 2 (Q2c) |
| D4 | Position cache | Separate file `~/.config/goldens/positions.toml`, tolerant reads (Q3b) |
| D5 | Table display | Compact stub, `t` toggle for full content (Q4b) |
| D6 | Figure display | Caption + page reference, no image rendering (Q5b) |
| D7 | "Weiter" confirmation | Confirm only if user already typed something (Q6c) |
| D8 | Anti-paste | Reuse legacy `query_substring_overlap`, threshold 30 (Q7a) |
| D9 | TTY guard | Verbatim legacy guard, no `--no-tty` opt-out (Q8a) |
| D10 | LLM validation | None — A.4 stays LLM-free (Q9b) |
| D11 | `--start-from` | Exact id first, prefix fallback (Q10c) |
| D12 | Backwards compat | None — fresh-start writer (Q11b) |
| D13 | `expected_chunk_ids` | Empty `[]`; `source_element` is the ground truth |
| D14 | TOML writer | Hand-rolled ~30 LOC, happy path only |
| D15 | Identity vs. positions | Identity fails loud; positions silent-degrade |
| D16 | A.5 sub-unit decomposition | A.5 owns its own helper; loader stays slim |
| D17 | Pseudonym schema | v1-provisional; format may change after IT/DSGVO review. Validation minimal. |
| D18 | Projection thread-through | A.4 extends `_apply_created` to surface `source_element` in `RetrievalEntry`. Without it, D13 ("source_element is the truth") would not hold end-to-end. |

## 11. Known Follow-ups

To be reproduced verbatim in the PR description:

> A.4 entries currently ship with `expected_chunk_ids = []`. They
> have a valid `source_element`. The current A.7 `chunk_match`
> evaluator (PR #11) cannot yet evaluate them; the dedicated
> `source_element → chunk_ids` translation layer (match-type
> classifier: EXACT / CONTAINED / CONTAINS / OVERLAP / MISS) is the
> next architectural phase after A.4 / A.5 land.
>
> Pseudonym / identity field handling is provisional pending
> internal IT / DSGVO review.

## 12. Open Questions

None. Q1–Q11 stay settled; the brief's §1–§5 are a direct
projection onto file structure and code surface here. §5.4 / D18
(projection thread-through) is a self-review-derived consequence of
D13: without it, "`source_element` is the ground truth" would not
hold end-to-end. The change is one block + two tests, all inside the
A.4 PR's blast radius.

## 13. Out of Scope

- HTTP / FastAPI surface — Phase A-Plus.
- Combined curate + review browser UI — Phase A-Plus.
- Multi-element entries — Phase F.
- `--no-tty` opt-out, random navigation, in-CLI element search.
- Edit-existing-from-CLI — A.6 owns programmatic refine / deprecate.
- Element → chunk derivation — next architectural phase after A.4 / A.5.
- Pseudonym sonderzeichen / escape testing — D17.
