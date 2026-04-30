"""Hand-rolled TOML writer for the two creation-layer config files
(identity.toml, positions.toml). Happy-path only (D14): top-level
scalar keys (str, int) and one nested table of str -> str. Anything
else raises TypeError so callers fail loud rather than silently
emitting malformed TOML."""

from __future__ import annotations


def _escape_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _emit_scalar(key: str, value: object) -> str:
    if isinstance(value, bool):
        raise TypeError(f"unsupported scalar type bool for key {key!r}")
    if isinstance(value, str):
        return f"{key} = {_escape_string(value)}"
    if isinstance(value, int):
        return f"{key} = {value}"
    raise TypeError(f"unsupported scalar type {type(value).__name__} for key {key!r}")


def _emit_table(name: str, table: dict[str, object]) -> list[str]:
    lines = [f"[{name}]"]
    for k, v in table.items():
        if not isinstance(v, str):
            raise TypeError(
                f"unsupported value type {type(v).__name__} in table {name!r} for key {k!r}"
            )
        lines.append(f'"{k}" = {_escape_string(v)}')
    return lines


def dump_toml(data: dict[str, object]) -> str:
    """Serialise `data` to TOML. See module docstring for the supported shape."""
    scalar_lines: list[str] = []
    table_lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            if table_lines:
                raise TypeError("only one nested table supported")
            table_lines.extend(_emit_table(key, value))
        else:
            scalar_lines.append(_emit_scalar(key, value))
    parts: list[str] = []
    parts.extend(scalar_lines)
    if table_lines:
        if parts:
            parts.append("")
        parts.extend(table_lines)
    return "\n".join(parts) + "\n"
