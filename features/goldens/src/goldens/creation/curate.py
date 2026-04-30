"""Interactive curate CLI + decision-bearing helpers.

The outer cmd_curate() loop body is `# pragma: no cover` because the
ergonomic UX wraps print()/input() calls; every branch with logic
worth testing is extracted into a helper that has its own unit test."""

from __future__ import annotations

import argparse  # noqa: TC003
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from goldens.creation._time import now_utc_iso
from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
from goldens.creation.identity import (
    identity_to_human_actor,
    load_identity,
    prompt_and_save_identity,
)
from goldens.creation.positions import read_position, write_position
from goldens.schemas import Event
from goldens.storage import (
    GOLDEN_EVENTS_V1_FILENAME,
    append_event,
    new_entry_id,
    new_event_id,
)

if TYPE_CHECKING:
    from goldens.creation.elements.adapter import DocumentElement
    from goldens.creation.identity import Identity

_WS_RE = re.compile(r"\s+")


class SlugResolutionError(Exception):
    """Raised when --doc cannot be auto-resolved (zero or multiple candidates)."""


def resolve_slug(explicit: str | None, *, outputs_root: Path) -> str:
    if explicit is not None:
        return explicit
    if not outputs_root.is_dir():
        raise SlugResolutionError(
            f"no candidate documents under {outputs_root} (directory does not exist)"
        )
    candidates: list[str] = []
    for child in sorted(outputs_root.iterdir()):
        if not child.is_dir():
            continue
        analyze_dir = child / "analyze"
        if analyze_dir.is_dir() and any(analyze_dir.glob("*.json")):
            candidates.append(child.name)
    if not candidates:
        raise SlugResolutionError(f"no candidate documents under {outputs_root}")
    if len(candidates) > 1:
        listed = ", ".join(candidates)
        raise SlugResolutionError(
            f"multiple candidate documents under {outputs_root} ({listed}); "
            "pass --doc <slug> to disambiguate"
        )
    return candidates[0]


class StartResolutionError(Exception):
    """Raised when --start-from matches no element."""


def resolve_start_position(
    elements: list[DocumentElement],
    *,
    explicit: str | None,
    cached: str | None,
) -> int:
    if explicit is not None:
        for i, el in enumerate(elements):
            if el.element_id == explicit:
                return i
        for i, el in enumerate(elements):
            if el.element_id.startswith(explicit):
                return i
        raise StartResolutionError(f"--start-from {explicit!r} matches nothing in this document")
    if cached is not None:
        for i, el in enumerate(elements):
            if el.element_id == cached:
                return i
    return 0


def _normalise(text: str) -> str:
    return _WS_RE.sub(" ", text).strip().lower()


def query_substring_overlap(query: str, source: str, *, threshold: int) -> bool:
    """True iff some contiguous substring of `query` of length >= `threshold`
    appears in `source`. Both strings are lowercased and whitespace-collapsed
    before comparison so trivial reformatting cannot bypass the check."""
    if threshold <= 0:
        return True
    q = _normalise(query)
    s = _normalise(source)
    if len(q) < threshold:
        return False
    return any(q[start : start + threshold] in s for start in range(0, len(q) - threshold + 1))


def build_created_event(
    *,
    question: str,
    element: DocumentElement,
    loader: AnalyzeJsonLoader,
    identity: Identity,
) -> Event:
    """Assemble a `created` Event from one curator-typed question.

    `expected_chunk_ids` is intentionally empty (D13); `source_element`
    is the ground truth and the chunk-id translation lives in a
    dedicated match-type classifier (next phase)."""
    source_element = loader.to_source_element(element)
    payload = {
        "task_type": "retrieval",
        "actor": identity_to_human_actor(identity).to_dict(),
        "action": "created_from_scratch",
        "notes": None,
        "entry_data": {
            "query": question,
            "expected_chunk_ids": [],
            "chunk_hashes": {},
            "source_element": source_element.to_dict(),
        },
    }
    return Event(
        event_id=new_event_id(),
        timestamp_utc=now_utc_iso(),
        event_type="created",
        entry_id=new_entry_id(),
        schema_version=1,
        payload=payload,
    )


