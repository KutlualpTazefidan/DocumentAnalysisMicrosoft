"""One-off agent-assisted authoring: run a flat deepagents pass with the
durable OKF_EXTRACTION prompt over an interview transcript and persist the
emitted OKF files to disk. Deliberately minimal — no CLI, no multi-interview
runner (deferred until interview #2). deepagents/langchain imported lazily so
importing this module never requires the `agent` extra."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def author_base(
    interview_text: str,
    out_dir: Path,
    *,
    model: object | None = None,
) -> list[str]:
    from deepagents import create_deep_agent  # lazy
    from deepagents.backends.utils import file_data_to_string  # lazy

    from local_pdf.agent.build import _build_model  # lazy
    from local_pdf.agent.extract_prompts import OKF_EXTRACTION

    agent = create_deep_agent(
        model=model or _build_model(),
        tools=[],
        system_prompt=OKF_EXTRACTION,
    )
    result = agent.invoke({"messages": [{"role": "user", "content": interview_text}]})
    files: dict = result.get("files", {})  # virtual-FS: path -> file data
    written: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir.resolve()
    for vpath, data in files.items():
        rel = vpath.lstrip("/")
        dest = (out_dir / rel).resolve()
        # Containment guard: a model emitting `../foo.md` must not escape out_dir
        # (mirrors the reader's _safe_concept_path on the write side).
        if dest != base and base not in dest.parents:
            raise ValueError(f"agent tried to write outside the base dir: {vpath!r}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(file_data_to_string(data), encoding="utf-8")
        written.append(rel)
    return written
