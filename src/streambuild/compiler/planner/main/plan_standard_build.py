"""Public entrypoint for standard-mode execution planning."""

from __future__ import annotations

from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.graph.models import ProjectGraph
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.classes.standard_plan_builder import StandardPlanBuilder
from streambuild.compiler.planner.models import StandardPlan, StandardWarehouseSnapshot


def plan_standard_build(
    *,
    graph: ProjectGraph,
    realized_project: RealizedProject,
    snapshot: StandardWarehouseSnapshot,
    database: str,
    selected_model_keys: frozenset[LogicalResourceKey],
) -> StandardPlan:
    """Plan the complete selected downstream closure without change pruning."""

    return StandardPlanBuilder(
        graph=graph,
        realized_project=realized_project,
        snapshot=snapshot,
        database=database,
        selected_model_keys=selected_model_keys,
    ).build()