def require_interactive_tty() -> None:
    """Hard-exit when stdin or stdout is not a TTY. Verbatim from the legacy
    curate writer (D9). No `--no-tty` opt-out."""
    if not sys.stdin.isatty():
        print("ERROR: curate requires an interactive stdin (TTY)", file=sys.stderr)
        raise SystemExit(2)
    if not sys.stdout.isatty():
        print("ERROR: curate requires an interactive stdout (TTY)", file=sys.stderr)
        raise SystemExit(2)


def _header(label: str, el: DocumentElement) -> str:
    return f"[{label}, Seite {el.page_number}, id={el.element_id}]"


def render_element_block(el: DocumentElement) -> str:
    """Compact textual rendering used per iteration. Tables get a stub +
    a hint that 't' expands the full grid."""
    if el.element_type == "table":
        rows, cols = el.table_dims or (0, 0)
        cross = chr(0x00D7)  # MULTIPLICATION SIGN
        header = f"[Tabelle, Seite {el.page_number}, {rows}{cross}{cols}, id={el.element_id}]"
        return f"{header}\n{el.content}\n(Drücke 't' für die volle Tabelle.)"
    if el.element_type == "figure":
        header = _header("Abbildung", el)
        caption = el.caption or ""
        return (
            f"{header}\n{caption}\n"
            f"(Bild kann im Terminal nicht angezeigt werden — siehe PDF Seite {el.page_number}.)"
        )
    label = {"heading": "Überschrift", "list_item": "Listpunkt"}.get(el.element_type, "Absatz")
    header = _header(label, el)
    return f"{header}\n{el.content}"


def render_table_full(el: DocumentElement) -> str:
    """Full grid view triggered by the 't' toggle."""
    rows, cols = el.table_dims or (0, 0)
    cross = chr(0x00D7)
    header = f"[Tabelle (voll), Seite {el.page_number}, {rows}{cross}{cols}, id={el.element_id}]"
    return f"{header}\n{el.content}"


_OVERLAP_THRESHOLD = 30
_PROMPT = (
    "Frage zu diesem Element (oder ENTER für 'Weiter', 'q' zum Beenden, 't' für volle Tabelle):\n> "
)


def cmd_curate(args: argparse.Namespace) -> int:  # pragma: no cover
    """Interactive curate session. The body is `# pragma: no cover`."""
    require_interactive_tty()

    outputs_root = Path("outputs")
    try:
        slug = resolve_slug(args.doc, outputs_root=outputs_root)
    except SlugResolutionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    identity = load_identity()
    if identity is None:
        prompt_and_save_identity()
        return 0

    loader = AnalyzeJsonLoader(slug, outputs_root=outputs_root)
    elements = loader.elements()
    try:
        start = resolve_start_position(
            elements,
            explicit=args.start_from,
            cached=read_position(slug),
        )
    except StartResolutionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    events_path = outputs_root / slug / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    print(
        f"\n=== curate: {slug} — {len(elements)} Elemente, "
        f"starte bei #{start + 1} ===\n"
        "Bitte keine Texte aus dem Dokument kopieren — formuliere die Frage "
        "in eigenen Worten.\n"
    )

    for idx in range(start, len(elements)):
        el = elements[idx]
        print("\n" + "—" * 60)
        print(render_element_block(el))
        question = input(_PROMPT)

        if question == "q":
            write_position(slug, el.element_id)
            return 0

        if question == "":
            write_position(slug, el.element_id)
            continue

        if question == "t" and el.element_type == "table":
            print("\n" + render_table_full(el))
            question = input(_PROMPT)
            if question == "q":
                write_position(slug, el.element_id)
                return 0
            if question == "":
                write_position(slug, el.element_id)
                continue

        if query_substring_overlap(question, el.content, threshold=_OVERLAP_THRESHOLD):
            keep = (
                input("WARNUNG: Frage scheint aus dem Element kopiert. Trotzdem speichern? [j/N] ")
                .strip()
                .lower()
            )
            if keep != "j":
                if input("Weiter? [j/N] ").strip().lower() == "j":
                    write_position(slug, el.element_id)
                continue

        save = input("Speichern? [J/n] ").strip().lower()
        if save in ("", "j"):
            event = build_created_event(
                question=question, element=el, loader=loader, identity=identity
            )
            append_event(events_path, event)
            write_position(slug, el.element_id)
            print("✓ gespeichert")
            continue

        if input("Weiter? [j/N] ").strip().lower() == "j":
            write_position(slug, el.element_id)

    print(f"\nDu hast alle Elemente von {slug} durchgesehen.")
    return 0
