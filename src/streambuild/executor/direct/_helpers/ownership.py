"""Durable direct ownership claims recorded before any relation is written."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterOwnershipRecord
from streambuild.adapter.types import AdapterOwningMode
from streambuild.compiler.planner.models import DirectPlan, DirectPlanEntry
from streambuild.executor.direct.constants import (
    DIRECT_TABLE_RESOURCE_KIND,
    DIRECT_VIEW_RESOURCE_KIND,
    MODEL_TABLE_RELATION_INDEX,
    MODEL_VIEW_RELATION_INDEX,
)
from streambuild.executor.direct.models import DirectReplayCoverage

_RESOURCE_KIND_BY_RELATION_INDEX: dict[int, str] = {
    MODEL_TABLE_RELATION_INDEX: DIRECT_TABLE_RESOURCE_KIND,
    MODEL_VIEW_RELATION_INDEX: DIRECT_VIEW_RESOURCE_KIND,
}


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
            resource_kind=_RESOURCE_KIND_BY_RELATION_INDEX[relation_index],
            logical_model_name=entry.model_key.name,
            owning_mode=AdapterOwningMode.DIRECT,
            tool_version=tool_version,
            replay_coverage=() if model_coverage is None else model_coverage.ranges,
        )
        for relation_index, relation_name in enumerate(entry.relation_names)
    )
