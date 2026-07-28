"""Public entrypoint that realizes one planned standard closure end to end."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterOwnershipRecord, CatalogSnapshot
from streambuild.compiler.planner.models import StandardPlan
from streambuild.executor.standard._helpers.ownership import (
    build_standard_ownership_records,
    record_standard_ownership,
)
from streambuild.executor.standard._helpers.population import execute_standard_population
from streambuild.executor.standard._helpers.preflight import (
    current_boundary_time,
    reject_incapable_adapter,
)
from streambuild.executor.standard._helpers.relations import (
    create_planned_tables,
    drop_planned_relations,
    target_relation_name_by_model_name,
)
from streambuild.executor.standard._helpers.retention import (
    assert_preserved_history_covers_ranges,
    capture_completed_replay_coverage,
    resolve_required_replay_coverage,
)
from streambuild.executor.standard._helpers.sources import (
    PreservedSourceRealization,
    preserve_managed_sources,
)
from streambuild.executor.standard.models import (
    StandardBuildRequest,
    StandardBuildResult,
    StandardPopulationResult,
    StandardReplayBoundary,
    StandardReplayCoverage,
)


def execute_standard_build(
    *, request: StandardBuildRequest, client: AdapterConnection
) -> StandardBuildResult:
    """Preserve sources, claim ownership, rebuild targets, and replay preserved history."""

    reject_incapable_adapter(client=client)
    client.ensure_database(request.database)
    client.migrate_metadata_state(request.metadata_database)
    catalog: CatalogSnapshot = client.load_catalog(request.database)
    target_relation_names: dict[str, str] = target_relation_name_by_model_name(plan=request.plan)
    existing_ownership: tuple[AdapterOwnershipRecord, ...] = client.load_target_ownership(
        request.metadata_database
    )
    preserved: PreservedSourceRealization = preserve_managed_sources(
        client=client,
        realized_project=request.realized_project,
        catalog=catalog,
        database=request.database,
    )
    replay_coverage: tuple[StandardReplayCoverage, ...] = resolve_required_replay_coverage(
        client=client,
        plan=request.plan,
        database=request.database,
        existing_relation_names=catalog.relation_names(),
        existing_ownership=existing_ownership,
        target_relation_name_by_model_name=target_relation_names,
    )
    assert_preserved_history_covers_ranges(
        client=client, replay_coverage=replay_coverage, database=request.database
    )
    ownership_records: tuple[AdapterOwnershipRecord, ...] = build_standard_ownership_records(
        plan=request.plan,
        database=request.database,
        tool_version=request.tool_version,
        replay_coverage=replay_coverage,
    )
    record_standard_ownership(
        client=client,
        database=request.metadata_database,
        records=ownership_records,
    )
    dropped: tuple[str, ...] = drop_planned_relations(
        client=client, plan=request.plan, database=request.database
    )
    created_tables: tuple[str, ...] = create_planned_tables(
        client=client,
        plan=request.plan,
        realized_project=request.realized_project,
        database=request.database,
    )
    boundary_time: str = request.boundary_time or current_boundary_time()
    population: StandardPopulationResult = execute_standard_population(
        client=client,
        plan=request.plan,
        realized_project=request.realized_project,
        database=request.database,
        boundary_time=boundary_time,
        stabilization_seconds=request.stabilization_seconds,
    )
    completed_coverage: tuple[StandardReplayCoverage, ...] = capture_completed_replay_coverage(
        client=client, plan=request.plan, database=request.database
    )
    completed_ownership_records: tuple[AdapterOwnershipRecord, ...] = (
        build_standard_ownership_records(
            plan=request.plan,
            database=request.database,
            tool_version=request.tool_version,
            replay_coverage=completed_coverage,
        )
    )
    record_standard_ownership(
        client=client,
        database=request.metadata_database,
        records=completed_ownership_records,
    )
    return StandardBuildResult(
        database=request.database,
        ownership_records=completed_ownership_records,
        preserved_source_relation_names=preserved.preserved_relation_names,
        created_source_relation_names=preserved.created_relation_names,
        dropped_relation_names=dropped,
        created_relation_names=(*created_tables, *population.created_view_relation_names),
        boundary_time=boundary_time,
        boundaries=_logical_root_boundaries(plan=request.plan, population=population),
        replayed_model_names=tuple(root.model_key.name for root in request.plan.replay_roots),
    )


def _logical_root_boundaries(
    *, plan: StandardPlan, population: StandardPopulationResult
) -> tuple[StandardReplayBoundary, ...]:
    root_names: frozenset[str] = frozenset(root.model_key.name for root in plan.replay_roots)
    return tuple(
        boundary for boundary in population.boundaries if boundary.model_name in root_names
    )
