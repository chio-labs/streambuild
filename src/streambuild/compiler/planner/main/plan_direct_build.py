"""Public entrypoint for direct-mode execution planning."""

from __future__ import annotations

from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.graph.models import ProjectGraph
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.classes.direct_plan_builder import DirectPlanBuilder
from streambuild.compiler.planner.models import DirectPlan, DirectWarehouseSnapshot
from streambuild.compiler.planner.types import DirectSelectionMode


def plan_direct_build(
    *,
    graph: ProjectGraph,
    realized_project: RealizedProject,
    snapshot: DirectWarehouseSnapshot,
    database: str,
    selected_model_keys: frozenset[LogicalResourceKey],
    selection_mode: DirectSelectionMode | None = None,
    include_missing_upstream: bool = False,
    effective_start_time: str | None = None,
) -> DirectPlan:
    """Plan the complete selected downstream closure without change pruning."""

    resolved_selection_mode: DirectSelectionMode = selection_mode or (
        DirectSelectionMode.EXPLICIT if selected_model_keys else DirectSelectionMode.ALL_MODELS
    )
    return DirectPlanBuilder(
        graph=graph,
        realized_project=realized_project,
        snapshot=snapshot,
        database=database,
        selected_model_keys=selected_model_keys,
        selection_mode=resolved_selection_mode,
        include_missing_upstream=include_missing_upstream,
        effective_start_time=effective_start_time,
    ).build()
