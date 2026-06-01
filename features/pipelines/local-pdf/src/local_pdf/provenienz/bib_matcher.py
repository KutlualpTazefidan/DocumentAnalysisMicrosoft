"""BibFileMatcher — heuristically resolve a bibliography citation to a
slug in the local corpus.

When the agent's RegisterLookup tool resolves "[3]" to
``GNB B 137/2001 (TR K 0152) Typ B(U)F-Versandstück …``, this module
checks whether one of the documents already uploaded to *data_root*
IS that citation, so the user/agent can pivot the Provenienz session
to the matching slug.

Pure heuristic — token overlap between the citation text and each
doc's ``meta.json`` (filename + slug + optional title). Falsy /
ambiguous matches are filtered out with a minimum-score gate so the
caller never gets a spurious "yes" on weak evidence.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path  # noqa: TC003

# Tokens shorter than this are too generic (single letters, "rev",
# "ed", …) — drop them so a single one-letter overlap doesn't decide
# the match. Empirically tuned: 3 keeps "GNB" + "TRK" but loses
# noise like "und"/"der" after umlaut-folding.
_MIN_TOKEN_LEN = 3

# Below this overlap count, the match is more likely coincidence than
# a real citation-to-doc resolution. Anything below 2 = caller gets
# None instead of a low-confidence guess.
_MIN_OVERLAP_SCORE = 2


def _tokenize(text: str) -> set[str]:
    """Lowercase, fold umlauts / ß, split on non-alphanumerics, drop
    tokens shorter than ``_MIN_TOKEN_LEN``.

    NFKD strips diacritics ("ü"→"u"), so callers shouldn't expect German
    "ü"→"ue" folding. The hand-folded ``ß`` → ``ss`` is the only
    explicit substitution because NFKD keeps ß intact.

    Examples
    --------
    >>> sorted(_tokenize("GNB B 137/2001 Typ B(U)F-Versandstück"))
    ['137', '2001', 'gnb', 'typ', 'versandstuck']
    """
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = folded.replace("ß", "ss")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    tokens = re.split(r"[^a-z0-9]+", folded)
    return {t for t in tokens if len(t) >= _MIN_TOKEN_LEN}


def match_bib_to_corpus(citation: str, data_root: Path) -> dict | None:
    """Score each doc in *data_root* by token overlap with *citation*.

    Walks ``{data_root}/<slug>/meta.json`` for every slug-dir, builds
    the doc's token set from filename + slug + title, intersects with
    the citation's tokens, picks the best score across the corpus.

    Returns ``{slug, filename, score, matched_tokens}`` when the best
    match scores at least ``_MIN_OVERLAP_SCORE``; ``None`` otherwise.

    The matched_tokens list is included so the caller can show the
    user *why* this slug won — useful both for debugging and for
    distinguishing "matched on document-id" from "matched on common
    German nouns".
    """
    cit_tokens = _tokenize(citation)
    if not cit_tokens:
        return None

    best: dict | None = None
    for slug_dir in sorted(data_root.iterdir()):
        if not slug_dir.is_dir():
            continue
        meta_path = slug_dir / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        slug = str(meta.get("slug") or slug_dir.name)
        filename = str(meta.get("filename") or "")
        title = str(meta.get("title") or "")
        doc_tokens = _tokenize(filename) | _tokenize(slug) | _tokenize(title)
        overlap = cit_tokens & doc_tokens
        if not overlap:
            continue
        score = len(overlap)
        if best is None or score > best["score"]:
            best = {
                "slug": slug,
                "filename": filename,
                "score": score,
                "matched_tokens": sorted(overlap),
            }
    if best is None or best["score"] < _MIN_OVERLAP_SCORE:
        return None
    return best
