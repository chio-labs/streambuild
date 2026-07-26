"""Load actual state from live ClickHouse inspection."""

from collections.abc import Mapping

from streambuild.compiler.actual_state.exceptions import ActualStateError
from streambuild.compiler.actual_state.models import (
    TableColumnSystemRow,
    TableNameSystemRow,
    TableStorageSystemRow,
)
from streambuild.compiler.shared.models import (
    Column,
    TableSpec,
    TableStorage,
)
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.constants import (
    BLANK_VALUES,
    EMPTY_TUPLE_EXPRESSION,
)


def _load_existing_table_names(*, client: ClickHouseClient, database: str) -> set[str]:
    rows: tuple[TableNameSystemRow, ...] = client.query_many(
        statement=f"SELECT name FROM system.tables WHERE database = '{database}'",
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
        statement="SELECT table, name, type, default_expression FROM system.columns "
        f"WHERE database = '{database}' AND table IN ({_quoted_sql_string_list(table_names)}) "
        "ORDER BY table, position",
        decode=_decode_table_column_system_row,
    )
    storage_rows: tuple[TableStorageSystemRow, ...] = client.query_many(
        statement="SELECT name, engine, sorting_key, partition_key FROM system.tables "
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
            raise ActualStateError(f"Expected live table metadata for {database}.{table_name}")
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
    if not normalized:
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
            None if row["default_expression"] in BLANK_VALUES else str(row["default_expression"])
        ),
    )


def _decode_table_storage_system_row(row: Mapping[str, object]) -> TableStorageSystemRow:
    return TableStorageSystemRow(
        table_name=str(row["name"]),
        engine=str(row["engine"]),
        sorting_key=str(row["sorting_key"]),
        partition_key=(
            None
            if row["partition_key"] in (*BLANK_VALUES, EMPTY_TUPLE_EXPRESSION)
            else str(row["partition_key"])
        ),
    )


def _quoted_sql_string_list(values: tuple[str, ...]) -> str:
    return ", ".join(_quoted_sql_string(value) for value in values)


def _quoted_sql_string(value: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"
