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
    for vpath, data in files.items():
        rel = vpath.lstrip("/")
        dest = out_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(file_data_to_string(data), encoding="utf-8")
        written.append(rel)
    return written
