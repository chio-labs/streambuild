"""Metadata persistence for backfill bootstrap execution."""

from dataclasses import asdict

from streambuild.clickhouse.metadata_state.main.build_metadata_state_insert_statements import (
    build_metadata_state_insert_statements,
)
from streambuild.clickhouse.metadata_state.main.render_metadata_state_statements import (
    render_metadata_state_statements,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement
from streambuild.compiler.actual_state.main.build_normalized_fingerprint import (
    build_normalized_fingerprint,
)
from streambuild.compiler.metadata_state.main import build_metadata_state
from streambuild.compiler.metadata_state.models import (
    DeploymentRecord,
    DeploymentRuntimeDetailRecord,
    MetadataState,
    ObjectStateRecord,
    PreparedObjectMapping,
)
from streambuild.compiler.planner._helpers.types import DesiredObject
from streambuild.compiler.planner.models import DeploymentPlan, RebuildSubtree
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    RAW_TABLE_NAME_PREFIX,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.shared.models import DesiredMaterializedView, ObjectKey
from streambuild.executor.backfill._helpers.reporting import (
    filter_root_backfill_reports_for_deployment,
)
from streambuild.executor.backfill.constants import DEPLOYMENT_STATUS_BACKFILLING
from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.executor.backfill.models import RootBackfillReport
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.spec.models.types import ReplayLineageMode


def ensure_database_exists(*, client: ClickHouseClient, database: str) -> None:
    """Create a ClickHouse database if it does not already exist."""

    client.command(f"CREATE DATABASE IF NOT EXISTS {database}")


def ensure_metadata_tables(*, client: ClickHouseClient, metadata_database: str) -> None:
    """Create metadata state tables required for backfill bootstrap."""

    ensure_database_exists(client=client, database=metadata_database)
    statements: tuple[RenderedClickHouseStatement, ...] = render_metadata_state_statements(
        metadata_database
    )
    statement: RenderedClickHouseStatement
    for statement in statements:
        client.command(statement.sql)


def persist_deployment_metadata(
    *,
    client: ClickHouseClient,
    metadata_database: str,
    deployment_plan: DeploymentPlan,
    desired_objects: tuple[DesiredObject, ...],
    deployment_id: str,
    created_at: str,
    replay_lineage_mode: ReplayLineageMode,
    root_reports: tuple[RootBackfillReport, ...],
) -> None:
    """Persist the staged deployment boundary for bootstrap execution."""

    metadata_state: MetadataState = build_metadata_state(
        object_states=_build_object_state_records(
            desired_objects=desired_objects,
            deployment_id=deployment_id,
            recorded_at=created_at,
        ),
        deployments=(
            DeploymentRecord(
                deployment_id=deployment_id,
                created_at=created_at,
                status=DEPLOYMENT_STATUS_BACKFILLING,
                replay_lineage_mode=replay_lineage_mode,
                selected_root_keys=tuple(
                    subtree.root_key for subtree in deployment_plan.rebuild_subtrees
                ),
                warning_codes=tuple(warning.warning_code for warning in deployment_plan.warnings),
                prepared_object_mappings=tuple(
                    PreparedObjectMapping(
                        logical_key=prepared_object.logical_key,
                        physical_name=prepared_object.physical_name,
                    )
                    for prepared_object in deployment_plan.prepared_shadow_objects
                ),
            ),
        ),
        deployment_watermarks=(),
        deployment_runtime_details=_build_deployment_runtime_detail_records(
            deployment_plan=deployment_plan,
            deployment_id=deployment_id,
            root_reports=root_reports,
            desired_objects=desired_objects,
        ),
        publish_events=(),
    )
    insert_statements: tuple[RenderedClickHouseStatement, ...] = (
        build_metadata_state_insert_statements(
            database=metadata_database,
            object_states=metadata_state.object_states,
            deployments=metadata_state.deployments,
            deployment_watermarks=metadata_state.deployment_watermarks,
            deployment_runtime_details=metadata_state.deployment_runtime_details,
            publish_events=metadata_state.publish_events,
        )
    )
    statement: RenderedClickHouseStatement
    for statement in insert_statements:
        if not statement.rows:
            continue
        client.insert_rows(table=_insert_table_name(statement.sql), rows=statement.rows)


def _insert_table_name(statement_sql: str) -> str:
    statement_prefix: str = "INSERT INTO "
    remainder: str = statement_sql[len(statement_prefix) :]
    return remainder.split(" ", 1)[0]


def _build_object_state_records(
    *,
    desired_objects: tuple[DesiredObject, ...],
    deployment_id: str,
    recorded_at: str,
) -> tuple[ObjectStateRecord, ...]:
    desired_object: DesiredObject
    records: list[ObjectStateRecord] = []
    for desired_object in desired_objects:
        normalized_query: str | None = None
        if isinstance(desired_object, DesiredMaterializedView):
            normalized_query = desired_object.query
        records.append(
            ObjectStateRecord(
                deployment_id=deployment_id,
                key=ObjectKey(
                    database=desired_object.key.database,
                    object_type=desired_object.key.object_type,
                    name=desired_object.key.name,
                ),
                normalized_fingerprint=build_normalized_fingerprint(asdict(desired_object.spec)),
                normalized_query=normalized_query,
                recorded_at=recorded_at,
            )
        )

    return tuple(records)


def _build_deployment_runtime_detail_records(
    *,
    deployment_plan: DeploymentPlan,
    deployment_id: str,
    root_reports: tuple[RootBackfillReport, ...],
    desired_objects: tuple[DesiredObject, ...],
) -> tuple[DeploymentRuntimeDetailRecord, ...]:
    deployment_root_reports: tuple[RootBackfillReport, ...] = (
        filter_root_backfill_reports_for_deployment(
            root_reports=root_reports, deployment_plan=deployment_plan
        )
    )
    root_materialized_view_by_target_name: dict[str, DesiredMaterializedView] = {
        object_.target_table_name: object_
        for object_ in desired_objects
        if isinstance(object_, DesiredMaterializedView)
    }
    active_deployment_id_by_root_key: dict[ObjectKey, str | None] = {
        root_report.root_key: root_report.active_deployment_id
        for root_report in deployment_root_reports
    }
    prepared_physical_name_by_key: dict[ObjectKey, str] = {
        prepared_object.logical_key: prepared_object.physical_name
        for prepared_object in deployment_plan.prepared_shadow_objects
    }
    records: list[DeploymentRuntimeDetailRecord] = []
    root_report: RootBackfillReport
    for root_report in deployment_root_reports:
        subtree: RebuildSubtree | None = _runtime_detail_subtree_for_live_target(
            rebuild_subtrees=deployment_plan.rebuild_subtrees,
            live_target_key=root_report.root_key,
        )
        if subtree is None:
            root_materialized_view: DesiredMaterializedView | None = (
                root_materialized_view_by_target_name.get(root_report.root_key.name)
            )
            if root_materialized_view is None:
                raise BackfillExecutionError(
                    "Could not resolve deployment runtime detail root "
                    f"'{root_report.root_key.name}' to a selected materialized view target"
                )
            anchor_key: ObjectKey = ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_TABLE,
                name=root_materialized_view.source_table_name,
            )
            live_target_names: tuple[str, ...] = (root_report.root_key.name,)
            execution_mode: str | None = None
            configured_backfill_mode: str | None = None
            execution_lookback_seconds: int | None = None
        else:
            anchor_key = subtree.upstream_boundary_key
            live_target_names = tuple(
                sorted(
                    {
                        key.name
                        for key in subtree.affected_keys
                        if key.object_type == DESIRED_OBJECT_TYPE_TABLE
                        and key.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
                    }
                )
            )
            execution_mode = subtree.execution_mode
            configured_backfill_mode = subtree.configured_backfill_mode
            execution_lookback_seconds = subtree.execution_lookback_seconds
        records.append(
            DeploymentRuntimeDetailRecord(
                deployment_id=deployment_id,
                root_key=root_report.root_key,
                state_kind=root_report.state_kind,
                replay_strategy=root_report.replay_strategy,
                active_deployment_id=active_deployment_id_by_root_key[root_report.root_key],
                anchor_key=anchor_key,
                anchor_physical_name=_runtime_detail_anchor_physical_name(
                    anchor_key=anchor_key,
                    prepared_physical_name_by_key=prepared_physical_name_by_key,
                ),
                execution_mode=execution_mode,
                configured_backfill_mode=configured_backfill_mode,
                execution_lookback_seconds=execution_lookback_seconds,
                live_target_names=live_target_names,
            )
        )
    return tuple(records)


def _runtime_detail_subtree_for_live_target(
    *,
    rebuild_subtrees: tuple[RebuildSubtree, ...],
    live_target_key: ObjectKey,
) -> RebuildSubtree | None:
    subtree: RebuildSubtree
    for subtree in rebuild_subtrees:
        if live_target_key in subtree.affected_keys:
            return subtree
    return None


def _runtime_detail_anchor_physical_name(
    *,
    anchor_key: ObjectKey,
    prepared_physical_name_by_key: dict[ObjectKey, str],
) -> str | None:
    physical_name: str | None = prepared_physical_name_by_key.get(anchor_key)
    if physical_name is not None:
        return physical_name
    if anchor_key.object_type == DESIRED_OBJECT_TYPE_TABLE and anchor_key.name.startswith(
        RAW_TABLE_NAME_PREFIX
    ):
        return anchor_key.name
    return None
