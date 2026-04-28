"""Analyze a PDF with Document Intelligence and persist the result as JSON.

The output JSON wraps the Document Intelligence response with an
`_ingestion_metadata` sidecar that downstream stages (chunk, embed, upload)
read to derive the slug, source_file, and lineage timestamp without the user
having to re-supply them at each step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from ingestion.client import get_doc_intel_client
from ingestion.slug import slug_from_filename
from ingestion.timestamp import now_compact_utc

if TYPE_CHECKING:
    from ingestion.config import IngestionConfig


def _outputs_root() -> Path:
    """Return the repository's outputs root.

    Discovered by walking up from this file until a directory containing both
    a `pyproject.toml` (root) and the `features/` directory is found.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "features").is_dir():
            return parent / "outputs"
    return Path.cwd() / "outputs"


def analyze_pdf(
    in_path: Path,
    out_path: Path | None = None,
    cfg: IngestionConfig | None = None,
) -> Path:
    """Analyze a PDF; write JSON; return the actual output path.

    If `out_path` is None, derive: `<outputs_root>/<slug>/analyze/<ts>.json`.
    """
    if cfg is None:
        from ingestion.config import IngestionConfig as _Cfg

        cfg = _Cfg.from_env()

    source_file = in_path.name
    slug = slug_from_filename(source_file)
    ts = now_compact_utc()

    if out_path is None:
        out_path = _outputs_root() / slug / "analyze" / f"{ts}.json"

    client = get_doc_intel_client(cfg)

    with in_path.open("rb") as f:
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            analyze_request=f,
            content_type="application/pdf",
        )
    result = poller.result()
    raw = result.as_dict()

    wrapped = {
        "_ingestion_metadata": {
            "source_file": source_file,
            "slug": slug,
            "timestamp_utc": ts,
        },
        "analyzeResult": raw,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(wrapped, ensure_ascii=False, indent=2), encoding="utf-8")

    page_count = len(raw.get("pages", []))
    paragraph_count = len(raw.get("paragraphs", []))
    print(f"Wrote {out_path} ({page_count} pages, {paragraph_count} paragraphs)")

    return out_path
