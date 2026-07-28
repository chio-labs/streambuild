"""Attach and catch up standard model views in dependency order."""

from __future__ import annotations

import time

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.models import StandardPlan, StandardPopulationSegment
from streambuild.executor.standard._helpers.boundaries import (
    capture_population_segment_boundaries,
)
from streambuild.executor.standard._helpers.relations import (
    create_planned_materialized_view,
    target_relation_name_by_model_name,
)
from streambuild.executor.standard._helpers.replay import execute_standard_population_segment
from streambuild.executor.standard.models import (
    StandardPopulationResult,
    StandardReplayBoundary,
)


def execute_standard_population(
    *,
    client: AdapterConnection,
    plan: StandardPlan,
    realized_project: RealizedProject,
    database: str,
    boundary_time: str,
    stabilization_seconds: float,
) -> StandardPopulationResult:
    """Attach each view after its dependencies and populate the model exactly once."""

    target_names: dict[str, str] = target_relation_name_by_model_name(plan=plan)
    created_views: list[str] = []
    boundaries: list[StandardReplayBoundary] = []
    populated_models: list[str] = []
    segment_index: int
    segment: StandardPopulationSegment
    for segment_index, segment in enumerate(plan.population_segments):
        created_views.append(
            create_planned_materialized_view(
                client=client,
                model_key=segment.model_key,
                realized_project=realized_project,
                database=database,
            )
        )
        time.sleep(stabilization_seconds if segment_index == 0 else 0)
        segment_boundaries: tuple[StandardReplayBoundary, ...] = (
            capture_population_segment_boundaries(
                client=client,
                segment=segment,
                database=database,
                target_relation_name=target_names[segment.model_key.name],
            )
        )
        boundaries.extend(segment_boundaries)
        populated_models.append(
            execute_standard_population_segment(
                client=client,
                segment=segment,
                realized_project=realized_project,
                database=database,
                boundary_time=boundary_time,
                boundaries=segment_boundaries,
            )
        )
    return StandardPopulationResult(
        created_view_relation_names=tuple(created_views),
        boundaries=tuple(boundaries),
        populated_model_names=tuple(populated_models),
    )
