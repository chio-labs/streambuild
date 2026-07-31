from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterQueryResult, AdapterReplayRequest, AdapterReplayResult
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.models import DeploymentPlan, DeploymentWatermarkRecord
from streambuild.executor.population._helpers.replay import execute_population_replay
from streambuild.executor.population.models import (
    PopulationObject,
    PopulationPlan,
    PopulationRoot,
    PopulationWatermark,
)


class RecordingReplayConnection:
    def __init__(self) -> None:
        self.requests: list[AdapterReplayRequest] = []

    def execute_replay(self, request: AdapterReplayRequest) -> AdapterReplayResult:
        self.requests.append(request)
        return AdapterReplayResult(written_rows=None)

    def query(self, statement: str) -> AdapterQueryResult:
        del statement
        return AdapterQueryResult(rows=((1,),))


def capture_replay_requests(
    *,
    connection: RecordingReplayConnection,
    mode: ReplayLineageMode,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    watermarks: tuple[DeploymentWatermarkRecord, ...],
) -> tuple[AdapterReplayRequest, ...]:
    plan: PopulationPlan = PopulationPlan(
        execution_id=deployment_plan.deployment_id or "test",
        roots=tuple(
            PopulationRoot(
                root_key=subtree.root_key,
                affected_keys=subtree.affected_keys,
                upstream_boundary_key=subtree.upstream_boundary_key,
                replay_lineage_mode=mode,
                execution_mode=subtree.execution_mode,
                forced_start_time=subtree.forced_start_time,
                execution_lookback_seconds=subtree.execution_lookback_seconds,
            )
            for subtree in deployment_plan.rebuild_subtrees
        ),
        objects=tuple(
            PopulationObject(logical_key=prepared.logical_key, physical_name=prepared.physical_name)
            for prepared in deployment_plan.prepared_shadow_objects
        ),
    )
    _ = execute_population_replay(
        client=cast(AdapterConnection, connection),
        plan=plan,
        desired_state=desired_state,
        default_database="analytics",
        watermarks=tuple(
            PopulationWatermark(
                root_key=watermark.root_key,
                anchor_key=watermark.anchor_key,
                boundary_key=watermark.boundary_key,
                cutoff_value=watermark.cutoff_value,
            )
            for watermark in watermarks
        ),
        boundary_time="2026-04-08 13:00:00.000",
    )
    return tuple(connection.requests)
