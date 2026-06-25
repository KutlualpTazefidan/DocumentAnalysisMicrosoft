"""OKF knowledge-base I/O (pure file reads) for the Wissen tab."""

from local_pdf.knowledge.docx_to_text import docx_to_text
from local_pdf.knowledge.reader import (
    BaseSummary,
    Concept,
    ConceptLink,
    ConceptSummary,
    list_bases,
    list_concepts,
    read_concept,
    search_concepts,
)

__all__ = [
    "BaseSummary",
    "Concept",
    "ConceptLink",
    "ConceptSummary",
    "docx_to_text",
    "list_bases",
    "list_concepts",
    "read_concept",
    "search_concepts",
]
