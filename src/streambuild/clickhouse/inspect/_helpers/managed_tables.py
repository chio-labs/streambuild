"""Managed-table inspection helpers for ClickHouse live state."""

from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.clickhouse.inspect.models import (
    ActiveBindingSystemRow,
    InspectedActiveTableBinding,
    InspectedManagedTableState,
    InspectedPhysicalTableCandidate,
    PhysicalCandidateSystemRow,
)
from streambuild.compiler.compile.constants import (
    RAW_TABLE_NAME_PREFIX,
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.planner.main.logical_name_from_physical_name import (
    logical_name_from_physical_name,
)


def build_inspected_managed_table_state(
    *,
    client: AdapterConnection,
    database: str,
) -> InspectedManagedTableState:
    """Build inspected managed-table state from ClickHouse system metadata."""

    active_binding_rows: tuple[ActiveBindingSystemRow, ...] = client.query_many(
        statement="SELECT name, as_select FROM system.tables "
        f"WHERE database = '{database}' AND engine = 'View'",
        decode=_decode_active_binding_system_row,
    )
    physical_candidate_rows: tuple[PhysicalCandidateSystemRow, ...] = client.query_many(
        statement=(
            f"SELECT name FROM system.tables WHERE database = '{database}' AND engine != 'View'"
        ),
        decode=_decode_physical_candidate_system_row,
    )

    active_bindings: list[InspectedActiveTableBinding] = []
    row: ActiveBindingSystemRow
    for row in active_binding_rows:
        physical_name: str | None = _extract_physical_table_name(row.as_select)
        if physical_name is None:
            continue
        active_bindings.append(
            InspectedActiveTableBinding(
                database=database,
                logical_name=row.name,
                physical_name=physical_name,
            )
        )

    physical_candidates: tuple[InspectedPhysicalTableCandidate, ...] = tuple(
        InspectedPhysicalTableCandidate(
            database=database,
            logical_name=_logical_name_from_physical_name(row.name),
            physical_name=row.name,
        )
        for row in physical_candidate_rows
        if _is_managed_table_logical_name(_logical_name_from_physical_name(row.name))
    )

    return InspectedManagedTableState(
        active_bindings=tuple(active_bindings),
        physical_candidates=physical_candidates,
    )


def _extract_physical_table_name(as_select: str) -> str | None:
    marker: str = "FROM "
    if marker not in as_select:
        return None
    return as_select.split(marker, 1)[1].strip().split(".", 1)[1]


def _logical_name_from_physical_name(physical_name: str) -> str:
    return logical_name_from_physical_name(physical_name)


def _is_managed_table_logical_name(logical_name: str) -> bool:
    return logical_name.startswith((RAW_TABLE_NAME_PREFIX, TRANSFORM_TABLE_NAME_PREFIX))


def _decode_active_binding_system_row(row: Mapping[str, object]) -> ActiveBindingSystemRow:
    return ActiveBindingSystemRow(
        name=str(row["name"]),
        as_select=str(row["as_select"]),
    )


def _decode_physical_candidate_system_row(
    row: Mapping[str, object],
) -> PhysicalCandidateSystemRow:
    return PhysicalCandidateSystemRow(name=str(row["name"]))
