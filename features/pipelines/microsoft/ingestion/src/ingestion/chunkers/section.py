"""Section-based chunker — V1 strategy.

Direct port of the logic in `archive/semantic_chunking.ipynb`. Splits the
flat paragraph list from Document Intelligence into one chunk per section,
where a "section" is the run of body paragraphs between two consecutive
sectionHeading/title boundaries. Noise paragraphs (pageHeader, pageFooter,
pageNumber, footnote) are dropped.
"""

from __future__ import annotations

from ingestion.chunkers.base import RawChunk

SKIP_ROLES = frozenset({"pageHeader", "pageFooter", "pageNumber", "footnote"})


class SectionChunker:
    name = "section"

    def chunk(
        self,
        analyze_result: dict,
        slug: str,
        source_file: str,
    ) -> list[RawChunk]:
        result = analyze_result.get("analyzeResult", {})
        paragraphs = result.get("paragraphs", [])

        title = next(
            (p["content"] for p in paragraphs if p.get("role") == "title"),
            "",
        )

        chunks: list[RawChunk] = []
        current_heading: str | None = None
        current_paragraphs: list[str] = []
        seq = 1

        def flush() -> None:
            nonlocal seq
            if current_heading is None:
                return
            chunks.append(
                RawChunk(
                    chunk_id=f"{slug}-{seq:03d}",
                    title=title,
                    section_heading=current_heading,
                    chunk=" ".join(current_paragraphs),
                    source_file=source_file,
                )
            )
            seq += 1

        for p in paragraphs:
            role = p.get("role")
            if role in SKIP_ROLES:
                continue
            if role in ("sectionHeading", "title"):
                flush()
                current_heading = p["content"]
                current_paragraphs = []
            else:
                current_paragraphs.append(p["content"])
        flush()  # don't forget the last section

        return chunks
