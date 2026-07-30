"""Reject virtual-environment work that would take over direct-owned relations."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterOwnershipRecord
from streambuild.adapter.types import AdapterOwningMode
from streambuild.compiler.planner.exceptions import TargetOwnershipConflictError


def assert_no_direct_owned_targets(
    *,
    client: AdapterConnection,
    metadata_database: str,
    target_database: str,
    relation_names: tuple[str, ...],
) -> None:
    """Refuse virtual-environment writes to any relation direct mode already owns."""

    records: tuple[AdapterOwnershipRecord, ...] = client.load_target_ownership(metadata_database)
    direct_owned_names: frozenset[str] = frozenset(
        record.relation_name
        for record in records
        if record.database_name == target_database
        and record.owning_mode == AdapterOwningMode.DIRECT
    )
    blocked_names: tuple[str, ...] = tuple(
        relation_name for relation_name in relation_names if relation_name in direct_owned_names
    )
    if blocked_names:
        raise TargetOwnershipConflictError(
            "Virtual environments refuse to take over relations owned by direct mode: "
            f"{', '.join(blocked_names)}"
        )
