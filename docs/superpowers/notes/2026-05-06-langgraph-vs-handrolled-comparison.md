# Provenienz: LangGraph vs. Hand-Rolled — Decision Notes & Future Comparison

**Status:** v1 ships hand-rolled (this PR #39). LangGraph parallel implementation deferred. This doc captures *why*, *what we'd build if we changed our mind*, and *what to measure when comparing the two pipelines side-by-side*.

**Date written:** 2026-05-06
**Companion docs:** [`specs/2026-05-05-provenienzanalyse-design.md`](../specs/2026-05-05-provenienzanalyse-design.md), [`plans/2026-05-05-provenienzanalyse.md`](../plans/2026-05-05-provenienzanalyse.md)

---

## 1. The question

Provenienz is an agent loop with mandatory human-in-the-loop at every fork: every LLM step emits an `action_proposal`, the human resolves via `/decide`. Could LangGraph replace the hand-rolled implementation? If we built both, what would we measure to pick a long-term winner?

## 2. v1 decision: hand-rolled

Four reasons we picked hand-rolled for v1:

1. **Audit trail is the product, not a side effect.** Spec says `events.jsonl` per session is the source of truth — human-readable, grep-able, one event per line. LangGraph's checkpointer stores msgpack BLOBs in SQLite/Postgres; same data but not shell-inspectable.
2. **The spec already dictated the pattern.** Every step emits an `action_proposal`, every resolution is a `decision` Node. That's a fixed-shape state machine, not an open agentic loop. LangGraph's value-add — letting an LLM pick the next node from a tool registry — isn't what we want.
3. **`local_pdf/llm.py` already exists.** `get_llm_client()` returns an `LLMClient` (vLLM / Azure / Ollama). LangChain's tool ecosystem would have been a sidegrade with deprecation churn we don't need.
4. **No tool-calling, no multi-agent, no streaming-to-UI yet.** The features LangGraph would actually save us code on aren't required for v1.

Net cost of hand-rolled: ~1500 LOC of router + storage + step dispatch + 93 tests, reusing existing LLM machinery.

## 3. What LangGraph actually provides

For honest comparison, here's what the framework gives you out of the box:

| Primitive | What it does | Maps to our model? |
|---|---|---|
| `StateGraph[State]` | Typed state object; nodes mutate it | ~70%. Our state = Node/Edge log. Theirs = TypedDict snapshot. |
| `add_node(name, fn)` | Register a function as a graph node | Yes — one per step_kind. |
| `add_edge(a, b)` / `add_conditional_edges` | Static + dynamic routing | Yes — our `step_kind` dispatch in `/decide`. |
| `interrupt(payload)` | Pause graph, persist state, return payload to caller | **Best fit.** Our `action_proposal` IS this. |
| `Command(resume=value)` | Resume from interrupt with human input | Our `/decide` POST. |
| `BaseCheckpointSaver` (Sqlite/Postgres/Memory/Redis) | Persists state at every step | Replaces our `events.jsonl` if you accept their format. |
| `astream_events()` | Async iterator yielding per-node events | Replaces hand-rolled SSE. |
| `Send(node_name, state)` | Spawn parallel branches | Useful if we ever evaluate N search_results in parallel. |
| Subgraphs / hierarchical agents | Compose graphs as nodes | Overkill today. |
| Multi-agent orchestration | Send/Receive between agents | If we ever want Searcher debating Evaluator. |

## 4. What we'd build if we did the LangGraph parallel pipeline

File-by-file sketch for a parallel `local_pdf/provenienz_lg/` package:

### 4.1 State definition

```python
# provenienz_lg/state.py
from typing import TypedDict, Annotated
from operator import add

class ProvenienzState(TypedDict):
    session_id: str
    slug: str
    nodes: Annotated[list[Node], add]   # accumulator — all nodes ever seen
    edges: Annotated[list[Edge], add]
    pending_proposal_id: str | None     # set when interrupted, None when resumed
```

### 4.2 The graph

```python
# provenienz_lg/graph.py
from langgraph.graph import StateGraph
from langgraph.types import interrupt, Command

def extract_claims_node(state: ProvenienzState) -> dict:
    chunk = find_node(state, "chunk", at=anchor_id)
    proposal = build_proposal(chunk, "extract_claims")
    state["nodes"].append(proposal)
    # interrupt = "ask the human"
    decision = interrupt(proposal.to_dict())
    # resume here once /decide POSTed
    return {"nodes": [decision] + spawn_claims(decision, proposal)}

g = StateGraph(ProvenienzState)
g.add_node("extract_claims", extract_claims_node)
g.add_node("formulate_task", formulate_task_node)
g.add_node("search", search_node)
g.add_node("evaluate", evaluate_node)
g.add_node("propose_stop", propose_stop_node)
g.add_conditional_edges(
    "extract_claims",
    route_after_extract,    # picks formulate_task or propose_stop
    {"formulate_task": "formulate_task", "propose_stop": "propose_stop", "end": END},
)
# ...
graph = g.compile(checkpointer=our_checkpointer)
```

### 4.3 The custom checkpointer (this is where the inversion lives)

```python
# provenienz_lg/checkpointer.py
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata

class JsonlSaver(BaseCheckpointSaver):
    """Writes LangGraph checkpoints as our domain-specific events.jsonl
    so the audit story stays human-grep-able. Translation between
    LangGraph's 'full state snapshot' model and our 'one event per
    Node/Edge' model happens here."""

    def __init__(self, data_root: Path):
        self.data_root = data_root

    def put(self, config, checkpoint: Checkpoint, metadata: CheckpointMetadata, *, ...) -> RunnableConfig:
        session_id = config["configurable"]["thread_id"]
        sd = session_dir(self.data_root, slug_from_config(config), session_id)
        # checkpoint["channel_values"]["nodes"] is the accumulator;
        # diff against the previous snapshot, append only the new ones.
        prev = self._latest_snapshot(sd)
        for new_node in diff(prev, checkpoint):
            append_node(sd, new_node)
        # Also write LangGraph's own checkpoint shape so resume() works.
        self._write_lg_checkpoint(sd, checkpoint, metadata)
        return config

    def get_tuple(self, config) -> CheckpointTuple | None: ...
    def list(self, config, *, before=None, limit=None, filter=None): ...
    # plus aput, aget_tuple, alist for async
```

The `_write_lg_checkpoint` line is the cost: we have to write a *second* representation alongside our domain events, because LangGraph's `get_tuple` needs to deserialize *its* checkpoint shape on resume. So we end up with both:

- `events.jsonl` (our human-readable log — read-only after write)
- `lg_checkpoints.jsonl` or sqlite `lg.db` (LangGraph's shape — read on resume)

That's the "two state stores" tax.

### 4.4 The HTTP layer

Routes change shape — `/decide` becomes `Command(resume=value)`:

```python
# provenienz_lg/routes.py
@router.post("/sessions/{session_id}/decide")
async def decide(session_id: str, body: DecideRequest, request: Request):
    cfg = {"configurable": {"thread_id": session_id}}
    result = graph.invoke(Command(resume=body.dict()), config=cfg)
    # 'result' = state at next interrupt OR final state if graph ended
    return result_to_http(result)
```

Step routes (`/extract-claims`, `/formulate-task`, etc.) collapse into a single `/run` endpoint that calls `graph.invoke(initial_state)` and returns at the first `interrupt()`. The user no longer chooses *which step to run* — the graph routing decides. This is a UX shift: more autonomous-feeling, less explicit.

### 4.5 The frontend

Streaming becomes feasible:

```ts
// hooks/useProvenienzStream.ts
const events = await fetchEventSource(`/sessions/${id}/stream`, ...);
events.onmessage = (e) => {
  const evt = JSON.parse(e.data);
  if (evt.type === "node_added") addNodeToCanvas(evt.node);
  if (evt.type === "interrupt") openProposalPanel(evt.payload);
};
```

The Canvas no longer waits for `useQuery` to refetch the whole session — nodes appear live as the graph runs. That's a genuine UX win.

## 5. What we'd gain (concrete, measurable)

| Gain | Today | With LangGraph |
|---|---|---|
| **Streaming UI updates** | None — full session refetch on every action | Per-node SSE; nodes appear live |
| **Branch/replay** | Hand-rolled (read events up to N, append from there) | `graph.update_state(config, ..., as_node=X)` — built-in time travel |
| **Topology visualization** | `git log` + reading code | `graph.get_graph().draw_mermaid()` — auto-renders |
| **Multi-agent pivot** | Major refactor | `Send` API + add nodes |
| **Autonomous mode pivot** | Replace `/decide` calls with auto-resume | Flip a flag per node — `interrupt()` becomes optional |
| **Test fixtures** | Manual `_FakeClient` | `MemorySaver` + `with_config({"thread_id": "test"})` |

## 6. What we'd pay (concrete, measurable)

| Cost | Magnitude |
|---|---|
| **Custom checkpointer adapter** | ~150-250 LOC for `JsonlSaver` + tests + diff logic |
| **Two state stores** | Disk: 2x writes per event. Consistency: if our events.jsonl write succeeds and LG checkpoint fails (or vice versa), session is corrupt. Need atomic write or recovery code. |
| **LangChain/LangGraph deps** | Pulls in ~30 transitive packages, version churn (LangGraph is pre-1.0 as of writing — breaking changes between minors are normal) |
| **Audit UX regression** | `grep` → custom Python helper (~10 LOC). Real for compliance scenarios. |
| **Onboarding cost** | New devs need to learn LangGraph mental model on top of FastAPI |
| **Coupling to internal protocol** | Their checkpoint shape isn't a stable public API in pre-1.0; minor upgrades may break the adapter |
| **Test rewrite** | 93 tests today are tightly coupled to `events.jsonl` storage. Migration ≈ rewrite. |

## 7. The "inverts the abstraction" point in detail

Normal LangGraph contract: *you author business logic, framework handles persistence + routing + resume*. The high-level promise is "give me a graph, I'll persist + run + interrupt + resume."

When you swap their checkpointer for one that writes *your* domain log, the relationship reverses: *the framework calls back into your storage code at every step*. Their "checkpoint = full state snapshot" model has to be translated to our "event = single Node or Edge delta" model on every save. You're writing infrastructure for them to consume, not consuming theirs.

Tactical cost: ~150-250 LOC of adapter.
Strategic cost: **coupling to their internal protocol.** A v0.2→v0.3 upgrade can break the adapter; you debug their internals to fix it. You ship and maintain framework infrastructure, instead of framework saving you maintenance.

## 8. Decision triggers — when to build the parallel version

Build the LangGraph version *if any of these become true*:

- [ ] **Manual SSE/WebSocket glue exceeds ~200 LOC** — streaming is the biggest concrete win
- [ ] **Branch-replay UX requested** — "rewind this session, take a different decision at step N, see the alternate timeline"
- [ ] **Multi-agent ask** — Searcher critiques Evaluator's verdict, or Approach-A vs Approach-B run in parallel and compare
- [ ] **Autonomous mode requirement** — "let the agent run unattended on a corpus, only escalate when confidence < threshold"
- [ ] **Compliance accepts non-grep audit** — auditor signs off on "we have a Python tool that exports to CSV on demand" rather than requiring shell-level inspectability
- [ ] **A real third pipeline emerges** — if Provenienz becomes one of three+ similar agent loops in the codebase, the framework starts paying for itself across consumers

Until then, the hand-rolled version's simpler operational story wins.

## 9. Comparison criteria (when both pipelines exist)

If we build the parallel `provenienz_lg/` package, measure:

### Code volume
- LOC backend (router + storage + helpers)
- LOC frontend (hooks + components)
- Test count + LOC
- Dep count delta (new packages pulled in)

### Operational
- Disk usage per session (events.jsonl bytes vs. events.jsonl + LG checkpoint bytes)
- Latency: median + p99 for `/decide` round-trip
- Restart story: time from server crash → session resumable
- Audit query: time to answer "show me every override with reason matching X" (shell vs. tool)

### Developer ergonomics
- Time to add a new step_kind (LOC + files touched + test cost)
- Time to add a new node kind (open-string contract today)
- Time for a new dev to ship their first PR against the codebase
- Frequency of framework-version upgrade pain

### UX
- Time-to-first-node-render after `/decide` POST (refetch latency vs. SSE)
- Branch/replay: present in LG version, absent in hand-rolled
- Topology visualization: present in LG, absent in hand-rolled

### Correctness / robustness
- 93+ test coverage parity
- Atomic-write story: how each handles "events.jsonl write succeeds, downstream fails"
- Concurrent /decide handling on same session

## 10. Migration path if we ever flip

If LangGraph wins long-term, migration is *not* a rewrite — it's parallel build + cutover:

1. Build `provenienz_lg/` alongside `provenienz/` (no deletion yet).
2. Mount under a different route prefix: `/api/admin/provenienz_lg/`.
3. Frontend tab gets a "Pipeline: hand-rolled / LangGraph" toggle.
4. Run both for ~3 sessions; compare outputs node-by-node.
5. If LG passes the criteria above for 4 weeks, redirect new sessions to LG.
6. Keep hand-rolled in read-only mode for old sessions; new sessions are LG-only.
7. After 6 months with no regressions, delete the hand-rolled package.

The `events.jsonl` format would persist across both — that's the audit-stable layer regardless of framework. Old sessions stay grep-able forever.

## 11. Honest summary

LangGraph could do this — it would not be "fighting the framework," because `interrupt()` is first-class for human-in-the-loop. The 70% that maps cleanly is real. The 30% friction (two state stores, audit UX, framework version coupling) is also real but not fatal.

For v1's volume of work and v1's compliance story, the simpler hand-rolled version wins. The framework's value-add is mostly in features we don't ship yet (streaming, branch/replay, multi-agent). When those features become real requirements, build the parallel version — don't refactor in place.

## Appendix A: relevant LangGraph docs

- StateGraph + interrupt: https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
- Checkpointer interface: https://langchain-ai.github.io/langgraph/reference/checkpoints/
- astream_events: https://langchain-ai.github.io/langgraph/concepts/streaming/
- Send API for parallel: https://langchain-ai.github.io/langgraph/concepts/low_level/#send

(Links current as of 2026-05-06; verify versions before relying on specifics — pre-1.0 churn.)

## Appendix B: this conversation's source quotes

For traceability — the points above were synthesized from this PR's brainstorming dialogue:

- "agentic framework — hand-rolled, no LangChain/LangGraph" with 4 reasons
- "What you'd get for free: time-travel/branching, graph topology visualization, token-streaming"
- "What you'd fight: the every-fork-interrupts pattern is supported but the framework isn't optimized for it"
- "Where it'd shine: multi-agent, hybrid auto-by-default mode"
- "70% match, not 10/90% as I implied earlier"
- "Worth revisiting when manual SSE wiring grows past ~200 LOC"
- "lose grep-able audit" — qualified to mean shell-level inspectability, not data preservation
- "inverts the abstraction" — framework calls back into your storage code instead of providing storage for you
