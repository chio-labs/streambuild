"""Assemble direct execution results from completed shared population work."""

from streambuild.adapter.models import AdapterOwnershipRecord
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.planner.models import DirectPlan
from streambuild.executor.direct.models import (
    DirectBuildRequest,
    DirectBuildResult,
    DirectReplayBoundary,
    DirectRootReplayResult,
)
from streambuild.executor.population.models import (
    PopulationPlan,
    PopulationResult,
    PopulationWatermark,
)


def build_direct_execution_result(
    *,
    request: DirectBuildRequest,
    population_plan: PopulationPlan,
    population: PopulationResult,
    ownership_records: tuple[AdapterOwnershipRecord, ...],
    dropped_relation_names: tuple[str, ...],
) -> DirectBuildResult:
    """Build the truthful direct result from actual shared population outcomes."""

    return DirectBuildResult(
        database=request.database,
        ownership_records=ownership_records,
        preserved_source_relation_names=population.preserved_source_relation_names,
        created_source_relation_names=population.created_source_relation_names,
        dropped_relation_names=dropped_relation_names,
        created_relation_names=population.created_relation_names,
        boundary_time=population.boundary_time,
        boundaries=_logical_root_boundaries(
            plan=request.plan,
            population_plan=population_plan,
            population=population,
        ),
        replay_results=tuple(
            DirectRootReplayResult(
                model_name=execution.root_key.name,
                written_rows=execution.written_rows,
            )
            for execution in population.replay_executions
        ),
    )


def resolve_completed_direct_model_names(
    *, plan: DirectPlan, population_plan: PopulationPlan, population: PopulationResult
) -> frozenset[str]:
    """Map completed physical population roots back to logical direct model identities."""

    completed_root_keys: frozenset[ObjectKey] = frozenset(population.completed_root_keys)
    return frozenset(
        direct_root.model_key.name
        for direct_root, population_root in zip(
            plan.replay_roots, population_plan.roots, strict=True
        )
        if population_root.root_key in completed_root_keys
    )


def _logical_root_boundaries(
    *, plan: DirectPlan, population_plan: PopulationPlan, population: PopulationResult
) -> tuple[DirectReplayBoundary, ...]:
    boundaries: list[DirectReplayBoundary] = []
    executed_root_keys: frozenset[ObjectKey] = frozenset(
        execution.root_key for execution in population.replay_executions
    )
    for direct_root, population_root in zip(plan.replay_roots, population_plan.roots, strict=True):
        watermark: PopulationWatermark
        for watermark in population.watermarks:
            if (
                population_root.root_key in executed_root_keys
                and watermark.root_key == population_root.root_key
            ):
                boundaries.append(
                    DirectReplayBoundary(
                        model_name=direct_root.model_key.name,
                        driving_input_relation_name=direct_root.driving_input_relation_name,
                        replay_boundary_mode=population_root.replay_lineage_mode,
                        boundary_key=watermark.boundary_key,
                        cutoff_value=watermark.cutoff_value,
                        cutoff_inclusive=True,
                    )
                )
    return tuple(boundaries)
