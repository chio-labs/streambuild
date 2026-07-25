"""Load actual state from live ClickHouse inspection."""

from collections.abc import Mapping

from streambuild.clickhouse.inspect._helpers.deployments import inspect_root_deployment_state
from streambuild.clickhouse.inspect.main import inspect_managed_table_state
from streambuild.clickhouse.inspect.models import (
    InspectedManagedTableState,
    RootDeploymentInspection,
)
from streambuild.compiler.actual_state._helpers.metadata import (
    load_latest_object_state_records_by_keys,
    load_object_state_records_by_deployments,
)
from streambuild.compiler.actual_state.main import build_actual_state
from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualState,
    ActualTable,
    TableColumnSystemRow,
    TableNameSystemRow,
    TableStorageSystemRow,
)
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.metadata_state.models import ObjectStateRecord
from streambuild.compiler.shared.constants import (
    MATERIALIZED_VIEW_NAME_PREFIX,
    RAW_TABLE_NAME_PREFIX,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.shared.models import (
    Column,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    KafkaTableSpec,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.executor.reconcile.constants import RECONCILE_DEPLOYMENT_ID_PREFIX
from streambuild.integrations.clickhouse.client import ClickHouseClient


def load_actual_state(
    *,
    client: ClickHouseClient,
    desired_state: DesiredState,
    database: str,
) -> ActualState:
    """Load the current active actual state from ClickHouse inspection."""

    existing_names: set[str] = _load_existing_table_names(client=client, database=database)
    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=database,
    )
    active_deployment_by_root: dict[ObjectKey, RootDeploymentInspection] = {
        object_.key: inspect_root_deployment_state(
            inspected_state=inspected_state,
            root_key=object_.key,
        )
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
        and object_.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
    }
    active_deployment_ids: tuple[str, ...] = tuple(
        sorted(
            {
                inspection.active_deployment_id
                for inspection in active_deployment_by_root.values()
                if inspection.active_deployment_id is not None
            }
        )
    )
    object_state_records_by_deployment: dict[str, tuple[ObjectStateRecord, ...]] = (
        load_object_state_records_by_deployments(
            client=client,
            metadata_database=database,
            deployment_ids=active_deployment_ids,
        )
    )
    object_state_by_deployment_and_key: dict[tuple[str, ObjectKey], ObjectStateRecord] = {
        (record.deployment_id, record.key): record
        for deployment_id in active_deployment_ids
        for record in object_state_records_by_deployment.get(deployment_id, ())
    }
    latest_object_state_by_key: dict[ObjectKey, ObjectStateRecord] = (
        load_latest_object_state_records_by_keys(
            client=client,
            metadata_database=database,
            keys=tuple(
                object_.key
                for object_ in desired_state.objects
                if isinstance(object_, DesiredMaterializedView)
                and object_.target_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
            ),
        )
    )
    active_physical_names_by_logical_name: dict[str, str] = {
        binding.logical_name: binding.physical_name for binding in inspected_state.active_bindings
    }
    active_table_names: tuple[str, ...] = tuple(
        sorted(
            {
                active_physical_names_by_logical_name[desired_object.name]
                for desired_object in desired_state.objects
                if isinstance(desired_object, DesiredTable)
                and desired_object.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
                and active_deployment_by_root[desired_object.key].state_kind
                == "active_view_present"
            }
        )
    )
    active_table_specs_by_name: dict[str, TableSpec] = _load_active_table_specs(
        client=client,
        database=database,
        table_names=active_table_names,
    )

    actual_objects: list[ActualKafkaTable | ActualTable | ActualMaterializedView] = []
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        if isinstance(desired_object, DesiredKafkaTable):
            if desired_object.name not in existing_names:
                continue
            actual_objects.append(
                ActualKafkaTable(
                    key=desired_object.key,
                    spec=KafkaTableSpec(
                        columns=desired_object.columns,
                        kafka=desired_object.kafka,
                    ),
                )
            )
            continue

        if isinstance(desired_object, DesiredTable):
            if desired_object.name.startswith(RAW_TABLE_NAME_PREFIX):
                if desired_object.name not in existing_names:
                    continue
                actual_objects.append(
                    ActualTable(
                        key=desired_object.key,
                        spec=TableSpec(
                            columns=desired_object.columns,
                            storage=TableStorage(
                                engine=desired_object.engine,
                                order_by=desired_object.order_by,
                                partition_by=desired_object.partition_by,
                                ttl=desired_object.ttl,
                                settings=desired_object.settings,
                            ),
                        ),
                    )
                )
                continue

            root_inspection: RootDeploymentInspection = active_deployment_by_root[
                desired_object.key
            ]
            if root_inspection.state_kind != "active_view_present":
                continue
            active_physical_name: str = active_physical_names_by_logical_name[desired_object.name]
            actual_objects.append(
                ActualTable(
                    key=desired_object.key,
                    spec=active_table_specs_by_name[active_physical_name],
                )
            )
            continue

        if desired_object.name not in existing_names and not desired_object.name.startswith(
            MATERIALIZED_VIEW_NAME_PREFIX
        ):
            continue
        actual_query: str = desired_object.query
        if desired_object.name.startswith(
            MATERIALIZED_VIEW_NAME_PREFIX
        ) and desired_object.target_table_name.startswith(TRANSFORM_TABLE_NAME_PREFIX):
            root_key: ObjectKey = next(
                object_.key
                for object_ in desired_state.objects
                if isinstance(object_, DesiredTable)
                and object_.name == desired_object.target_table_name
            )
            root_inspection = active_deployment_by_root[root_key]
            if root_inspection.state_kind != "active_view_present":
                continue
            if root_inspection.active_deployment_id is not None:
                object_state_record: ObjectStateRecord | None = (
                    object_state_by_deployment_and_key.get(
                        (root_inspection.active_deployment_id, desired_object.key)
                    )
                )
                if (
                    object_state_record is not None
                    and object_state_record.normalized_query is not None
                ):
                    actual_query = object_state_record.normalized_query
            latest_object_state_record: ObjectStateRecord | None = latest_object_state_by_key.get(
                desired_object.key
            )
            if (
                latest_object_state_record is not None
                and latest_object_state_record.deployment_id.startswith(
                    RECONCILE_DEPLOYMENT_ID_PREFIX
                )
                and latest_object_state_record.normalized_query is not None
            ):
                actual_query = latest_object_state_record.normalized_query
        elif desired_object.name.startswith(
            MATERIALIZED_VIEW_NAME_PREFIX
        ) and desired_object.target_table_name.startswith(RAW_TABLE_NAME_PREFIX):
            if desired_object.name not in existing_names:
                continue
            actual_query = desired_object.query
        elif desired_object.name not in existing_names:
            continue
        actual_objects.append(
            ActualMaterializedView(
                key=desired_object.key,
                spec=MaterializedViewSpec(
                    source_table_name=desired_object.source_table_name,
                    target_table_name=desired_object.target_table_name,
                    query=actual_query,
                ),
            )
        )

    return build_actual_state(tuple(actual_objects))


def _load_existing_table_names(*, client: ClickHouseClient, database: str) -> set[str]:
    rows: tuple[TableNameSystemRow, ...] = client.query_many(
        f"SELECT name FROM system.tables WHERE database = '{database}'",
        decode=_decode_table_name_system_row,
    )
    return {row.name for row in rows}


def _decode_table_name_system_row(row: Mapping[str, object]) -> TableNameSystemRow:
    return TableNameSystemRow(name=str(row["name"]))


def _load_active_table_specs(
    *, client: ClickHouseClient, database: str, table_names: tuple[str, ...]
) -> dict[str, TableSpec]:
    if not table_names:
        return {}
    column_rows: tuple[TableColumnSystemRow, ...] = client.query_many(
        "SELECT table, name, type, default_expression FROM system.columns "
        f"WHERE database = '{database}' AND table IN ({_quoted_sql_string_list(table_names)}) "
        "ORDER BY table, position",
        decode=_decode_table_column_system_row,
    )
    storage_rows: tuple[TableStorageSystemRow, ...] = client.query_many(
        "SELECT name, engine, sorting_key, partition_key FROM system.tables "
        f"WHERE database = '{database}' AND name IN ({_quoted_sql_string_list(table_names)})",
        decode=_decode_table_storage_system_row,
    )
    column_rows_by_table_name: dict[str, list[TableColumnSystemRow]] = {
        table_name: [] for table_name in table_names
    }
    column_row: TableColumnSystemRow
    for column_row in column_rows:
        column_rows_by_table_name.setdefault(column_row.table_name, []).append(column_row)
    storage_row_by_table_name: dict[str, TableStorageSystemRow] = {
        storage_row.table_name: storage_row for storage_row in storage_rows
    }
    table_specs_by_name: dict[str, TableSpec] = {}
    table_name: str
    for table_name in table_names:
        storage_row: TableStorageSystemRow | None = storage_row_by_table_name.get(table_name)
        if storage_row is None:
            raise ValueError(f"Expected live table metadata for {database}.{table_name}")
        table_specs_by_name[table_name] = TableSpec(
            columns=tuple(
                Column(
                    name=row.name,
                    type=row.type,
                    default=row.default_expression,
                )
                for row in column_rows_by_table_name.get(table_name, [])
            ),
            storage=TableStorage(
                engine=_normalize_storage_engine(storage_row.engine),
                order_by=_parse_sorting_key(storage_row.sorting_key),
                partition_by=storage_row.partition_key,
                ttl=None,
                settings=None,
            ),
        )
    return table_specs_by_name


def _parse_sorting_key(value: str) -> tuple[str, ...]:
    normalized: str = value.strip()
    if normalized == "":
        return ()
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1]
    return tuple(part.strip() for part in normalized.split(",") if part.strip())


def _normalize_storage_engine(value: str) -> str:
    normalized: str = value.strip()
    if "(" in normalized:
        return normalized
    return f"{normalized}()"


def _decode_table_column_system_row(row: Mapping[str, object]) -> TableColumnSystemRow:
    return TableColumnSystemRow(
        table_name=str(row["table"]),
        name=str(row["name"]),
        type=str(row["type"]),
        default_expression=(
            None if row["default_expression"] in (None, "") else str(row["default_expression"])
        ),
    )


def _decode_table_storage_system_row(row: Mapping[str, object]) -> TableStorageSystemRow:
    return TableStorageSystemRow(
        table_name=str(row["name"]),
        engine=str(row["engine"]),
        sorting_key=str(row["sorting_key"]),
        partition_key=(
            None if row["partition_key"] in (None, "", "tuple()") else str(row["partition_key"])
        ),
    )


def _quoted_sql_string_list(values: tuple[str, ...]) -> str:
    return ", ".join(_quoted_sql_string(value) for value in values)


def _quoted_sql_string(value: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"
