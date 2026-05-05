def test_build_proposal_node_emits_action_proposal_kind():
    from local_pdf.provenienz.llm import (
        ActionOption,
        ActionProposalPayload,
        build_proposal_node,
    )

    payload = ActionProposalPayload(
        step_kind="search",
        anchor_node_id="n1",
        recommended=ActionOption(label="bm25 search", args={"q": "x"}),
        alternatives=[],
        reasoning="...",
        guidance_consulted=[],
    )
    n = build_proposal_node(session_id="s1", actor="llm:vllm", payload=payload)
    assert n.kind == "action_proposal"
    assert n.session_id == "s1"
    assert n.actor == "llm:vllm"
    p = n.payload
    assert p["step_kind"] == "search"
    assert p["anchor_node_id"] == "n1"
    assert p["recommended"]["label"] == "bm25 search"
    assert p["recommended"]["args"] == {"q": "x"}
    assert p["alternatives"] == []
    assert p["reasoning"] == "..."
    assert p["guidance_consulted"] == []
    # Node fields are populated.
    assert len(n.node_id) == 26
    assert n.created_at == ""  # storage layer fills this on append


def test_build_proposal_node_serialises_alternatives_and_guidance():
    from local_pdf.provenienz.llm import (
        ActionOption,
        ActionProposalPayload,
        GuidanceRef,
        build_proposal_node,
    )

    payload = ActionProposalPayload(
        step_kind="extract_claims",
        anchor_node_id="chunk-id",
        recommended=ActionOption(label="A", args={"claims": ["c1"]}),
        alternatives=[
            ActionOption(label="B", args={"claims": []}),
            ActionOption(label="C", args={"claims": ["c2", "c3"]}),
        ],
        reasoning="weighed both",
        guidance_consulted=[
            GuidanceRef(kind="reason", id="r-1", summary="prefer tables"),
            GuidanceRef(kind="approach", id="a-1", summary="numerical-claim-v1"),
        ],
    )
    n = build_proposal_node(session_id="s", actor="llm:azure", payload=payload)
    p = n.payload
    assert len(p["alternatives"]) == 2
    assert p["alternatives"][1]["args"]["claims"] == ["c2", "c3"]
    assert len(p["guidance_consulted"]) == 2
    assert p["guidance_consulted"][0]["kind"] == "reason"
    assert p["guidance_consulted"][1]["summary"] == "numerical-claim-v1"


def test_resolve_provider_uses_argument_first(monkeypatch):
    from local_pdf.provenienz.llm import resolve_provider

    monkeypatch.setenv("PROVENIENZ_DEFAULT_PROVIDER", "envvar")
    assert resolve_provider("vllm") == "llm:vllm"
    assert resolve_provider("azure") == "llm:azure"


def test_resolve_provider_falls_back_to_env(monkeypatch):
    from local_pdf.provenienz.llm import resolve_provider

    monkeypatch.setenv("PROVENIENZ_DEFAULT_PROVIDER", "azure")
    assert resolve_provider(None) == "llm:azure"
    assert resolve_provider("") == "llm:azure"


def test_resolve_provider_falls_back_to_vllm_when_no_env(monkeypatch):
    from local_pdf.provenienz.llm import resolve_provider

    monkeypatch.delenv("PROVENIENZ_DEFAULT_PROVIDER", raising=False)
    assert resolve_provider(None) == "llm:vllm"
