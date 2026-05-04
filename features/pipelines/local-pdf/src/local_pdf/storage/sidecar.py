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

from local_pdf.api.schemas import CuratorQuestion, CuratorQuestionsFile, DocMeta, SegmentsFile


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


def _migrate_segments_data(data: dict) -> dict:
    """Transparently rewrite legacy kind values before validation.

    Specifically: kind="abandon" was renamed to kind="auxiliary" in the
    2026-05 release. Any stored segments.json that still uses the old value
    is silently upgraded on read so the rest of the stack never sees "abandon".
    """
    boxes = data.get("boxes")
    if not boxes:
        return data
    migrated = [{**b, "kind": "auxiliary"} if b.get("kind") == "abandon" else b for b in boxes]
    if migrated == boxes:
        return data
    return {**data, "boxes": migrated}


def read_segments(data_root: Path, slug: str) -> SegmentsFile | None:
    raw = _read_text_or_none(_segments_path(data_root, slug))
    if raw is None:
        return None
    data = _migrate_segments_data(json.loads(raw))
    return SegmentsFile.model_validate(data)  # type: ignore[no-any-return]


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


def _questions_path(data_root: Path, slug: str) -> Path:
    return doc_dir(data_root, slug) / "curator-questions.json"


def write_curator_questions(data_root: Path, slug: str, payload: CuratorQuestionsFile) -> None:
    _write_locked_text(
        _questions_path(data_root, slug),
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False, indent=2),
    )


def read_curator_questions(data_root: Path, slug: str) -> CuratorQuestionsFile | None:
    raw = _read_text_or_none(_questions_path(data_root, slug))
    if raw is None:
        return None
    return CuratorQuestionsFile.model_validate(json.loads(raw))  # type: ignore[no-any-return]


def _answers_path(data_root: Path, slug: str) -> Path:
    """LLM-generated reference answers, keyed by question entry_id.

    Lives next to golden_events.v1.jsonl so a slug's answers travel
    with its events. Format: {entry_id: answer_text} JSON.
    """
    return doc_dir(data_root, slug) / "datasets" / "answers.json"


def read_answers(data_root: Path, slug: str) -> dict[str, str]:
    raw = _read_text_or_none(_answers_path(data_root, slug))
    if not raw:
        return {}
    obj = json.loads(raw)
    return {str(k): str(v) for k, v in obj.items()} if isinstance(obj, dict) else {}


def write_answers(data_root: Path, slug: str, answers: dict[str, str]) -> None:
    path = _answers_path(data_root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_locked_text(path, json.dumps(answers, ensure_ascii=False, indent=2))


def update_question(
    data_root: Path, slug: str, question_id: str, patch: dict
) -> CuratorQuestionsFile | None:
    """Atomically apply *patch* to the question matching *question_id*.

    Returns the updated CuratorQuestionsFile, or None if the question was not
    found.  Uses the same LOCK_EX pattern as write_curator_questions.
    """
    existing = read_curator_questions(data_root, slug) or CuratorQuestionsFile(
        slug=slug, questions=[]
    )
    updated: list[CuratorQuestion] = []
    found = False
    for q in existing.questions:
        if q.question_id == question_id:
            found = True
            updated.append(q.model_copy(update=patch))
        else:
            updated.append(q)
    if not found:
        return None
    new_file: CuratorQuestionsFile = existing.model_copy(update={"questions": updated})
    write_curator_questions(data_root, slug, new_file)
    return new_file
