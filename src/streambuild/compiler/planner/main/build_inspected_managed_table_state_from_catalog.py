"""Build managed-table inspection from an immutable catalog snapshot."""

from streambuild.adapter.models import CatalogSnapshot, InspectedManagedTableState
from streambuild.compiler.planner._helpers.warehouse_inspection import (
    build_inspected_managed_table_state_from_catalog as _build_from_catalog,
)


def build_inspected_managed_table_state_from_catalog(
    *, catalog: CatalogSnapshot
) -> InspectedManagedTableState:
    """Build managed-table inspection without additional warehouse reads."""

    return _build_from_catalog(catalog=catalog)
