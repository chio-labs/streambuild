"""Dev server type declarations."""

from __future__ import annotations

from enum import StrEnum


class CompileStateKind(StrEnum):
    """Whether the held project compile is servable or failing."""

    OK = "ok"
    FAILING = "failing"


class ReplayAnchorReason(StrEnum):
    """Why a model is or is not a replay anchor."""

    ELIGIBLE = "eligible"
    AGGREGATE = "aggregate"
    MUTABLE_REF = "mutable_ref"
    NEVER = "never"
    LINEAGE_LOSS = "lineage_loss"
    VIEW = "view"


class Freshness(StrEnum):
    """Derived source or model freshness against its authored policy."""

    FRESH = "fresh"
    LAGGING = "lagging"
    STALLED = "stalled"
