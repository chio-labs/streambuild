"""User-facing reporting helpers for backfill execution."""

from streambuild.clickhouse.inspect._helpers.deployments import inspect_root_deployment_state
from streambuild.clickhouse.inspect.main import inspect_managed_table_state
from streambuild.clickhouse.inspect.models import (
    InspectedManagedTableState,
    RootDeploymentInspection,
)
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.models import DeploymentPlan, RebuildSubtree
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.shared.models import DesiredTable, ObjectKey
from streambuild.executor.backfill.models import RootBackfillReport
from streambuild.integrations.clickhouse.client import ClickHouseClient


def build_root_backfill_reports(
    *,
    client: ClickHouseClient,
    desired_state: DesiredState,
    database: str,
) -> tuple[RootBackfillReport, ...]:
    """Build user-facing rebuild strategy reports for managed roots."""

    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=database,
    )
    root_keys: tuple[ObjectKey, ...] = tuple(
        object_.key
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
        and object_.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
    )
    return tuple(
        _build_root_backfill_report(
            inspection=inspect_root_deployment_state(
                inspected_state=inspected_state,
                root_key=root_key,
            )
        )
        for root_key in root_keys
    )


def filter_root_backfill_reports_for_deployment(
    *,
    root_reports: tuple[RootBackfillReport, ...],
    deployment_plan: DeploymentPlan,
) -> tuple[RootBackfillReport, ...]:
    deployment_live_target_keys: set[ObjectKey] = set()
    subtree: RebuildSubtree
    for subtree in deployment_plan.rebuild_subtrees:
        key: ObjectKey
        for key in subtree.affected_keys:
            if key.object_type == DESIRED_OBJECT_TYPE_TABLE and key.name.startswith(
                TRANSFORM_TABLE_NAME_PREFIX
            ):
                deployment_live_target_keys.add(key)
    return tuple(
        root_report
        for root_report in root_reports
        if root_report.root_key in deployment_live_target_keys
    )


def _build_root_backfill_report(inspection: RootDeploymentInspection) -> RootBackfillReport:
    replay_strategy_by_state_kind: dict[str, str] = {
        "active_view_present": "bounded_replay",
        "greenfield": "create_from_scratch",
        "logical_view_missing": "full_rebuild_required",
    }
    return RootBackfillReport(
        root_key=inspection.root_key,
        state_kind=inspection.state_kind,
        replay_strategy=replay_strategy_by_state_kind[inspection.state_kind],
        active_deployment_id=inspection.active_deployment_id,
    )
