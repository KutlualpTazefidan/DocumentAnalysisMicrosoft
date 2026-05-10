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
    # Concrete trigger heuristics injected into the Planner prompt — tells
    # the agent *exactly* when to capability_request this tool by its right
    # name. More specific than ``when_to_use`` (which is a one-sentence
    # human description) — this is the agent's playbook entry.
    agent_hint: str = ""


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
        agent_hint=(
            "Default-Tool im /search-Step. KEIN capability_request nötig — wähle "
            "einfach executable_step name='search'."
        ),
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
        agent_hint=(
            "capability_request mit name='CrossDocSearcher' wenn die Aussage explizit "
            "auf andere Dokumente verweist ('in [3]', 'gemäß DIN', 'siehe Anhang A', "
            "Zitate, Quellenangaben) ODER wenn InDocSearcher leer geblieben wäre und "
            "das Thema offensichtlich aus einem Geschwister-Dokument stammt."
        ),
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
        agent_hint=(
            "capability_request mit name='SemanticSearcher' wenn die Aussage "
            "umschriebene Konzepte enthält die im Korpus mit anderen Wörtern stehen "
            "(z.B. 'Heizleistung' vs. 'Wärmeerzeugung'). InDocSearcher findet das "
            "wegen BM25-Lexikon nicht."
        ),
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
        agent_hint=(
            "capability_request mit name='AzureSearcher' wenn die Aussage einen "
            "Kontext erwähnt der wahrscheinlich im Microsoft-Index liegt aber nicht "
            "im lokalen Korpus (firmen-interne Doks, externe Spezifikationen)."
        ),
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
        agent_hint=(
            "capability_request mit name='NumericExtractor' bei Chunks mit dichten "
            "Zahlen + Einheiten (Datenblätter, Tabellen, Spezifikationen). Bei "
            "Fließtext: lieber regulär executable_step name='extract_claims'."
        ),
    ),
    ToolInfo(
        name="calculator",
        label="Calculator",
        description=(
            "Deterministische Zahlen-Verifikation. Operationen: 'compare' "
            "(strikte Gleichheit von (Wert, Einheit)-Paaren), 'sum' "
            "(Summen mit konsistenter Einheit). Ersetzt LLM-In-The-Head-"
            "Mathematik durch echten Code. Toleranzen sind nicht "
            "eingebaut — die fachliche Bewertung einer Differenz ist "
            "Domain-Sache (Skills entscheiden)."
        ),
        when_to_use=(
            "Wenn ein search_result und seine zu prüfende Aussage Zahlen "
            "mit Einheit enthalten und ein deterministischer Wert-Vergleich "
            "vor evaluate gewünscht ist. Wird NICHT mehr automatisch in "
            "evaluate aufgerufen — der Agent / User muss ihn explizit "
            "anstoßen."
        ),
        scope="compute",
        cost_hint="schnell",
        enabled=True,
        used_by=["search_result", "evaluate"],
        agent_hint=(
            "capability_request mit name='Calculator' im next_step "
            "wenn der Anker ein search_result ist UND sowohl Aussage als "
            "auch Treffer-Text Zahlen mit Einheit enthalten, deren "
            "exakte Übereinstimmung den Verdict beeinflussen würde. "
            "Ausführung: User triggert per Knopf am search_result-Tile "
            "ODER Auto-Executor postet "
            "/api/admin/provenienz/sessions/{id}/calculator-on-result "
            "mit search_result_node_id. Ergebnis landet als "
            "tool_annotation Node am Treffer und wird automatisch in den "
            "nächsten evaluate-Prompt eingespeist."
        ),
    ),
    ToolInfo(
        name="bib_file_matcher",
        label="BibFileMatcher",
        description=(
            "Schlägt eine Bibliography-Citation gegen die meta.json aller "
            "Slugs im data_root nach. Token-Overlap, kein BM25 — schnell, "
            "deterministisch, no LLM."
        ),
        when_to_use=(
            "Wenn ein RegisterLookup-Treffer kind=bibliography liefert und "
            "der Agent prüfen will, ob das zitierte Dokument bereits im "
            "lokalen Korpus liegt."
        ),
        scope="cross-doc",
        cost_hint="schnell",
        enabled=True,
        used_by=["search"],
        agent_hint=(
            "Reactive: feuert automatisch im register_lookup-Endpoint wenn "
            "kind=bibliography. Output landet als corpus_match Feld am Hit. "
            "Kein manueller capability_request nötig."
        ),
    ),
    ToolInfo(
        name="register_lookup",
        label="RegisterLookup",
        description=(
            "Konsolidiertes Verzeichnis (Inhalts-/Tabellen-/Abbildungs-/"
            "Literaturverzeichnis) als strukturierte Liste mit Markdown-Tabelle. "
            "Nutze für Cross-Reference-Auflösung — NICHT für allgemeine Inhaltssuche."
        ),
        when_to_use=(
            "Wenn die Aussage explizit einen Verzeichnis-Eintrag referenziert "
            "('siehe Tabelle 3', 'Abbildung 7', 'in [4]', 'gemäß Quelle X')."
        ),
        scope="in-doc",
        cost_hint="schnell",
        enabled=True,
        used_by=["search"],
        agent_hint=(
            "capability_request mit name='RegisterLookup' wenn die Aussage einen "
            "Verzeichnis-Treffer braucht: Quellen-Zitat ([n], (Autor Jahr)) → "
            "bibliography; Tabellen-Verweis (Tabelle/Tab. n) → list_of_tables; "
            "Abbildungs-Verweis (Abbildung/Abb. n) → list_of_figures; "
            "Kapitel-Verweis (Kapitel n, Abschnitt n.m) → toc. "
            "Verzeichnisse sind aus dem InDocSearcher-Korpus AUSGESCHLOSSEN, "
            "deshalb braucht man dieses Tool für Querverweise."
        ),
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
