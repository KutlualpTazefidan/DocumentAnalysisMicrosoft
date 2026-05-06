"""Tool / capability registry for the Provenienz agent.

Each tool is a named capability the Planner can pick when scheduling a step.
v1 ships one enabled tool (``InDocSearcher`` — already wired into the
``search`` step) plus stubs for tools we anticipate but haven't built. The
stubs are visible in the Agent tab + selectable by the Planner only when
``enabled=True``.

This module is the single source of truth for what the system *can* do —
adding a new tool means dropping a ``ToolInfo`` entry here, not chasing
frontend strings.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolInfo:
    """Static metadata about a tool. Surfaced via /api/admin/provenienz/tools
    for the Agent tab + ingested by the Planner so it knows what's available.
    """

    name: str  # stable id; used by Planner output and step routing
    label: str  # human-readable name for the UI
    description: str  # one sentence on what it does
    when_to_use: str  # one sentence on when the Planner should pick it
    scope: str  # "in-doc" | "cross-doc" | "external" | "compute" | "extract"
    cost_hint: str  # "schnell" | "moderat" | "teuer" | "extern-API"
    enabled: bool  # if False: Planner sees it but cannot select it
    used_by: list[str] = field(default_factory=list)  # step_kinds that can call it


# v1 registry. Add a new tool by appending here — the agent-info endpoint
# and the Tools section of the Agent tab pick it up automatically.
TOOL_REGISTRY: list[ToolInfo] = [
    ToolInfo(
        name="in_doc_searcher",
        label="InDocSearcher",
        description="BM25-Suche im selben Quell-Dokument. Schnell, lokal, deterministisch.",
        when_to_use=("Default für search-Step. Findet Quellen, die im selben Dokument liegen."),
        scope="in-doc",
        cost_hint="schnell",
        enabled=True,
        used_by=["search"],
    ),
    ToolInfo(
        name="cross_doc_searcher",
        label="CrossDocSearcher",
        description="BM25 über alle indizierten Dokumente im Korpus.",
        when_to_use=(
            "Wenn in-doc-Suche keine passenden Quellen lieferte oder die Aussage "
            "auf andere Dokumente verweist."
        ),
        scope="cross-doc",
        cost_hint="moderat",
        enabled=False,
        used_by=["search"],
    ),
    ToolInfo(
        name="semantic_searcher",
        label="SemanticSearcher",
        description="Embedding-Suche statt Keyword-BM25.",
        when_to_use=("Wenn keyword-basierte Suche wegen Synonymen / Paraphrasen leer bleibt."),
        scope="in-doc",
        cost_hint="moderat",
        enabled=False,
        used_by=["search"],
    ),
    ToolInfo(
        name="azure_searcher",
        label="AzureSearcher",
        description="Azure Cognitive Search via vorhandenes pipelines/microsoft.",
        when_to_use="Wenn der Microsoft-Index bessere Coverage verspricht als der lokale Korpus.",
        scope="external",
        cost_hint="extern-API",
        enabled=False,
        used_by=["search"],
    ),
    ToolInfo(
        name="numeric_extractor",
        label="NumericExtractor",
        description="Spezial-LLM-Call der gezielt Zahlen + Einheiten + Kontext extrahiert.",
        when_to_use=(
            "Wenn der Claim numerisch ist und der allgemeine extract_claims-Schritt "
            "zu viel Boilerplate aufnimmt."
        ),
        scope="extract",
        cost_hint="moderat",
        enabled=False,
        used_by=["extract_claims"],
    ),
    ToolInfo(
        name="calculator",
        label="Calculator",
        description="Zahlen-Verifikation: Summen, Mittelwerte, Einheiten-Umrechnung.",
        when_to_use="Wenn evaluate eine Rechenoperation prüfen muss bevor ein Verdict steht.",
        scope="compute",
        cost_hint="schnell",
        enabled=False,
        used_by=["evaluate"],
    ),
]


def list_tools() -> list[ToolInfo]:
    """Return a copy of the registry. Pure metadata — no side effects."""
    return list(TOOL_REGISTRY)


def get_tool(name: str) -> ToolInfo | None:
    """Lookup by stable name. Returns None for unknown names."""
    for t in TOOL_REGISTRY:
        if t.name == name:
            return t
    return None


def tools_for_step(step_kind: str, *, enabled_only: bool = False) -> list[ToolInfo]:
    """Tools that can be invoked from a particular step kind. Useful for
    the Planner: at extract_claims it sees only [InDocSearcher (off),
    NumericExtractor (off)] etc."""
    out = [t for t in TOOL_REGISTRY if step_kind in t.used_by]
    if enabled_only:
        out = [t for t in out if t.enabled]
    return out
