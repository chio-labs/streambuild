"""Neutral adapter type contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from streambuild.adapter.models import (
        AdapterAdoptedSourceRealizationRequest,
        AdapterManagedSource,
        AdapterManagedSourceRealizationRequest,
        AdapterMaterializedView,
        AdapterModelRealization,
        AdapterModelRealizationRequest,
        AdapterSourceRealization,
        AdapterStableView,
        AdapterTable,
    )


class AdapterReplayBoundaryMode(StrEnum):
    """A replay boundary strategy implemented by an adapter."""

    OFFSETS = "offsets"
    TIMESTAMP = "timestamp"
    LANDED_AT = "landed_at"
    CURSOR = "cursor"


class AdapterReplaySeedMode(StrEnum):
    """How an adapter initializes history before replaying a bounded tail."""

    NONE = "none"
    HISTORY_PREFIX = "history_prefix"


class AdapterReplayLowerBoundMode(StrEnum):
    """How an adapter resolves the inclusive lower edge of replay."""

    NONE = "none"
    FORCED_TIME = "forced_time"
    LOOKBACK = "lookback"
    ACTIVE_FRONTIER = "active_frontier"


class AdapterResourceRenderer(Protocol):
    """Render one neutral resource request for an adapter."""

    def __call__(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> str: ...


class AdapterSourceRealizer(Protocol):
    """Realize one logical managed or adopted source."""

    def __call__(
        self,
        *,
        request: AdapterManagedSourceRealizationRequest | AdapterAdoptedSourceRealizationRequest,
    ) -> AdapterSourceRealization: ...


class AdapterModelRelationNamer(Protocol):
    """Resolve the adapter relation name for one logical model."""

    def __call__(self, *, logical_name: str) -> str: ...


class AdapterModelRealizer(Protocol):
    """Realize one semantically compiled logical model."""

    def __call__(self, *, request: AdapterModelRealizationRequest) -> AdapterModelRealization: ...
