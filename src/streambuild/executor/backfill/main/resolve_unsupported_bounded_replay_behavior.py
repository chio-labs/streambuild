"""Resolve how a root behaves when bounded replay is unsupported."""

from __future__ import annotations

from dataclasses import replace

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.models import DeploymentPlan, RebuildSubtree
from streambuild.executor.backfill._helpers.behavior import (
    _resolve_subtree_behavior,
)


def resolve_unsupported_bounded_replay_behavior(
    *,
    client: AdapterConnection,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    default_database: str,
    replay_lineage_mode: ReplayLineageMode,
) -> DeploymentPlan:
    resolved_subtrees: tuple[RebuildSubtree, ...] = tuple(
        _resolve_subtree_behavior(
            client=client,
            subtree=subtree,
            desired_state=desired_state,
            default_database=default_database,
            replay_lineage_mode=replay_lineage_mode,
        )
        for subtree in deployment_plan.rebuild_subtrees
    )
    return replace(deployment_plan, rebuild_subtrees=resolved_subtrees)
