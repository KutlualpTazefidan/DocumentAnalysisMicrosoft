"""Convert a .docx to plain UTF-8 text, one paragraph per line.

Uses python-docx when importable; otherwise falls back to unzipping the
package and stripping XML (works headless with no extra deps)."""

from __future__ import annotations

import re
import zipfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def docx_to_text(docx_path: Path) -> str:
    try:
        import docx  # python-docx

        document = docx.Document(str(docx_path))
        paras = [p.text.strip() for p in document.paragraphs]
        return "\n".join(p for p in paras if p)
    except ModuleNotFoundError:
        return _docx_to_text_fallback(docx_path)


def _docx_to_text_fallback(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    # paragraph boundary → newline, then strip all remaining tags
    xml = xml.replace("</w:p>", "\n")
    text = re.sub(r"<[^>]*>", "", xml)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    lines = [ln.strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)
