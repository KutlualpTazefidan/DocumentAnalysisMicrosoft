"""Operations-layer exceptions.

Mapped to HTTP statuses by the future FastAPI layer (Phase A-Plus):
- EntryNotFoundError    → 404 Not Found
- EntryDeprecatedError  → 409 Conflict

The base classes (LookupError / ValueError) let consumers dispatch on
standard Python exceptions without importing this module directly."""


class EntryNotFoundError(LookupError):
    """Raised when an operation targets an entry_id that is not present
    in the projected state."""


class EntryDeprecatedError(ValueError):
    """Raised when an operation targets an entry that is already
    deprecated. Re-deprecation, reviewing a deprecated entry, and
    refining a deprecated entry all raise this."""
