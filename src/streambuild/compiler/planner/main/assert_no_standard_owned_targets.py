"""Reject virtual-environment work that would take over standard-owned relations."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterOwnershipRecord
from streambuild.adapter.types import AdapterOwningMode
from streambuild.compiler.planner.exceptions import TargetOwnershipConflictError


def assert_no_standard_owned_targets(
    *,
    client: AdapterConnection,
    database: str,
    relation_names: tuple[str, ...],
) -> None:
    """Refuse virtual-environment writes to any relation standard mode already owns."""

    records: tuple[AdapterOwnershipRecord, ...] = client.load_target_ownership(database)
    standard_owned_names: frozenset[str] = frozenset(
        record.relation_name
        for record in records
        if record.owning_mode == AdapterOwningMode.STANDARD
    )
    blocked_names: tuple[str, ...] = tuple(
        relation_name for relation_name in relation_names if relation_name in standard_owned_names
    )
    if blocked_names:
        raise TargetOwnershipConflictError(
            "Virtual environments refuse to take over relations owned by standard mode: "
            f"{', '.join(blocked_names)}"
        )
