"""Durable direct ownership claims recorded before any relation is written."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterOwnershipRecord
from streambuild.adapter.types import AdapterOwningMode
from streambuild.compiler.planner.models import DirectPlan, DirectPlanEntry
from streambuild.executor.direct.models import DirectReplayCoverage


def build_direct_ownership_records(
    *,
    plan: DirectPlan,
    database: str,
    tool_version: str,
    replay_coverage: tuple[DirectReplayCoverage, ...],
) -> tuple[AdapterOwnershipRecord, ...]:
    """Claim every relation the planned closure will create or replace."""

    records: list[AdapterOwnershipRecord] = []
    entry: DirectPlanEntry
    for entry in plan.entries:
        records.extend(
            _entry_records(
                entry=entry,
                database=database,
                tool_version=tool_version,
                replay_coverage=replay_coverage,
            )
        )
    return tuple(records)


def record_direct_ownership(
    *,
    client: AdapterConnection,
    database: str,
    records: tuple[AdapterOwnershipRecord, ...],
) -> None:
    """Persist the ownership claims before the first destructive action."""

    client.record_target_ownership(database=database, records=records)


def claim_direct_ownership(
    *,
    client: AdapterConnection,
    plan: DirectPlan,
    target_database: str,
    metadata_database: str,
    tool_version: str,
    replay_coverage: tuple[DirectReplayCoverage, ...],
) -> tuple[AdapterOwnershipRecord, ...]:
    """Build and persist pre-destructive ownership claims."""

    records: tuple[AdapterOwnershipRecord, ...] = build_direct_ownership_records(
        plan=plan,
        database=target_database,
        tool_version=tool_version,
        replay_coverage=replay_coverage,
    )
    record_direct_ownership(client=client, database=metadata_database, records=records)
    return records


def remove_retired_direct_ownership(
    *, client: AdapterConnection, database: str, plan: DirectPlan
) -> tuple[str, ...]:
    """Remove claims represented only by rename teardown operations."""

    current_relation_names: set[str] = set()
    entry: DirectPlanEntry
    for entry in plan.entries:
        current_relation_names.update(entry.relation_names)
    retired_relation_names: tuple[str, ...] = tuple(
        operation.relation_name
        for operation in plan.teardown_operations
        if operation.relation_name not in current_relation_names
    )
    client.remove_target_ownership(
        database=database,
        target_database=plan.database,
        relation_names=retired_relation_names,
    )
    return retired_relation_names


def finalize_direct_ownership(
    *,
    client: AdapterConnection,
    database: str,
    records: tuple[AdapterOwnershipRecord, ...],
    plan: DirectPlan,
) -> None:
    """Persist completed claims and retire stale rename claims."""

    record_direct_ownership(client=client, database=database, records=records)
    _ = remove_retired_direct_ownership(client=client, database=database, plan=plan)


def _entry_records(
    *,
    entry: DirectPlanEntry,
    database: str,
    tool_version: str,
    replay_coverage: tuple[DirectReplayCoverage, ...],
) -> tuple[AdapterOwnershipRecord, ...]:
    model_coverage: DirectReplayCoverage | None = next(
        (coverage for coverage in replay_coverage if coverage.model_name == entry.model_key.name),
        None,
    )
    return tuple(
        AdapterOwnershipRecord(
            database_name=database,
            relation_name=relation_name,
            resource_kind=resource_kind,
            logical_model_name=entry.model_key.name,
            owning_mode=AdapterOwningMode.DIRECT,
            tool_version=tool_version,
            replay_coverage=() if model_coverage is None else model_coverage.ranges,
        )
        for relation_name, resource_kind in zip(
            entry.relation_names, entry.resource_kinds, strict=True
        )
    )
