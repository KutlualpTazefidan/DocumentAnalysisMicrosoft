"""Prompt-template store + schema-validating loader.

JSON files under this package hold the templates that drive the
synthetic generator (A.5). Filenames carry both the element type and
the version: `<element_type>_<version>.json`. The loader validates the
filename against the in-file `element_type` / `version` fields so a
rename or content edit can never silently desync.

Schema:
    {
        "version": "v1",
        "element_type": "paragraph" | "table_row" | "list_item",
        "description": "<one-line human description>",
        "template": "<prompt body, with `\\n` for newlines>"
    }

Public API:
    - load_prompt(element_type, version="v1") -> str
    - PromptNotFoundError
    - PromptSchemaError
"""

from __future__ import annotations

import json
from pathlib import Path

__all__ = [
    "PromptNotFoundError",
    "PromptSchemaError",
    "load_prompt",
]

_PROMPTS_DIR: Path = Path(__file__).parent
_REQUIRED_KEYS: tuple[str, ...] = ("version", "element_type", "description", "template")


class PromptNotFoundError(FileNotFoundError):
    """Raised when no prompt file matches the requested
    `<element_type>_<version>.json`."""


class PromptSchemaError(ValueError):
    """Raised when a prompt file is structurally invalid: missing
    keys, mismatched filename↔fields, or non-string values."""


def load_prompt(element_type: str, version: str = "v1") -> str:
    """Return the prompt template string for `element_type` at `version`.

    Resolves `<element_type>_<version>.json` under this package's
    directory, validates the JSON against the schema, asserts that the
    file's `element_type` and `version` fields match the filename, and
    returns the `template` field verbatim.

    Raises:
        PromptNotFoundError: file does not exist.
        PromptSchemaError: file exists but its content is invalid.
    """
    path = _PROMPTS_DIR / f"{element_type}_{version}.json"
    if not path.is_file():
        raise PromptNotFoundError(
            f"No prompt template at {path} (element_type={element_type!r}, version={version!r})"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PromptSchemaError(f"{path.name}: invalid JSON ({e.msg})") from e

    missing = [k for k in _REQUIRED_KEYS if k not in data]
    if missing:
        raise PromptSchemaError(f"{path.name}: missing required keys: {missing!r}")

    if data["element_type"] != element_type:
        raise PromptSchemaError(
            f"{path.name}: filename element_type={element_type!r} "
            f"!= JSON element_type={data['element_type']!r}"
        )
    if data["version"] != version:
        raise PromptSchemaError(
            f"{path.name}: filename version={version!r} != JSON version={data['version']!r}"
        )

    template = data["template"]
    if not isinstance(template, str) or not template:
        raise PromptSchemaError(f"{path.name}: `template` must be a non-empty string")
    return template
