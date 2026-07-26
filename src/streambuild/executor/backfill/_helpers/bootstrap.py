"""Bootstrap helpers for staged backfill execution."""

from datetime import UTC, datetime
from uuid import uuid4

from streambuild.compiler.actual_state.main.load_actual_state import load_actual_state
from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.planner.main.plan_deployment import plan_deployment
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.executor.backfill._helpers.metadata import (
    ensure_database_exists,
    persist_deployment_metadata,
)
from streambuild.executor.backfill._helpers.shadow_objects import create_shadow_objects
from streambuild.executor.backfill._helpers.timing import build_current_timestamp
from streambuild.executor.backfill.main.build_root_backfill_reports import (
    build_root_backfill_reports,
)
from streambuild.executor.backfill.main.ensure_metadata_tables import ensure_metadata_tables
from streambuild.executor.backfill.main.resolve_unsupported_bounded_replay_behavior import (
    resolve_unsupported_bounded_replay_behavior,
)
from streambuild.executor.backfill.models import (
    BackfillBootstrapRequest,
    BackfillBootstrapResult,
    RootBackfillReport,
)
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.spec.models.types import ReplayLineageMode


def execute_backfill_bootstrap(
    *,
    request: BackfillBootstrapRequest,
    client: ClickHouseClient,
) -> BackfillBootstrapResult:
    """Create the first real staged deployment boundary in ClickHouse."""

    replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(request.replay_lineage_mode)
    created_at: str = request.created_at or build_current_timestamp()
    deployment_id: str = request.deployment_id or _build_deployment_id(created_at)
    actual_state: ActualState = load_actual_state(
        client=client,
        desired_state=request.desired_state,
        database=request.default_database,
    )
    root_reports: tuple[RootBackfillReport, ...] = build_root_backfill_reports(
        client=client,
        desired_state=request.desired_state,
        database=request.default_database,
    )
    deployment_plan: DeploymentPlan = plan_deployment(
        desired_state=request.desired_state,
        actual_state=actual_state,
        default_database=request.default_database,
        deployment_id=deployment_id,
        full_refresh_keys=request.full_refresh_keys,
        start_time_keys=request.start_time_keys,
        start_time=request.start_time,
    )
    deployment_plan = resolve_unsupported_bounded_replay_behavior(
        client=client,
        deployment_plan=deployment_plan,
        desired_state=request.desired_state,
        default_database=request.default_database,
        replay_lineage_mode=replay_lineage_mode,
    )

    ensure_database_exists(client=client, database=request.default_database)
    ensure_metadata_tables(client=client, metadata_database=request.metadata_database)
    persist_deployment_metadata(
        client=client,
        metadata_database=request.metadata_database,
        deployment_plan=deployment_plan,
        desired_objects=request.desired_state.objects,
        deployment_id=deployment_id,
        created_at=created_at,
        replay_lineage_mode=replay_lineage_mode,
        root_reports=root_reports,
    )
    create_shadow_objects(
        client=client,
        deployment_plan=deployment_plan,
        desired_state=request.desired_state,
        default_database=request.default_database,
    )

    return BackfillBootstrapResult(
        deployment_id=deployment_id,
        created_at=created_at,
        deployment_plan=deployment_plan,
        root_reports=root_reports,
    )


def _build_deployment_id(created_at: str) -> str:
    timestamp: datetime = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=UTC)
    return f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:6]}"
