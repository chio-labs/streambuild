"""Stable logical view creation helpers for publish."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterBindingReplacementResult,
    AdapterStableBinding,
    InspectedManagedTableState,
)
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.planner.main.build_deployment_physical_name import (
    build_deployment_physical_name,
)
from streambuild.executor.publish.exceptions import PublishExecutionError


def publish_stable_views(
    *,
    client: AdapterConnection,
    metadata_database: str,
    default_database: str,
    deployment_id: str,
) -> AdapterBindingReplacementResult:
    """Build and apply neutral stable bindings for a staged deployment."""

    inspected_state: InspectedManagedTableState = client.inspect_managed_table_state(
        default_database
    )
    physical_name_by_key: dict[ObjectKey, str] = {
        ObjectKey(
            database=candidate.database,
            object_type=DESIRED_OBJECT_TYPE_TABLE,
            name=candidate.logical_name,
        ): candidate.physical_name
        for candidate in inspected_state.physical_candidates
        if candidate.logical_name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
        if candidate.physical_name
        == build_deployment_physical_name(
            logical_name=candidate.logical_name, deployment_id=deployment_id
        )
    }
    if not physical_name_by_key:
        raise PublishExecutionError(
            f"Deployment '{deployment_id}' has no staged physical tables to publish"
        )
    root_keys: tuple[ObjectKey, ...] = tuple(
        sorted(
            physical_name_by_key,
            key=lambda value: (
                value.database or "",
                _published_view_kind_order(value.name),
                value.object_type,
                value.name,
            ),
        )
    )
    replacement_request: AdapterBindingReplacementRequest = AdapterBindingReplacementRequest(
        bindings=tuple(
            AdapterStableBinding(
                database=root_key.database or default_database,
                logical_name=root_key.name,
                physical_name=physical_name_by_key[root_key],
            )
            for root_key in root_keys
        )
    )
    result: AdapterBindingReplacementResult = client.replace_stable_bindings(replacement_request)
    if result.bindings != replacement_request.bindings:
        raise AdapterResultError("Adapter returned bindings that did not match the publish request")
    return result


def _published_view_kind_order(logical_name: str) -> int:
    if logical_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
        return 0
    return 1
