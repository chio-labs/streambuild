"""Extract logical source and model refs from model SQL."""

from __future__ import annotations

from streambuild.compiler.compile._helpers.refs import (
    _extract_refs_tuple,
)
from streambuild.compiler.compile.models import ParsedRef


def extract_refs(sql: str) -> list[ParsedRef]:
    """Return parsed logical node refs referenced by `__source(...)` and `__ref(...)`."""

    return list(_extract_refs_tuple(sql))
