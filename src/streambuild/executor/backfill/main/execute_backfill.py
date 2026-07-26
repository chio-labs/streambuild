"""Backfill execution entrypoint."""

from streambuild.compiler.metadata_state.models import DeploymentWatermarkRecord
from streambuild.executor.backfill._helpers.bootstrap import execute_backfill_bootstrap
from streambuild.executor.backfill._helpers.replay import (
    execute_offset_replay,
    execute_scalar_replay,
)
from streambuild.executor.backfill._helpers.timing import (
    build_current_timestamp,
    wait_for_shadow_stabilization,
)
from streambuild.executor.backfill._helpers.watermarks import (
    persist_deployment_watermarks,
    resolve_cursor_watermarks,
    resolve_offset_watermarks,
    resolve_scalar_watermarks,
)
from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.executor.backfill.models import (
    BackfillBootstrapRequest,
    BackfillBootstrapResult,
    BackfillExecutionResult,
)
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.spec.types import ReplayLineageMode


def execute_backfill(
    *,
    request: BackfillBootstrapRequest,
    client: ClickHouseClient,
) -> BackfillExecutionResult:
    """Execute staged backfill through boundary capture and supported replay steps."""

    replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(request.replay_lineage_mode)
    bootstrap_result: BackfillBootstrapResult = execute_backfill_bootstrap(
        request=request, client=client
    )
    wait_for_shadow_stabilization(request.stabilization_seconds)
    boundary_time: str = request.boundary_time or build_current_timestamp()
    if replay_lineage_mode in {
        ReplayLineageMode.TIMESTAMP,
        ReplayLineageMode.LANDED_AT,
        ReplayLineageMode.CURSOR,
    }:
        deployment_watermarks: tuple[DeploymentWatermarkRecord, ...]
        if replay_lineage_mode == ReplayLineageMode.CURSOR:
            deployment_watermarks = resolve_cursor_watermarks(
                client=client,
                deployment_id=bootstrap_result.deployment_id,
                deployment_plan=bootstrap_result.deployment_plan,
                desired_state=request.desired_state,
                default_database=request.default_database,
            )
        else:
            deployment_watermarks = resolve_scalar_watermarks(
                deployment_id=bootstrap_result.deployment_id,
                deployment_plan=bootstrap_result.deployment_plan,
                desired_state=request.desired_state,
                replay_lineage_mode=replay_lineage_mode,
                boundary_time=boundary_time,
            )
        persist_deployment_watermarks(
            client=client,
            metadata_database=request.metadata_database,
            deployment_watermarks=deployment_watermarks,
        )
        execute_scalar_replay(
            client=client,
            deployment_plan=bootstrap_result.deployment_plan,
            desired_state=request.desired_state,
            default_database=request.default_database,
            replay_lineage_mode=replay_lineage_mode,
            deployment_watermarks=deployment_watermarks,
            boundary_time=boundary_time,
        )
        return BackfillExecutionResult(
            bootstrap=bootstrap_result,
            boundary_time=boundary_time,
        )

    if replay_lineage_mode == ReplayLineageMode.OFFSETS:
        deployment_watermarks: tuple[DeploymentWatermarkRecord, ...] = resolve_offset_watermarks(
            client=client,
            deployment_id=bootstrap_result.deployment_id,
            deployment_plan=bootstrap_result.deployment_plan,
            desired_state=request.desired_state,
            default_database=request.default_database,
            boundary_time=boundary_time,
        )
        persist_deployment_watermarks(
            client=client,
            metadata_database=request.metadata_database,
            deployment_watermarks=deployment_watermarks,
        )
        execute_offset_replay(
            client=client,
            deployment_plan=bootstrap_result.deployment_plan,
            desired_state=request.desired_state,
            default_database=request.default_database,
            deployment_watermarks=deployment_watermarks,
            boundary_time=boundary_time,
        )
        return BackfillExecutionResult(
            bootstrap=bootstrap_result,
            boundary_time=boundary_time,
        )

    raise BackfillExecutionError(
        f"Backfill execution does not yet support replay mode '{request.replay_lineage_mode}'"
    )
