"""MinerU 3 extraction wrapper.

Per spec D5/D17: full-doc extract walks every non-discard box and yields a
MinerUResult per box. region extract runs MinerU on a single bbox.

The default extract_fn invokes the `mineru` CLI (configurable via env
LOCAL_PDF_MINERU_BIN). Tests inject a fake to avoid the heavy VLM.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from local_pdf.api.schemas import BoxKind, SegmentBox


@dataclass(frozen=True)
class MinerUResult:
    box_id: str
    html: str


ExtractFn = Callable[[Path, SegmentBox], MinerUResult]


def _default_extract(pdf_path: Path, box: SegmentBox) -> MinerUResult:
    """Real MinerU 3 invocation. Crops the page region and runs the CLI."""
    binary = os.environ.get("LOCAL_PDF_MINERU_BIN", "mineru")
    with tempfile.TemporaryDirectory() as td:
        out_dir = Path(td)
        cmd = [
            binary,
            "-p",
            str(pdf_path),
            "-o",
            str(out_dir),
            "--page",
            str(box.page),
            "--bbox",
            f"{box.bbox[0]},{box.bbox[1]},{box.bbox[2]},{box.bbox[3]}",
            "--format",
            "html",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise RuntimeError(f"mineru failed: {proc.stderr}")
        out_html = out_dir / "result.html"
        out_json = out_dir / "result.json"
        if out_html.exists():
            html = out_html.read_text(encoding="utf-8")
        elif out_json.exists():
            payload = json.loads(out_json.read_text(encoding="utf-8"))
            html = payload.get("html", "")
        else:
            html = proc.stdout
        return MinerUResult(box_id=box.box_id, html=html)


def run_mineru(
    pdf_path: Path,
    boxes: list[SegmentBox],
    *,
    extract_fn: ExtractFn | None = None,
) -> Iterator[MinerUResult]:
    """Yield one MinerUResult per non-discard box, in input order."""
    fn = extract_fn or _default_extract
    for box in boxes:
        if box.kind == BoxKind.discard:
            continue
        yield fn(pdf_path, box)


def run_mineru_region(
    pdf_path: Path,
    box: SegmentBox,
    *,
    extract_fn: ExtractFn | None = None,
) -> MinerUResult:
    """Extract a single bbox region (re-extract path; spec D17)."""
    fn = extract_fn or _default_extract
    return fn(pdf_path, box)
