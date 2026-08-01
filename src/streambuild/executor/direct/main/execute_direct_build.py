"""Public entrypoint that realizes one planned direct closure end to end."""

from __future__ import annotations

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterOwnershipRecord, CatalogSnapshot
from streambuild.executor.direct._helpers.execution_result import (
    build_direct_execution_result,
    resolve_completed_direct_model_names,
)
from streambuild.executor.direct._helpers.ownership import (
    build_direct_ownership_records,
    claim_direct_ownership,
    finalize_direct_ownership,
)
from streambuild.executor.direct._helpers.population_plan import build_direct_population_plan
from streambuild.executor.direct._helpers.preflight import reject_incapable_adapter
from streambuild.executor.direct._helpers.relations import (
    drop_planned_relations,
    target_relation_name_by_model_name,
)
from streambuild.executor.direct._helpers.retention import (
    assert_preserved_history_covers_ranges,
    capture_completed_replay_coverage,
    resolve_required_replay_coverage,
)
from streambuild.executor.direct._helpers.sources import (
    prepare_preserved_managed_sources,
)
from streambuild.executor.direct.models import (
    DirectBuildRequest,
    DirectBuildResult,
    DirectReplayCoverage,
)
from streambuild.executor.population.main._execute_population import execute_population
from streambuild.executor.population.models import (
    PopulationPlan,
    PopulationRequest,
    PopulationResult,
    PopulationSourcePreparation,
)


def execute_direct_build(
    *, request: DirectBuildRequest, client: AdapterConnection
) -> DirectBuildResult:
    """Preserve sources, claim ownership, rebuild targets, and replay preserved history."""

    reject_incapable_adapter(client=client)
    client.ensure_database(request.database)
    client.migrate_metadata_state(request.metadata_database)
    catalog: CatalogSnapshot = client.load_catalog(request.database)
    target_relation_names: dict[str, str] = target_relation_name_by_model_name(plan=request.plan)
    existing_ownership: tuple[AdapterOwnershipRecord, ...] = client.load_target_ownership(
        request.metadata_database
    )
    source_preparation: PopulationSourcePreparation = prepare_preserved_managed_sources(
        client=client,
        realized_project=request.realized_project,
        catalog=catalog,
        database=request.database,
    )
    replay_coverage: tuple[DirectReplayCoverage, ...] = resolve_required_replay_coverage(
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
    _ = claim_direct_ownership(
        client=client,
        plan=request.plan,
        target_database=request.database,
        metadata_database=request.metadata_database,
        tool_version=request.tool_version,
        replay_coverage=replay_coverage,
    )
    dropped: tuple[str, ...] = drop_planned_relations(
        client=client, plan=request.plan, database=request.database
    )
    population_plan: PopulationPlan = build_direct_population_plan(
        plan=request.plan,
        realized_project=request.realized_project,
    )
    population: PopulationResult = execute_population(
        request=PopulationRequest(
            plan=population_plan,
            desired_state=request.realized_project.desired_state,
            default_database=request.database,
            source_preparation=source_preparation,
            stabilization_seconds=request.stabilization_seconds,
            boundary_time=request.boundary_time,
        ),
        client=client,
    )
    completed_ownership_records: tuple[AdapterOwnershipRecord, ...] = _finalize_ownership(
        request=request,
        client=client,
        completed_model_names=resolve_completed_direct_model_names(
            plan=request.plan,
            population_plan=population_plan,
            population=population,
        ),
        preflight_replay_coverage=replay_coverage,
    )
    return build_direct_execution_result(
        request=request,
        population_plan=population_plan,
        population=population,
        ownership_records=completed_ownership_records,
        dropped_relation_names=dropped,
    )


def _finalize_ownership(
    *,
    request: DirectBuildRequest,
    client: AdapterConnection,
    completed_model_names: frozenset[str],
    preflight_replay_coverage: tuple[DirectReplayCoverage, ...],
) -> tuple[AdapterOwnershipRecord, ...]:
    completed_coverage: tuple[DirectReplayCoverage, ...] = capture_completed_replay_coverage(
        client=client,
        plan=request.plan,
        database=request.database,
        completed_model_names=completed_model_names,
    )
    completed_coverage_by_model_name: dict[str, DirectReplayCoverage] = {
        coverage.model_name: coverage for coverage in completed_coverage
    }
    finalized_coverage: tuple[DirectReplayCoverage, ...] = tuple(
        completed_coverage_by_model_name.get(coverage.model_name, coverage)
        for coverage in preflight_replay_coverage
    )
    records: tuple[AdapterOwnershipRecord, ...] = build_direct_ownership_records(
        plan=request.plan,
        database=request.database,
        tool_version=request.tool_version,
        replay_coverage=finalized_coverage,
    )
    finalize_direct_ownership(
        client=client,
        database=request.metadata_database,
        records=records,
        plan=request.plan,
    )
    return records
