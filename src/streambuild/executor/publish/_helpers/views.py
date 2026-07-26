"""Stable logical view creation helpers for publish."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import InspectedManagedTableState
from streambuild.adapters.clickhouse.main.inspect_managed_table_state import (
    inspect_managed_table_state,
)
from streambuild.clickhouse.render.main.render_create_view_ddl import render_create_view_ddl
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.planner.main.build_deployment_physical_name import (
    build_deployment_physical_name,
)
from streambuild.executor.publish.exceptions import PublishExecutionError
from streambuild.executor.publish.models import PublishedView


def publish_stable_views(
    *,
    client: AdapterConnection,
    metadata_database: str,
    default_database: str,
    deployment_id: str,
) -> tuple[PublishedView, ...]:
    """Create or replace stable logical views for a staged deployment."""

    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=default_database,
    )
    published_views: list[PublishedView] = []
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
    root_key: ObjectKey
    for root_key in tuple(
        sorted(
            physical_name_by_key,
            key=lambda value: (
                value.database or "",
                _published_view_kind_order(value.name),
                value.object_type,
                value.name,
            ),
        )
    ):
        database: str = root_key.database or default_database
        target_table_name: str = physical_name_by_key[root_key]
        client.command(
            render_create_view_ddl(
                database=database,
                view_name=root_key.name,
                target_table_name=target_table_name,
            )
        )
        published_views.append(
            PublishedView(
                view_name=root_key.name,
                target_table_name=target_table_name,
            )
        )

    return tuple(published_views)


def _published_view_kind_order(logical_name: str) -> int:
    if logical_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
        return 0
    return 1
