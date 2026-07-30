"""Preflight validation performed before a direct build writes anything."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterCapabilityError


def reject_incapable_adapter(*, client: AdapterConnection) -> None:
    """Refuse to build through an adapter that cannot perform direct rebuilds."""

    if not client.capabilities.direct_rebuild:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support direct rebuilds"
        )
