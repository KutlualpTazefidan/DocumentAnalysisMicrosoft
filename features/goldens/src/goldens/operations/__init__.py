"""Operations layer — semantic API on top of the event log."""

from goldens.operations.deprecate import deprecate
from goldens.operations.errors import EntryDeprecatedError, EntryNotFoundError
from goldens.operations.refine import refine

__all__ = [
    "EntryDeprecatedError",
    "EntryNotFoundError",
    "deprecate",
    "refine",
]
