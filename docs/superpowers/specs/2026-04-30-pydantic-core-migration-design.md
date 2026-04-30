# Pydantic-v2 Core Migration — Design

**Status:** Draft, brainstorming-derived (2026-04-30). Prerequisite for A-Plus.1 (Backend HTTP-API).

## 1. Motivation

`goldens.schemas` was implemented in A.2 (PR #8) as frozen dataclasses with hand-rolled `to_dict` / `from_dict` methods. That choice was deliberate at the time — Pydantic was avoided as a runtime dependency in `core/` and `goldens/`, and the schemas were treated as DTOs without business logic.

Since then:

- A.7 wired `chunk_match` against the projected event log
- A.4-A.6 stabilized creation and operations modules
- The smoke-test loop (PRs #15-#17) demonstrated the end-to-end stack works

The next phase (A-Plus.1) introduces a FastAPI-based HTTP API that exposes the same domain types. With dataclasses, that surface needs **either** Pydantic mirror models at the API boundary (drift risk, ~230 LOC of mirror+adapter code), **or** runtime adapters per endpoint, **or** a one-time migration to make the domain Pydantic-native.

The mirror approach was tried in the A-Plus.1 brainstorming and dismissed: the domain models (`RetrievalEntry`, `SourceElement`, `HumanActor`, `LLMActor`, `Event`) are already thin projection-result DTOs — wrapping them in mirrors duplicates fields without buying isolation. The third option (Pydantic-native domain) is cleaner long-term:

- Single source of truth — no API/domain divergence
- Pydantic validation lives where invariants belong
- Discriminated unions (`HumanActor | LLMActor`) become declarative
- FastAPI's OpenAPI generation works directly against domain types
- Microsoft-Python-Stack convention (FastAPI + Pydantic) is what reviewer-facing code looks like

## 2. Goals & Non-Goals

### Goals

- Replace `@dataclass(frozen=True)` with `BaseModel(model_config=ConfigDict(frozen=True))` in `goldens.schemas`
- Replace hand-rolled `to_dict` / `from_dict` with Pydantic's `model_dump` / `model_validate` (and `model_dump_json` / `model_validate_json` where appropriate)
- Update all 6 call-sites that consume `to_dict` / `from_dict`: `storage/{log,projection}.py`, `operations/{refine,deprecate}.py`, `creation/{curate,synthetic}.py`
- Preserve byte-equivalent JSONL output for the event log: existing `golden_events_v1.jsonl` files must continue to round-trip identically (re-read → re-write produces the same bytes after key-sort)
- Update tests mechanically; existing test coverage targets (~95%) hold
- Add `pydantic >= 2.5, < 3` as a runtime dependency

### Non-Goals

- **No new functionality.** This PR is pure refactor — same observable behavior, same JSONL format, same exception types, same module APIs.
- **No `Event.payload` typing.** `Event.payload: dict[str, Any]` stays as-is. Discriminated payload typing (`CreatedPayload | RefinedPayload | DeprecatedPayload`) is a separate refactor that belongs to Phase B or later.
- **No API layer.** A-Plus.1 is the next PR; this one only prepares the ground.
- **No CLI changes.** `query-eval curate / synthesise / refine / deprecate / eval / report` keep their argument shapes.

## 3. Schema-by-Schema Plan

### 3.1 `goldens/schemas/base.py`

Current types: `Event`, `HumanActor`, `LLMActor`, `SourceElement`, `Actor` (union alias).

Migration:

```python
# from:
@dataclass(frozen=True)
class HumanActor:
    pseudonym: str
    level: Level
    kind: Literal["human"] = "human"
    def to_dict(self) -> dict[str, Any]: ...
    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> HumanActor: ...

# to:
class HumanActor(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["human"] = "human"
    pseudonym: str
    level: Level
```

Same shape for `LLMActor`. The discriminated union becomes:

```python
Actor = Annotated[HumanActor | LLMActor, Field(discriminator="kind")]
```

`Event`:

```python
class Event(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: str
    timestamp_utc: str
    event_type: EventType
    entry_id: str
    schema_version: int
    payload: dict[str, Any]
```

`SourceElement`:

```python
class SourceElement(BaseModel):
    model_config = ConfigDict(frozen=True)
    document_id: str
    page_number: int
    element_id: str           # bare hash (sans `p{page}-` prefix)
    element_type: ElementType
```

### 3.2 `goldens/schemas/retrieval.py`

`RetrievalEntry`:

```python
class RetrievalEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    entry_id: str
    query: str
    expected_chunk_ids: list[str]
    chunk_hashes: dict[str, str]
    source_element: SourceElement | None
    actor: Actor                                  # discriminated union
    action: CreateAction
    refines: str | None
    refined_by: str | None
    deprecated: bool
    notes: str | None
    schema_version: int
    created_at_utc: str
    deprecated_at_utc: str | None
```

### 3.3 Type aliases / Literals

Stay verbatim — `Level`, `ElementType`, `EventType`, `CreateAction` remain `Literal[...]` definitions.

## 4. Call-Site Migrations

### 4.1 `goldens/storage/log.py`

```python
# from:
line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
# to:
line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
```

Notes on byte-equivalence:
- The current implementation uses `dataclasses.asdict(self)` for `to_dict()`, which preserves field-declaration order. Pydantic v2's `model_dump()` also preserves field-declaration order. As long as the migration keeps the field-declaration order identical between dataclass and Pydantic versions, the resulting dicts have the same key-order.
- The existing code does **not** use `sort_keys=True` — and the migration must not add it, or every existing log line would re-write with reordered keys.
- The `mode="json"` flag is required so nested types (Pydantic-specific types like `HttpUrl`, `datetime`, etc., should they be added later) serialize identically to the dataclass's `asdict` behaviour for the same field types.
- `event.model_dump_json()` is a tempting one-liner replacement, but it bypasses the `mode="json"` control and uses Pydantic's own JSON serializer (slightly different from stdlib `json.dumps` for edge cases like NaN/Infinity, key ordering of nested dicts). We use `json.dumps(model_dump(mode="json"))` for stdlib-equivalent output.

### 4.2 `goldens/storage/projection.py`

```python
# from:
event = Event.from_dict(json.loads(line))
# to:
event = Event.model_validate_json(line)
```

### 4.3 `goldens/operations/refine.py`, `deprecate.py`

Both functions accept `actor: HumanActor | LLMActor` and call `actor.to_dict()` to embed in event payload. Migration:

```python
# from:
actor_dict = actor.to_dict()
# to:
actor_dict = actor.model_dump()
```

### 4.4 `goldens/creation/curate.py`, `synthetic.py`

Both call `entry.to_dict()` or `actor.to_dict()` when assembling event payloads or events. Mechanical replacement.

### 4.5 `goldens/__init__.py`, `goldens/schemas/__init__.py`

Public re-exports stay identical — Pydantic models are drop-in for callers that only access fields.

## 5. JSONL Byte-Compatibility

The event log is the project's most precious artifact (audit-trail, reproducibility, evaluation history). Existing logs must continue to load, and new writes must be byte-equivalent to old writes for the same logical input.

### 5.1 Round-trip test

A regression test reads each fixture JSONL line, parses with Pydantic, dumps via `json.dumps(model.model_dump(mode="json"), ensure_ascii=False)`, and asserts `dumped + "\n" == original_line`. Test runs against:

- `features/goldens/tests/fixtures/*.jsonl` (existing test fixtures)
- A synthetic 50-entry log covering all event types (`created`, `reviewed`, `deprecated`, `refined` if it exists), all actor types, all action variants

### 5.2 Field ordering

Pydantic v2 preserves field-declaration order in `model_dump`. The existing dataclass implementation uses `dataclasses.asdict` which also preserves field-declaration order. Therefore: **field-declaration order in the new BaseModel definitions must match the existing dataclass field-declaration order verbatim**, or the JSONL output will diverge.

This is a hard rule of the migration — verified by the round-trip test (Section 5.1). New fields added in future PRs go at the end of their model, like before.

### 5.3 None vs missing

`to_dict` historically emitted `null` for `None` fields. Pydantic v2 default is also `null` (not omit). No change.

## 6. Dependency-Layer

`pydantic >= 2.5, < 3` is added as a dependency of `features/goldens/`. `core/` is **not** updated — it doesn't depend on `goldens`, so no transitive ripple.

`features/evaluators/chunk_match/` already depends on `goldens` and will inherit Pydantic transitively. It does not directly use the schemas' `to_dict` / `from_dict` (it uses `iter_active_retrieval_entries` from projection), so its code stays untouched. Its test fixtures may need updating if any directly construct `RetrievalEntry` from kwargs (mechanical: `RetrievalEntry(**kwargs)` still works in Pydantic).

## 7. Test Migration

### 7.1 Tests that touch `to_dict` / `from_dict` directly

- `features/goldens/tests/test_base.py` (covers `Event`, `HumanActor`, `LLMActor`, `SourceElement`)
- `features/goldens/tests/test_retrieval.py` (covers `RetrievalEntry`)
- A few storage tests in `test_storage_log.py` / `test_storage_log_bulk.py` / `test_storage_projection.py` that call `Event.from_dict` for fixtures

Mechanical: replace `obj.to_dict()` with `obj.model_dump(mode="json")` (the `mode="json"` is essential for compat); replace `Cls.from_dict(d)` with `Cls.model_validate(d)`.

### 7.2 Tests that construct schemas via kwargs

No change. `HumanActor(pseudonym="alice", level="phd")` works in both dataclass and Pydantic.

### 7.3 Tests that check immutability

Dataclass `frozen=True` raises `dataclasses.FrozenInstanceError`. Pydantic frozen raises `pydantic.ValidationError`. Affected tests (if any) need a `pytest.raises` exception-class update.

### 7.4 Tests that check JSONL round-trip byte-equivalence

New test (Section 5.1) added explicitly.

### 7.5 Coverage

Goldens-suite coverage is currently 95.94% (post PR #17). Migration is mechanical; coverage should stay within ±1%.

## 8. Migration Strategy

### 8.1 Big-bang vs gradual

Big-bang. Pydantic vs dataclass cannot coexist in the same `BaseModel`-vs-`@dataclass`-frozen surface — `Event(payload=...)` is constructed in many places, and a half-migrated state would force callers to know whether they're holding the old or new type. One PR, all schemas migrated, all call-sites updated, all tests green.

### 8.2 PR ordering

1. **This PR** (`refactor/pydantic-core-migration`) — migration only, no new features.
2. **Next** (`feat/a-plus-1-backend`) — A-Plus.1 (FastAPI HTTP API), built on the migrated schemas.

The two PRs are sequenced, not parallel — A-Plus.1 imports the migrated schemas directly.

## 9. Verification Checklist

Before merging the migration PR:

- [ ] Full test suite green: `pytest features/goldens/tests features/evaluators/chunk_match/tests`
- [ ] Coverage holds at ≥95%
- [ ] Ruff + mypy + format pre-commit hooks pass
- [ ] JSONL byte-equivalence test green against all fixture logs
- [ ] Existing `outputs/smoke-test-tragkorb/` event log loads without error after migration
- [ ] CLI smoke: `query-eval curate --doc smoke-test-tragkorb` (interactive — pick one element, type one question, save, quit) writes an event that round-trips identically
- [ ] CLI smoke: `query-eval synthesise --doc smoke-test-tragkorb --dry-run --llm-model gpt-4o-mini` returns 0 with `prompt_tokens_estimated > 0`
- [ ] CLI smoke: `query-eval eval` (chunk_match) runs against the migrated event log and produces a metrics report

## 10. Rollback

If the migration introduces unforeseen regressions, the rollback is `git revert <merge-commit>`. The event log on disk is untouched — only the code that reads/writes it changes. Old code re-reads old JSONL identically.

## 11. Decision Log

| # | Topic | Decision |
|---|---|---|
| M1 | Pydantic version | v2.5+; v2 is stable, v3 is unreleased — pin `>= 2.5, < 3` |
| M2 | Migration scope | All `goldens.schemas` types in one PR; no half-migration |
| M3 | `Event.payload` typing | Stays `dict[str, Any]`; discriminated payload typing is out of scope |
| M4 | JSONL byte-equivalence | Required — protects existing logs and downstream tooling |
| M5 | Pydantic in `core/` | Not added; `core/` does not depend on `goldens`, no transitive need |
| M6 | Test migration | Mechanical; new round-trip test added; existing coverage held |
| M7 | Frozen-exception type | Tests updated for `pydantic.ValidationError` instead of `dataclasses.FrozenInstanceError` where applicable |

## 12. Open Questions

None. The migration is mechanical with one constraint (byte-equivalence) and one validation gate (full smoke + JSONL round-trip).
