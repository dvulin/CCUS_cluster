"""Input/output adapters for the core package (no UI code)."""

from __future__ import annotations

from .commented_json import (
    FIELD_METADATA,
    dump,
    dump_file,
    from_payload,
    load,
    load_file,
    unwrap,
)

__all__ = [
    "FIELD_METADATA",
    "dump",
    "dump_file",
    "from_payload",
    "load",
    "load_file",
    "unwrap",
]