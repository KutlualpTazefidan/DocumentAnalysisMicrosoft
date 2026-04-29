# Phase A.2 — `goldens/schemas/` Design Spec

**Status:** Draft for review
**Date:** 2026-04-28
**Parent spec:** `docs/superpowers/specs/2026-04-28-goldens-restructure-design.md` (§4 Data Model, §6 Schema Versioning, §7 Phase A.2)

---

## 1. Scope

Build the `goldens/schemas/` package — frozen dataclasses defining
the event-sourced data model: `Event`, `Review`, `HumanActor`,
`LLMActor`, and the first concrete entry type `RetrievalEntry`.

This phase delivers **types only**: dataclasses with light
`__post_init__` validation and serialization helpers
(`to_dict`/`from_dict`). No storage, no projection, no I/O.
Phase A.3 (`goldens/storage/`) consumes these types.

## 2. Goals & Non-Goals

### Goals

- Five dataclasses, all `frozen=True`:
  `Event`, `Review`, `HumanActor`, `LLMActor`, `RetrievalEntry`.
- Light `__post_init__` validation: timestamp ISO format,
  `schema_version >= 1`, IDs not empty.
- `to_dict()` / `from_dict()` per type for round-trip JSON
  compatibility.
- A discriminated-union helper for actors (`HumanActor | LLMActor`
  driven by the `kind` field).
- A `RetrievalEntry.level` property derived from `review_chain`,
  using the strict ordering documented in §5.
- 100 % test coverage, per
  `docs/evaluation/coverage-thresholds.md`.

### Non-Goals

- Pydantic. We stay on stdlib `dataclasses` for consistency with
  the rest of the codebase and minimal runtime overhead.
- Validation that requires external resources (e.g. checking a
  chunk_id exists in the index, verifying a chunk_hash matches the
  current chunk content). Those happen at storage / read time.
- `AnswerQualityEntry` and `ClassificationEntry`. Phase B / C
  respectively.
- Schema-version dispatch at the loader level. The `from_dict`
  factories assume `schema_version` ∈ {1}; future major bumps add
  branches. v1 ignores unknown fields silently (additive-only rule).

## 3. Package Layout

```
features/goldens/
├── pyproject.toml
├── README.md
├── src/
│   └── goldens/
│       ├── __init__.py            ← re-exports the public API
│       └── schemas/
│           ├── __init__.py
│           ├── base.py            ← Event, Review, HumanActor, LLMActor, Actor union
│           └── retrieval.py       ← RetrievalEntry
└── tests/
    ├── conftest.py
    ├── test_base.py
    └── test_retrieval.py
```

No `tests/__init__.py` (matches the convention used by all other
packages — pytest collects tests without it; adding one risks the
namespace collision that bit Phase A.1 Task 7).

## 4. Types

### 4.1 Actors

```python
# goldens/schemas/base.py

@dataclass(frozen=True)
class HumanActor:
    pseudonym: str                     # GDPR-safe identifier
    level: Literal["expert", "phd", "masters", "bachelors", "other"]
    kind: Literal["human"] = "human"   # discriminator; default last per dataclass rules

    def __post_init__(self) -> None:
        if not self.pseudonym:
            raise ValueError("pseudonym must be non-empty")


@dataclass(frozen=True)
class LLMActor:
    model: str
    model_version: str
    prompt_template_version: str
    temperature: float
    kind: Literal["llm"] = "llm"

    def __post_init__(self) -> None:
        for f in ("model", "model_version", "prompt_template_version"):
            if not getattr(self, f):
                raise ValueError(f"{f} must be non-empty")


Actor = HumanActor | LLMActor
```

The `kind` field is the discriminator. Default values let a caller
write `HumanActor(pseudonym="alice", level="phd")` without explicitly
passing `kind`.

### 4.2 Review

```python
@dataclass(frozen=True)
class Review:
    timestamp_utc: str
    action: Literal[
        "created_from_scratch", "synthesised", "imported_from_faq",
        "accepted_unchanged", "approved", "rejected",
        "deprecated",
    ]
    actor: Actor                       # HumanActor or LLMActor
    notes: str | None

    def __post_init__(self) -> None:
        _validate_iso_utc(self.timestamp_utc)
```

`Review` is the projection-time view of an event. Storage-layer
projection (Phase A.3) constructs `Review` instances from the raw
event log.

### 4.3 Event

