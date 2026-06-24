"""Research tools for the Agent spike: corpus search + a reflection tool.

Search delegates to features/pipelines/microsoft/retrieval (`hybrid_search`) rather than
calling the Azure SDKs here, because the repo's import-boundary hook restricts
openai.* / azure.search.* imports to that package + core/llm_clients. hybrid_search reads
the same AI_FOUNDRY_*/AI_SEARCH_* env and queries the same index (push-semantic-chunking-1).
NOTE: BM25+vector, not semantic-reranked — the partner reference used query_type="semantic";
deferred as a refinement.
"""

from langchain_core.tools import tool
from query_index.search import hybrid_search


@tool(parse_docstring=True)
def azure_ai_search(query: str, top: int = 5) -> str:
    """Search the document index for information relevant to a given query.

    Uses the project's hybrid (text + vector) search over the indexed knowledge
    base to find relevant document sections.

    Args:
        query: Search query to execute against the document index
        top: Maximum number of results to return (default: 5)

    Returns:
        Formatted search results with section headings and content
    """
    hits = hybrid_search(query, top=top)
    if not hits:
        return f"No results found for query: '{query}'"
    parts = []
    for i, h in enumerate(hits, 1):
        heading = h.section_heading or "Untitled Section"
        parts.append(f"## [{i}] {heading}\n**Relevance Score:** {h.score}\n\n{h.chunk}\n\n---\n")
    return f"Found {len(parts)} result(s) for '{query}':\n\n" + "\n".join(parts)


@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Tool for strategic reflection on research progress and decision-making.

    Use this tool after each search to analyze results and plan next steps systematically.

    Args:
        reflection: Your detailed reflection on research progress, findings, gaps, and next steps

    Returns:
        Confirmation that reflection was recorded for decision-making
    """
    return f"Reflection recorded: {reflection}"
