"""Preserve or create live managed landing resources before population."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.constants import RAW_TABLE_NAME_PREFIX
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    DesiredView,
)
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource


def ensure_live_landing_objects(
    *,
    client: AdapterConnection,
    desired_state: DesiredState,
    default_database: str,
    existing_relation_names: frozenset[str],
) -> None:
    """Ensure the stable source side exists before creating populated targets."""

    existing_names: set[str] = set(existing_relation_names)
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView | DesiredView
    for desired_object in desired_state.objects:
        database: str = desired_object.key.database or default_database
        if isinstance(desired_object, DesiredKafkaTable):
            client.realize_resource(
                resource=build_adapter_resource(desired_object),
                database=database,
                if_not_exists=True,
            )
            existing_names.add(desired_object.name)
        elif isinstance(desired_object, DesiredTable) and desired_object.name.startswith(
            RAW_TABLE_NAME_PREFIX
        ):
            if desired_object.name not in existing_names:
                client.realize_resource(
                    resource=build_adapter_resource(desired_object), database=database
                )
                existing_names.add(desired_object.name)
        elif (
            isinstance(desired_object, DesiredMaterializedView)
            and desired_object.target_table_name.startswith(RAW_TABLE_NAME_PREFIX)
            and desired_object.name not in existing_names
        ):
            client.realize_resource(
                resource=build_adapter_resource(desired_object), database=database
            )
            existing_names.add(desired_object.name)
