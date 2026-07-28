from collections.abc import Callable
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterReplayRequest
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.models import DeploymentPlan, DeploymentWatermarkRecord
from streambuild.executor.backfill._helpers.replay import (
    execute_offset_replay,
    execute_scalar_replay,
)


class RecordingReplayConnection:
    def __init__(self) -> None:
        self.requests: list[AdapterReplayRequest] = []

    def execute_replay(self, request: AdapterReplayRequest) -> None:
        self.requests.append(request)


def capture_replay_requests(
    *,
    connection: RecordingReplayConnection,
    mode: ReplayLineageMode,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    watermarks: tuple[DeploymentWatermarkRecord, ...],
) -> tuple[AdapterReplayRequest, ...]:
    runner: Callable[..., None] = {
        ReplayLineageMode.OFFSETS: _capture_offset_requests,
        ReplayLineageMode.TIMESTAMP: _capture_scalar_requests,
        ReplayLineageMode.LANDED_AT: _capture_scalar_requests,
        ReplayLineageMode.CURSOR: _capture_scalar_requests,
    }[mode]
    runner(
        connection=connection,
        mode=mode,
        deployment_plan=deployment_plan,
        desired_state=desired_state,
        watermarks=watermarks,
    )
    return tuple(connection.requests)


def _capture_offset_requests(
    *,
    connection: RecordingReplayConnection,
    mode: ReplayLineageMode,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    watermarks: tuple[DeploymentWatermarkRecord, ...],
) -> None:
    del mode
    execute_offset_replay(
        client=cast(AdapterConnection, connection),
        deployment_plan=deployment_plan,
        desired_state=desired_state,
        default_database="analytics",
        deployment_watermarks=watermarks,
        boundary_time="2026-04-08 13:00:00.000",
    )


def _capture_scalar_requests(
    *,
    connection: RecordingReplayConnection,
    mode: ReplayLineageMode,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    watermarks: tuple[DeploymentWatermarkRecord, ...],
) -> None:
    execute_scalar_replay(
        client=cast(AdapterConnection, connection),
        deployment_plan=deployment_plan,
        desired_state=desired_state,
        default_database="analytics",
        replay_lineage_mode=mode,
        deployment_watermarks=watermarks,
        boundary_time="2026-04-08 13:00:00.000",
    )
