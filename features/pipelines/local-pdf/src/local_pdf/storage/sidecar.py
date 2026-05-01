"""fcntl-locked read/write of per-PDF sidecar files.

Each PDF lives in `<data_root>/<slug>/` containing:
  - source.pdf          (immutable after upload)
  - meta.json           (DocMeta)
  - yolo.json           (raw DocLayout-YOLO output, immutable)
  - segments.json       (user-edited, SegmentsFile)
  - mineru-out.json     (raw MinerU output, immutable)
  - html.html           (user-edited HTML)
  - sourceelements.json (final canonical export)

All writes are LOCK_EX + write-then-fsync. Reads are tolerant: a missing
file returns None.
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path  # noqa: TC003

from local_pdf.api.schemas import DocMeta, SegmentsFile


def doc_dir(data_root: Path, slug: str) -> Path:
    return data_root / slug


def _meta_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "meta.json"


def _segments_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "segments.json"


def _html_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "html.html"


def _yolo_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "yolo.json"


def _mineru_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "mineru-out.json"


def _source_elements_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "sourceelements.json"


def _write_locked_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    os.replace(tmp, path)


def _read_text_or_none(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def write_meta(data_root: Path, slug: str, meta: DocMeta) -> None:
    payload = json.dumps(meta.model_dump(mode="json"), ensure_ascii=False, indent=2)
    _write_locked_text(_meta_path(data_root, slug), payload)


def read_meta(data_root: Path, slug: str) -> DocMeta | None:
    raw = _read_text_or_none(_meta_path(data_root, slug))
    if raw is None:
        return None
    return DocMeta.model_validate(json.loads(raw))  # type: ignore[no-any-return]


def write_segments(data_root: Path, slug: str, segments: SegmentsFile) -> None:
    payload = json.dumps(segments.model_dump(mode="json"), ensure_ascii=False, indent=2)
    _write_locked_text(_segments_path(data_root, slug), payload)


def read_segments(data_root: Path, slug: str) -> SegmentsFile | None:
    raw = _read_text_or_none(_segments_path(data_root, slug))
    if raw is None:
        return None
    return SegmentsFile.model_validate(json.loads(raw))  # type: ignore[no-any-return]


def write_html(data_root: Path, slug: str, html: str) -> None:
    _write_locked_text(_html_path(data_root, slug), html)


def read_html(data_root: Path, slug: str) -> str | None:
    return _read_text_or_none(_html_path(data_root, slug))


def write_yolo(data_root: Path, slug: str, payload: dict) -> None:
    _write_locked_text(
        _yolo_path(data_root, slug), json.dumps(payload, ensure_ascii=False, indent=2)
    )


def read_yolo(data_root: Path, slug: str) -> dict | None:
    raw = _read_text_or_none(_yolo_path(data_root, slug))
    return json.loads(raw) if raw else None


def write_mineru(data_root: Path, slug: str, payload: dict) -> None:
    _write_locked_text(
        _mineru_path(data_root, slug), json.dumps(payload, ensure_ascii=False, indent=2)
    )


def read_mineru(data_root: Path, slug: str) -> dict | None:
    raw = _read_text_or_none(_mineru_path(data_root, slug))
    return json.loads(raw) if raw else None


def write_source_elements(data_root: Path, slug: str, payload: dict) -> None:
    _write_locked_text(
        _source_elements_path(data_root, slug), json.dumps(payload, ensure_ascii=False, indent=2)
    )


def read_source_elements(data_root: Path, slug: str) -> dict | None:
    raw = _read_text_or_none(_source_elements_path(data_root, slug))
    return json.loads(raw) if raw else None
