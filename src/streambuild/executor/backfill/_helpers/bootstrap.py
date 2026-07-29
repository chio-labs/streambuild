"""Bootstrap helpers for staged backfill execution."""

from datetime import UTC, datetime
from uuid import uuid4

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.constants import MANAGED_SOURCE_KIND_KAFKA
from streambuild.adapter.exceptions import AdapterCapabilityError
from streambuild.adapter.types import AdapterReplayBoundaryMode
from streambuild.compiler.compile.models import DesiredKafkaTable
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.constants import REBUILD_EXECUTION_MODE_SEEDED_BOUNDED
from streambuild.compiler.planner.main.load_actual_state_from_snapshot import (
    load_actual_state_from_snapshot,
)
from streambuild.compiler.planner.main.load_planning_warehouse_snapshot import (
    load_planning_warehouse_snapshot,
)
from streambuild.compiler.planner.main.plan_deployment import plan_deployment
from streambuild.compiler.planner.models import (
    ActualState,
    DeploymentPlan,
    PlanningWarehouseSnapshot,
)
from streambuild.executor.backfill._helpers.metadata import (
    persist_deployment_metadata,
)
from streambuild.executor.backfill._helpers.sources import ensure_live_landing_objects
from streambuild.executor.backfill._helpers.timing import build_current_timestamp
from streambuild.executor.backfill.main._ensure_metadata_tables import ensure_metadata_tables
from streambuild.executor.backfill.main.build_root_backfill_reports import (
    build_root_backfill_reports,
)
from streambuild.executor.backfill.main.resolve_unsupported_bounded_replay_behavior import (
    resolve_unsupported_bounded_replay_behavior,
)
from streambuild.executor.backfill.models import (
    BackfillBootstrapRequest,
    BackfillBootstrapResult,
    RootBackfillReport,
)


def execute_backfill_bootstrap(
    *,
    request: BackfillBootstrapRequest,
    client: AdapterConnection,
) -> BackfillBootstrapResult:
    """Create the first real staged deployment boundary in ClickHouse."""

    _validate_managed_source_capabilities(request=request, client=client)
    _validate_replay_boundary_capability(request=request, client=client)
    replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(request.replay_lineage_mode)
    created_at: str = request.created_at or build_current_timestamp()
    deployment_id: str = request.deployment_id or _build_deployment_id(created_at)
    snapshot: PlanningWarehouseSnapshot = load_planning_warehouse_snapshot(
        client=client,
        database=request.default_database,
    )
    actual_state: ActualState = load_actual_state_from_snapshot(
        snapshot=snapshot,
        desired_state=request.desired_state,
        database=request.default_database,
    )
    root_reports: tuple[RootBackfillReport, ...] = build_root_backfill_reports(
        catalog=snapshot.catalog,
        desired_state=request.desired_state,
    )
    deployment_plan: DeploymentPlan = plan_deployment(
        desired_state=request.desired_state,
        actual_state=actual_state,
        default_database=request.default_database,
        render_resource=client.render_resource,
        deployment_id=deployment_id,
        full_refresh_keys=request.full_refresh_keys,
        start_time_keys=request.start_time_keys,
        start_time=request.start_time,
    )
    deployment_plan = resolve_unsupported_bounded_replay_behavior(
        catalog=snapshot.catalog,
        deployment_plan=deployment_plan,
        desired_state=request.desired_state,
        default_database=request.default_database,
        replay_lineage_mode=replay_lineage_mode,
    )
    _validate_history_prefix_capability(deployment_plan=deployment_plan, client=client)

    client.ensure_database(request.default_database)
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
    ensure_live_landing_objects(
        client=client,
        desired_state=request.desired_state,
        default_database=request.default_database,
        existing_relation_names=snapshot.catalog.relation_names(),
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


def _validate_managed_source_capabilities(
    *, request: BackfillBootstrapRequest, client: AdapterConnection
) -> None:
    requires_kafka: bool = any(
        isinstance(desired_object, DesiredKafkaTable)
        for desired_object in request.desired_state.objects
    )
    if requires_kafka and MANAGED_SOURCE_KIND_KAFKA not in client.capabilities.managed_source_kinds:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support managed source kind "
            f"'{MANAGED_SOURCE_KIND_KAFKA}'"
        )


def _validate_replay_boundary_capability(
    *, request: BackfillBootstrapRequest, client: AdapterConnection
) -> None:
    mode: AdapterReplayBoundaryMode = AdapterReplayBoundaryMode(request.replay_lineage_mode)
    if mode not in client.capabilities.replay_boundary_modes:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support replay boundary mode "
            f"'{mode}'"
        )


def _validate_history_prefix_capability(
    *, deployment_plan: DeploymentPlan, client: AdapterConnection
) -> None:
    requires_history_prefix: bool = any(
        subtree.execution_mode == REBUILD_EXECUTION_MODE_SEEDED_BOUNDED
        for subtree in deployment_plan.rebuild_subtrees
    )
    if requires_history_prefix and not client.capabilities.history_prefix_seed:
        raise AdapterCapabilityError(
            f"Adapter '{client.adapter_identity.name}' does not support history-prefix seeding"
        )
