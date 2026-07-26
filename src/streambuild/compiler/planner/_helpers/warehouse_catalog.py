"""Project neutral catalog relations into the preserved comparable table shape."""

from collections.abc import Mapping

from streambuild.adapter.models import CatalogRelation, CatalogSnapshot
from streambuild.compiler.compile.models import Column, TableSpec, TableStorage
from streambuild.compiler.planner.constants import (
    BLANK_VALUES,
    EMPTY_TUPLE_EXPRESSION,
    ENGINE_ARGUMENT_OPEN,
)
from streambuild.compiler.planner.exceptions import ActualStateError
from streambuild.compiler.planner.models import (
    TableColumnSystemRow,
    TableNameSystemRow,
    TableStorageSystemRow,
)


def existing_table_names(catalog: CatalogSnapshot) -> frozenset[str]:
    return catalog.relation_names()


def active_table_specs_from_catalog(
    *, catalog: CatalogSnapshot, database: str, table_names: tuple[str, ...]
) -> dict[str, TableSpec]:
    table_specs_by_name: dict[str, TableSpec] = {}
    table_name: str
    for table_name in table_names:
        relation: CatalogRelation | None = catalog.relation(table_name)
        if relation is None:
            raise ActualStateError(f"Expected live table metadata for {database}.{table_name}")
        table_specs_by_name[table_name] = TableSpec(
            columns=tuple(
                Column(
                    name=column.name,
                    type=column.type,
                    default=column.default_expression,
                )
                for column in relation.columns
            ),
            storage=TableStorage(
                engine=normalize_storage_engine(relation.engine),
                order_by=relation.order_by,
                partition_by=relation.partition_by,
                ttl=None,
                settings=None,
            ),
        )
    return table_specs_by_name


def decode_table_name_system_row(row: Mapping[str, object]) -> TableNameSystemRow:
    return TableNameSystemRow(name=str(row["name"]))


def parse_sorting_key(value: str) -> tuple[str, ...]:
    normalized: str = value.strip()
    if not normalized:
        return ()
    if normalized.startswith("(") and normalized.endswith(")"):
        normalized = normalized[1:-1]
    return tuple(part.strip() for part in normalized.split(",") if part.strip())


def normalize_storage_engine(value: str) -> str:
    normalized: str = value.strip()
    if ENGINE_ARGUMENT_OPEN in normalized:
        return normalized
    return f"{normalized}()"


def decode_table_column_system_row(row: Mapping[str, object]) -> TableColumnSystemRow:
    return TableColumnSystemRow(
        table_name=str(row["table"]),
        name=str(row["name"]),
        type=str(row["type"]),
        default_expression=(
            None if row["default_expression"] in BLANK_VALUES else str(row["default_expression"])
        ),
    )


def decode_table_storage_system_row(row: Mapping[str, object]) -> TableStorageSystemRow:
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
