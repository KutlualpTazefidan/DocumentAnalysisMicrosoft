"""Tests for goldens.creation.curate helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from goldens.creation.curate import (
    SlugResolutionError,
    StartResolutionError,
    build_created_event,
    query_substring_overlap,
    resolve_slug,
    resolve_start_position,
)
from goldens.creation.elements.adapter import DocumentElement
from goldens.creation.elements.analyze_json import AnalyzeJsonLoader
from goldens.creation.identity import Identity
from goldens.schemas import Event


def _make_doc(root: Path, slug: str) -> None:
    analyze_dir = root / slug / "analyze"
    analyze_dir.mkdir(parents=True)
    (analyze_dir / "2026-04-29T10-00-00Z.json").write_text("{}", encoding="utf-8")


def test_overlap_true_for_paste_above_threshold() -> None:
    source = "Der Tragkorb wird in zwei Hälften gefertigt und vor Ort verschraubt."
    pasted = "Der Tragkorb wird in zwei Hälften gefertigt"
    assert query_substring_overlap(pasted, source, threshold=30) is True


def test_overlap_false_for_short_quote_below_threshold() -> None:
    source = "Der Tragkorb wird in zwei Hälften gefertigt und vor Ort verschraubt."
    quoted = "§47 Abs. 2"
    assert query_substring_overlap(quoted, source, threshold=30) is False


def test_overlap_false_when_query_shorter_than_threshold() -> None:
    source = "long source text " * 10
    short = "abc"
    assert query_substring_overlap(short, source, threshold=30) is False


def test_overlap_normalises_whitespace_and_case() -> None:
    source = "Der  Tragkorb   wird in zwei  Hälften gefertigt und vor Ort verschraubt."
    paste = "der tragkorb wird IN zwei Hälften gefertigt"
    assert query_substring_overlap(paste, source, threshold=30) is True


def test_overlap_zero_threshold_short_circuits_true() -> None:
    assert query_substring_overlap("anything", "anything else", threshold=0) is True


def test_resolve_slug_auto_picks_when_one_doc(tmp_path: Path) -> None:
    _make_doc(tmp_path, "doc-a")
    assert resolve_slug(None, outputs_root=tmp_path) == "doc-a"


def test_resolve_slug_uses_explicit_when_set(tmp_path: Path) -> None:
    _make_doc(tmp_path, "doc-a")
    _make_doc(tmp_path, "doc-b")
    assert resolve_slug("doc-b", outputs_root=tmp_path) == "doc-b"


def test_resolve_slug_errors_when_zero_docs(tmp_path: Path) -> None:
    with pytest.raises(SlugResolutionError, match="no candidate"):
        resolve_slug(None, outputs_root=tmp_path)


def test_resolve_slug_errors_when_multiple_docs(tmp_path: Path) -> None:
    _make_doc(tmp_path, "doc-a")
    _make_doc(tmp_path, "doc-b")
    with pytest.raises(SlugResolutionError, match="doc-a") as excinfo:
        resolve_slug(None, outputs_root=tmp_path)
    assert "doc-b" in str(excinfo.value)


def test_resolve_slug_errors_when_outputs_root_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(SlugResolutionError, match="does not exist"):
        resolve_slug(None, outputs_root=missing)


def test_resolve_slug_skips_dirs_without_analyze_json(tmp_path: Path) -> None:
    _make_doc(tmp_path, "doc-real")
    (tmp_path / "doc-noisy").mkdir()
    assert resolve_slug(None, outputs_root=tmp_path) == "doc-real"


def _els(*ids_and_pages: tuple[str, int]) -> list[DocumentElement]:
    return [
        DocumentElement(
            element_id=id_, page_number=page, element_type="paragraph", content=f"c-{id_}"
        )
        for id_, page in ids_and_pages
    ]


def test_resolve_start_exact_id_wins() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p1-bbbbbbbb", 1), ("p2-aaaaaaaa", 2))
    idx = resolve_start_position(elements, explicit="p1-bbbbbbbb", cached=None)
    assert idx == 1


def test_resolve_start_prefix_match_when_no_exact() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p1-bbbbbbbb", 1))
    idx = resolve_start_position(elements, explicit="p1-bb", cached=None)
    assert idx == 1


def test_resolve_start_unknown_id_errors() -> None:
    elements = _els(("p1-aaaaaaaa", 1))
    with pytest.raises(StartResolutionError, match="nothing"):
        resolve_start_position(elements, explicit="p9-zzzzzzzz", cached=None)


def test_resolve_start_falls_back_to_position_cache() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p2-bbbbbbbb", 2), ("p3-cccccccc", 3))
    idx = resolve_start_position(elements, explicit=None, cached="p2-bbbbbbbb")
    assert idx == 1


def test_resolve_start_falls_back_to_zero_when_cache_misses() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p2-bbbbbbbb", 2))
    idx = resolve_start_position(elements, explicit=None, cached="p9-zzzzzzzz")
    assert idx == 0


def test_resolve_start_falls_back_to_zero_when_cache_absent() -> None:
    elements = _els(("p1-aaaaaaaa", 1), ("p2-bbbbbbbb", 2))
    idx = resolve_start_position(elements, explicit=None, cached=None)
    assert idx == 0


def _identity() -> Identity:
    return Identity(
        schema_version=1,
        pseudonym="alice",
        level="phd",
        created_at_utc="2026-04-29T14:32:00Z",
    )


def _loader_with_one_paragraph(tmp_path: Path) -> AnalyzeJsonLoader:
    import shutil

    fixtures = Path(__file__).parent / "fixtures"
    analyze_dir = tmp_path / "doc-a" / "analyze"
    analyze_dir.mkdir(parents=True)
    shutil.copy(fixtures / "analyze_minimal.json", analyze_dir / "ts.json")
    return AnalyzeJsonLoader("doc-a", outputs_root=tmp_path)


def test_build_event_shape(tmp_path: Path) -> None:
    loader = _loader_with_one_paragraph(tmp_path)
    element = next(el for el in loader.elements() if el.element_type == "paragraph")
    event = build_created_event(
        question="Wie wird der Tragkorb montiert?",
        element=element,
        loader=loader,
        identity=_identity(),
    )
    assert isinstance(event, Event)
    assert event.event_type == "created"
    assert event.schema_version == 1
    payload = event.payload
    assert payload["task_type"] == "retrieval"
    assert payload["action"] == "created_from_scratch"
    assert payload["notes"] is None
    assert payload["actor"] == {"kind": "human", "pseudonym": "alice", "level": "phd"}
    entry_data = payload["entry_data"]
    assert entry_data["query"] == "Wie wird der Tragkorb montiert?"
    assert entry_data["expected_chunk_ids"] == []
    assert entry_data["chunk_hashes"] == {}
    src = entry_data["source_element"]
    assert src["document_id"] == "doc-a"
    assert src["page_number"] == element.page_number
    assert src["element_type"] == "paragraph"


def test_build_event_source_element_id_strips_page_prefix(tmp_path: Path) -> None:
    loader = _loader_with_one_paragraph(tmp_path)
    element = next(el for el in loader.elements() if el.element_type == "paragraph")
    event = build_created_event(question="x", element=element, loader=loader, identity=_identity())
    src = event.payload["entry_data"]["source_element"]
    assert src["element_id"] == element.element_id.split("-", 1)[1]
    assert "-" not in src["element_id"]


def test_build_event_uses_now_utc_iso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("goldens.creation.curate.now_utc_iso", lambda: "2026-04-29T20:00:00Z")
    loader = _loader_with_one_paragraph(tmp_path)
    element = next(el for el in loader.elements() if el.element_type == "paragraph")
    event = build_created_event(question="x", element=element, loader=loader, identity=_identity())
    assert event.timestamp_utc == "2026-04-29T20:00:00Z"


def test_build_event_ids_are_unique_per_call(tmp_path: Path) -> None:
    loader = _loader_with_one_paragraph(tmp_path)
    element = next(el for el in loader.elements() if el.element_type == "paragraph")
    a = build_created_event(question="x", element=element, loader=loader, identity=_identity())
    b = build_created_event(question="y", element=element, loader=loader, identity=_identity())
    assert a.event_id != b.event_id
    assert a.entry_id != b.entry_id


class _TtyStream:
    def isatty(self) -> bool:
        return True

    def write(self, _data: str) -> int:
        return 0

    def flush(self) -> None:
        return None


class _NonTtyStream:
    def isatty(self) -> bool:
        return False

    def write(self, _data: str) -> int:
        return 0

    def flush(self) -> None:
        return None


def test_require_tty_passes_when_both_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from goldens.creation.curate import require_interactive_tty

    monkeypatch.setattr("sys.stdin", _TtyStream())
    monkeypatch.setattr("sys.stdout", _TtyStream())
    require_interactive_tty()


def test_require_tty_exits_when_stdin_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from goldens.creation.curate import require_interactive_tty

    monkeypatch.setattr("sys.stdin", _NonTtyStream())
    monkeypatch.setattr("sys.stdout", _TtyStream())
    with pytest.raises(SystemExit) as excinfo:
        require_interactive_tty()
    assert excinfo.value.code == 2


def test_require_tty_exits_when_stdout_not_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    from goldens.creation.curate import require_interactive_tty

    monkeypatch.setattr("sys.stdin", _TtyStream())
    monkeypatch.setattr("sys.stdout", _NonTtyStream())
    with pytest.raises(SystemExit) as excinfo:
        require_interactive_tty()
    assert excinfo.value.code == 2


def test_render_paragraph_includes_type_page_id_content() -> None:
    from goldens.creation.curate import render_element_block

    el = DocumentElement(
        element_id="p3-deadbeef",
        page_number=3,
        element_type="paragraph",
        content="Hello world",
    )
    block = render_element_block(el)
    assert "Absatz" in block
    assert "p3-deadbeef" in block
    assert "Seite 3" in block
    assert "Hello world" in block


def test_render_heading_uses_heading_label() -> None:
    from goldens.creation.curate import render_element_block

    el = DocumentElement(
        element_id="p1-aaaaaaaa", page_number=1, element_type="heading", content="Statik"
    )
    block = render_element_block(el)
    assert "Überschrift" in block
    assert "Statik" in block


def test_render_table_compact_shows_dims_and_stub() -> None:
    from goldens.creation.curate import render_element_block

    el = DocumentElement(
        element_id="p1-cccccccc",
        page_number=1,
        element_type="table",
        content="Pos. | Material | Menge\n1 | Stahl | 12",
        table_dims=(2, 3),
    )
    block = render_element_block(el)
    assert "Tabelle" in block
    assert f"2{chr(0x00D7)}3" in block
    assert "Pos." in block
    assert "Drücke 't'" in block


def test_render_table_full_shows_full_grid() -> None:
    from goldens.creation.curate import render_table_full

    el = DocumentElement(
        element_id="p1-cccccccc",
        page_number=1,
        element_type="table",
        content="Pos. | Material | Menge\n1 | Stahl | 12",
        table_dims=(2, 3),
    )
    block = render_table_full(el)
    assert "Pos." in block
    assert "Stahl" in block
    assert "Drücke 't'" not in block


def test_render_figure_includes_caption_and_terminal_note() -> None:
    from goldens.creation.curate import render_element_block

    el = DocumentElement(
        element_id="p7-ffffffff",
        page_number=7,
        element_type="figure",
        content="",
        caption="Abbildung 1 — Schnitt durch den Tragkorb",
    )
    block = render_element_block(el)
    assert "Abbildung 1 — Schnitt durch den Tragkorb" in block
    assert "siehe PDF Seite 7" in block


def test_render_list_item_has_listpunkt_label() -> None:
    from goldens.creation.curate import render_element_block

    el = DocumentElement(
        element_id="p2-bbbbbbbb",
        page_number=2,
        element_type="list_item",
        content="erstens",
    )
    block = render_element_block(el)
    assert "Listpunkt" in block
    assert "erstens" in block
    assert "p2-bbbbbbbb" in block


def _identity_file(xdg: Path) -> None:
    cfg = xdg / "goldens"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "identity.toml").write_text(
        'schema_version = 1\npseudonym = "alice"\nlevel = "masters"\n'
        'created_at_utc = "2026-04-29T14:32:00Z"\n',
        encoding="utf-8",
    )


def test_cmd_curate_writes_event_then_quits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse
    import builtins
    import shutil

    from goldens.creation.curate import cmd_curate
    from goldens.storage import GOLDEN_EVENTS_V1_FILENAME, read_events

    outputs = tmp_path / "outputs"
    fixtures = Path(__file__).parent / "fixtures"
    analyze_dir = outputs / "doc-a" / "analyze"
    analyze_dir.mkdir(parents=True)
    shutil.copy(fixtures / "analyze_minimal.json", analyze_dir / "ts.json")

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _identity_file(xdg)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", _TtyStream())
    monkeypatch.setattr("sys.stdout", _TtyStream())

    answers = iter(["Wozu dient der Tragkorb?", "q"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(answers))

    args = argparse.Namespace(doc=None, start_from=None)
    rc = cmd_curate(args)
    assert rc == 0
    events_path = outputs / "doc-a" / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    events = list(read_events(events_path))
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == "created"
    assert ev.payload["entry_data"]["query"] == "Wozu dient der Tragkorb?"
    assert ev.payload["entry_data"]["source_element"]["document_id"] == "doc-a"


def test_cmd_curate_writes_multiple_events_for_one_element(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D19: typed questions auto-save and stay on the same element until
    an empty ENTER advances. Three questions on element #1 → three
    events, all referencing the same source element."""
    import argparse
    import builtins
    import shutil

    from goldens.creation.curate import cmd_curate
    from goldens.storage import GOLDEN_EVENTS_V1_FILENAME, read_events

    outputs = tmp_path / "outputs"
    fixtures = Path(__file__).parent / "fixtures"
    analyze_dir = outputs / "doc-a" / "analyze"
    analyze_dir.mkdir(parents=True)
    shutil.copy(fixtures / "analyze_minimal.json", analyze_dir / "ts.json")

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _identity_file(xdg)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", _TtyStream())
    monkeypatch.setattr("sys.stdout", _TtyStream())

    answers = iter(["Wozu dient das Bauteil?", "Welche Norm gilt?", "Wer prüft?", "q"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(answers))

    args = argparse.Namespace(doc=None, start_from=None)
    rc = cmd_curate(args)
    assert rc == 0

    events_path = outputs / "doc-a" / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    events = list(read_events(events_path))
    assert len(events) == 3
    queries = [ev.payload["entry_data"]["query"] for ev in events]
    assert queries == ["Wozu dient das Bauteil?", "Welche Norm gilt?", "Wer prüft?"]
    element_ids = {ev.payload["entry_data"]["source_element"]["element_id"] for ev in events}
    assert len(element_ids) == 1, "all three events must reference the same source element"


def test_cmd_curate_empty_enter_advances_without_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D19: empty ENTER is unconditional 'Weiter'. Save one question on
    element #1, then empty ENTER → element #2, then quit. Only one
    event written."""
    import argparse
    import builtins
    import shutil

    from goldens.creation.curate import cmd_curate
    from goldens.storage import GOLDEN_EVENTS_V1_FILENAME, read_events

    outputs = tmp_path / "outputs"
    fixtures = Path(__file__).parent / "fixtures"
    analyze_dir = outputs / "doc-a" / "analyze"
    analyze_dir.mkdir(parents=True)
    shutil.copy(fixtures / "analyze_minimal.json", analyze_dir / "ts.json")

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    _identity_file(xdg)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", _TtyStream())
    monkeypatch.setattr("sys.stdout", _TtyStream())

    answers = iter(["Wozu dient das Bauteil?", "", "q"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(answers))

    args = argparse.Namespace(doc=None, start_from=None)
    rc = cmd_curate(args)
    assert rc == 0

    events_path = outputs / "doc-a" / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    events = list(read_events(events_path))
    assert len(events) == 1
    assert events[0].payload["entry_data"]["query"] == "Wozu dient das Bauteil?"


def test_cmd_curate_returns_2_when_no_doc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    from goldens.creation.curate import cmd_curate

    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()
    monkeypatch.setattr("sys.stdin", _TtyStream())
    monkeypatch.setattr("sys.stdout", _TtyStream())
    args = argparse.Namespace(doc=None, start_from=None)
    rc = cmd_curate(args)
    assert rc == 2


def test_cmd_curate_first_run_configures_identity_and_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse
    import builtins
    import shutil

    from goldens.creation.curate import cmd_curate
    from goldens.storage import GOLDEN_EVENTS_V1_FILENAME

    outputs = tmp_path / "outputs"
    fixtures = Path(__file__).parent / "fixtures"
    analyze_dir = outputs / "doc-a" / "analyze"
    analyze_dir.mkdir(parents=True)
    shutil.copy(fixtures / "analyze_minimal.json", analyze_dir / "ts.json")

    xdg = tmp_path / "xdg"
    xdg.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", _TtyStream())
    monkeypatch.setattr("sys.stdout", _TtyStream())
    monkeypatch.setattr("goldens.creation.identity.now_utc_iso", lambda: "2026-04-29T14:32:00Z")

    answers = iter(["alice", "masters"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(answers))

    args = argparse.Namespace(doc=None, start_from=None)
    rc = cmd_curate(args)
    assert rc == 0
    assert (xdg / "goldens" / "identity.toml").exists()
    events_path = outputs / "doc-a" / "datasets" / GOLDEN_EVENTS_V1_FILENAME
    assert not events_path.exists()
