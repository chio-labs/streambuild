"""Doctor execution entrypoint."""

from streambuild.clickhouse.inspect._helpers.deployments import inspect_root_deployment_state
from streambuild.clickhouse.inspect.main import inspect_managed_table_state
from streambuild.clickhouse.inspect.models import (
    InspectedManagedTableState,
    RootDeploymentInspection,
)
from streambuild.compiler.shared._helpers.deployment_names import deployment_id_from_physical_name
from streambuild.compiler.shared.constants import DESIRED_OBJECT_TYPE_TABLE
from streambuild.compiler.shared.models import ObjectKey
from streambuild.executor.doctor.models import ActiveViewStatus, DoctorRequest, DoctorResult
from streambuild.integrations.clickhouse.client import ClickHouseClient


def execute_doctor(*, request: DoctorRequest, client: ClickHouseClient) -> DoctorResult:
    """Inspect active-view health for managed deployment tables."""

    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=request.default_database,
    )
    logical_table_names: tuple[str, ...] = tuple(
        sorted(
            {binding.logical_name for binding in inspected_state.active_bindings}
            | {candidate.logical_name for candidate in inspected_state.physical_candidates}
        )
    )
    active_views: tuple[ActiveViewStatus, ...] = tuple(
        _build_active_view_status(
            inspected_state=inspected_state,
            database=request.default_database,
            table_name=table_name,
        )
        for table_name in logical_table_names
    )
    return DoctorResult(active_views=active_views)


def _build_active_view_status(
    *,
    inspected_state: InspectedManagedTableState,
    database: str,
    table_name: str,
) -> ActiveViewStatus:
    inspection: RootDeploymentInspection = inspect_root_deployment_state(
        inspected_state=inspected_state,
        root_key=ObjectKey(
            database=database,
            object_type=DESIRED_OBJECT_TYPE_TABLE,
            name=table_name,
        ),
    )
    candidate_deployment_ids: tuple[str, ...] = tuple(
        deployment_id_from_physical_name(candidate.physical_name)
        for candidate in inspected_state.physical_candidates
        if candidate.database == database and candidate.logical_name == table_name
    )
    return ActiveViewStatus(
        table_name=table_name,
        state_kind=inspection.state_kind,
        active_deployment_id=inspection.active_deployment_id,
        candidate_deployment_ids=tuple(sorted(candidate_deployment_ids)),
    )
