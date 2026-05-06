from pathlib import Path

from local_pdf.provenienz.storage import (
    Edge,
    Node,
    SessionMeta,
    append_edge,
    append_node,
    read_meta,
    read_session,
    write_meta,
)


def test_append_then_read_round_trips_one_node(tmp_path: Path):
    session_dir = tmp_path / "sess1"
    n = Node(node_id="n1", session_id="s1", kind="chunk", payload={"text": "hi"}, actor="human")
    append_node(session_dir, n)
    nodes, edges = read_session(session_dir)
    assert len(nodes) == 1
    assert nodes[0].node_id == "n1"
    assert nodes[0].kind == "chunk"
    assert nodes[0].payload["text"] == "hi"
    assert edges == []


def test_append_then_read_round_trips_edge(tmp_path: Path):
    session_dir = tmp_path / "sess1"
    append_node(
        session_dir, Node(node_id="n1", session_id="s1", kind="chunk", payload={}, actor="human")
    )
    append_node(
        session_dir, Node(node_id="n2", session_id="s1", kind="claim", payload={}, actor="llm:vllm")
    )
    append_edge(
        session_dir,
        Edge(
            edge_id="e1",
            session_id="s1",
            from_node="n2",
            to_node="n1",
            kind="extracts-from",
            reason=None,
            actor="llm:vllm",
        ),
    )
    nodes, edges = read_session(session_dir)
    assert len(nodes) == 2
    assert len(edges) == 1
    assert edges[0].kind == "extracts-from"


def test_meta_round_trip(tmp_path: Path):
    session_dir = tmp_path / "sess1"
    meta = SessionMeta(session_id="s1", slug="doc-a", root_chunk_id="p3-b4", status="open")
    write_meta(session_dir, meta)
    got = read_meta(session_dir)
    assert got is not None
    assert got.session_id == "s1"
    assert got.status == "open"


def test_read_session_returns_empty_when_dir_missing(tmp_path: Path):
    nodes, edges = read_session(tmp_path / "does-not-exist")
    assert nodes == []
    assert edges == []


def test_new_id_is_unique_and_lexically_sortable():
    """Two ids generated in order: same millisecond shares the 10-char
    time prefix (random tail breaks the tie either way), different
    millisecond strictly increases on the prefix. Sleep across the ms
    boundary so the assertion isn't flaky."""
    import time

    from local_pdf.provenienz.storage import new_id

    a = new_id()
    time.sleep(0.005)
    b = new_id()
    assert a != b
    assert len(a) == 26
    # Time prefix (first 10 chars) is monotonic across ms boundaries.
    assert b[:10] > a[:10]


def test_session_dir_layout(tmp_path: Path):
    from local_pdf.provenienz.storage import session_dir

    d = session_dir(tmp_path, "my-slug", "01H123")
    assert d == tmp_path / "my-slug" / "provenienz" / "01H123"


def test_tombstone_hides_node_and_dangling_edges(tmp_path: Path):
    from local_pdf.provenienz.storage import append_tombstone

    sd = tmp_path / "sess1"
    append_node(sd, Node(node_id="A", session_id="s1", kind="chunk", payload={}, actor="human"))
    append_node(sd, Node(node_id="B", session_id="s1", kind="claim", payload={}, actor="llm"))
    append_node(sd, Node(node_id="C", session_id="s1", kind="claim", payload={}, actor="llm"))
    append_edge(
        sd,
        Edge(
            edge_id="e1",
            session_id="s1",
            from_node="B",
            to_node="A",
            kind="extracts-from",
            reason=None,
            actor="llm",
        ),
    )
    append_edge(
        sd,
        Edge(
            edge_id="e2",
            session_id="s1",
            from_node="C",
            to_node="A",
            kind="extracts-from",
            reason=None,
            actor="llm",
        ),
    )
    append_tombstone(sd, "B")
    nodes, edges = read_session(sd)
    assert {n.node_id for n in nodes} == {"A", "C"}
    # Edge e1 (B → A) is hidden because B is gone; e2 (C → A) survives.
    assert {e.edge_id for e in edges} == {"e2"}


def test_cascade_helper_walks_dependency_chain():
    """Smoke: deleting a chunk should cascade to claims under it, tasks
    under those claims, results under those tasks, evaluations of those
    results, plus any anchored proposal+decision pair."""
    from local_pdf.api.routers.admin.provenienz import _collect_cascade

    nodes = [
        Node(node_id="chunk1", session_id="s", kind="chunk", payload={}, actor="h"),
        Node(node_id="claim1", session_id="s", kind="claim", payload={}, actor="h"),
        Node(
            node_id="task1",
            session_id="s",
            kind="task",
            payload={"focus_claim_id": "claim1"},
            actor="h",
        ),
        Node(
            node_id="sr1",
            session_id="s",
            kind="search_result",
            payload={"task_node_id": "task1"},
            actor="h",
        ),
        Node(node_id="eval1", session_id="s", kind="evaluation", payload={}, actor="h"),
        Node(
            node_id="prop1",
            session_id="s",
            kind="action_proposal",
            payload={"anchor_node_id": "claim1"},
            actor="h",
        ),
        Node(node_id="dec1", session_id="s", kind="decision", payload={}, actor="h"),
        Node(node_id="bystander", session_id="s", kind="claim", payload={}, actor="h"),
    ]
    edges = [
        Edge(
            edge_id="e1",
            session_id="s",
            from_node="claim1",
            to_node="chunk1",
            kind="extracts-from",
            reason=None,
            actor="h",
        ),
        Edge(
            edge_id="e2",
            session_id="s",
            from_node="task1",
            to_node="claim1",
            kind="verifies",
            reason=None,
            actor="h",
        ),
        Edge(
            edge_id="e3",
            session_id="s",
            from_node="sr1",
            to_node="task1",
            kind="candidates-for",
            reason=None,
            actor="h",
        ),
        Edge(
            edge_id="e4",
            session_id="s",
            from_node="eval1",
            to_node="sr1",
            kind="evaluates",
            reason=None,
            actor="h",
        ),
        Edge(
            edge_id="e5",
            session_id="s",
            from_node="dec1",
            to_node="prop1",
            kind="decided-by",
            reason=None,
            actor="h",
        ),
    ]
    cascade = _collect_cascade("chunk1", nodes, edges)
    assert cascade == {"chunk1", "claim1", "task1", "sr1", "eval1", "prop1", "dec1"}
    assert "bystander" not in cascade
