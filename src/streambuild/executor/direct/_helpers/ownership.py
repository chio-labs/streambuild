"""Durable direct ownership claims recorded before any relation is written."""

from __future__ import annotations

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