```python
@dataclass(frozen=True)
class Event:
    event_id: str                      # UUID4
    timestamp_utc: str
    event_type: Literal["created", "reviewed", "deprecated"]
    entry_id: str                      # UUID4
    schema_version: int
    payload: dict                      # event-type-specific; no narrower type in v1

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id must be non-empty")
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if self.schema_version < 1:
            raise ValueError("schema_version must be >= 1")
        _validate_iso_utc(self.timestamp_utc)
```

The `payload` dict is intentionally untyped at the dataclass layer
because its shape varies by `event_type`. Storage / projection
layers downcast safely.

### 4.4 RetrievalEntry

```python
# goldens/schemas/retrieval.py

@dataclass(frozen=True)
class RetrievalEntry:
    entry_id: str
    query: str
    expected_chunk_ids: tuple[str, ...]   # tuple for hashability
    chunk_hashes: dict[str, str]          # chunk_id → "sha256:..." at curation time
    review_chain: tuple[Review, ...]      # tuple for hashability
    deprecated: bool
    refines: str | None                   # entry_id of predecessor
    task_type: Literal["retrieval"] = "retrieval"

    def __post_init__(self) -> None:
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if not self.query:
            raise ValueError("query must be non-empty")

    @property
    def level(self) -> Literal["expert", "phd", "masters", "bachelors", "other", "synthetic"]:
        """Highest human level in review_chain; 'synthetic' if only
        LLM actors have touched this entry."""
        return _highest_level(self.review_chain)
```

`expected_chunk_ids` and `review_chain` are tuples (not lists)
because frozen dataclasses with mutable container fields are a
documented foot-gun: the dataclass is "frozen" but its list field is
mutable, breaking the hash invariant. Tuples preserve immutability.

## 5. The `level` Ordering

The ordering used by `_highest_level`:

```python
_HUMAN_LEVEL_ORDER: tuple[str, ...] = (
    "expert", "phd", "masters", "bachelors", "other",
)
```

Algorithm:

1. Collect `actor.level` for every `Review` whose actor is a
   `HumanActor`.
2. If the set is empty, return `"synthetic"`.
3. Otherwise return the value that appears earliest in
   `_HUMAN_LEVEL_ORDER`.

Rationale: a single expert sign-off "wins" over any number of lower
levels. We don't average or count — the highest authority that has
touched the entry is its level. This matches how Microsoft's
collaborators expect provenance to be summarised.

## 6. Serialization Contract

Every dataclass has:

- `to_dict() -> dict` — returns a JSON-compatible dict (only
  primitives, lists, and dicts).
- `cls.from_dict(d: dict) -> Self` — reverse direction.

For the actor union, a free function:

```python
def actor_from_dict(d: dict) -> Actor:
    """Dispatch on the 'kind' discriminator."""
    kind = d.get("kind")
    if kind == "human":
        return HumanActor.from_dict(d)
    if kind == "llm":
        return LLMActor.from_dict(d)
    raise ValueError(f"unknown actor kind: {kind!r}")
```

`Review.from_dict` uses `actor_from_dict` for its `actor` field.
`RetrievalEntry.from_dict` rebuilds `review_chain` as a tuple of
`Review.from_dict` calls.

`to_dict` is mostly `dataclasses.asdict()` plus normalisation (lists
→ stay lists in JSON; tuples become lists). `from_dict` is hand-rolled
to handle the union dispatch and the tuple/list conversion.

## 7. Schema Versioning Behaviour in v1

- `Event.schema_version` field is set to `1` by default in
  factories that produce events; consumers reading older logs use the
  same code path because no v0 ever existed.
- `from_dict` ignores unknown keys silently (forward compatibility).
- `from_dict` accepts missing optional fields by relying on dataclass
  defaults. This means `RetrievalEntry.refines` defaults to `None`,
  `task_type` defaults to `"retrieval"`, etc.

When a future schema_version 2 ships, `from_dict` becomes a small
dispatch on the field. Not in scope here.

## 8. Coverage Strategy

100 % per `docs/evaluation/coverage-thresholds.md`. This means
covering:

- All `__post_init__` branches (every `raise ValueError`).
- Both branches of `actor_from_dict` (`human`, `llm`) and the
  unknown-kind error path.
- `level` property: each ordering tier reachable, plus the
  "synthetic" branch (only LLM actors).
- `to_dict`/`from_dict` round-trip equivalence for every type.
- `from_dict` ignoring unknown keys.

## 9. Open Questions

None — design is a literal projection of the parent restructure
spec's §4 onto the file structure decided in §3.

## 10. Out of Scope

- `Event.payload` typed shape per `event_type` — handled in storage
  via narrow projection helpers.
- Migration from any prior schema — none exists (fresh start, parent
  spec §7 R6).
- Pydantic alternative — explicitly rejected for stdlib parity.
