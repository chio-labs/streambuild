"""Preflight validation performed before a standard build writes anything."""

from __future__ import annotations

from datetime import UTC, datetime

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError


def reject_incapable_adapter(*, client: AdapterConnection) -> None:
    """Refuse to build through an adapter that cannot perform standard rebuilds."""

    if not client.capabilities.standard_rebuild:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support standard rebuilds"
        )


def current_boundary_time() -> str:
    """Return the warehouse-formatted instant separating replay from live rows."""

    return datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
