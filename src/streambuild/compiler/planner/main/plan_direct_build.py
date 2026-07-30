"""Public entrypoint for direct-mode execution planning."""

from __future__ import annotations

from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.graph.models import ProjectGraph
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.classes.direct_plan_builder import DirectPlanBuilder
from streambuild.compiler.planner.models import DirectPlan, DirectWarehouseSnapshot


def plan_direct_build(
    *,
    graph: ProjectGraph,
    realized_project: RealizedProject,
    snapshot: DirectWarehouseSnapshot,
    database: str,
    selected_model_keys: frozenset[LogicalResourceKey],
) -> DirectPlan:
    """Plan the complete selected downstream closure without change pruning."""

    return DirectPlanBuilder(
        graph=graph,
        realized_project=realized_project,
        snapshot=snapshot,
        database=database,
        selected_model_keys=selected_model_keys,
    ).build()
