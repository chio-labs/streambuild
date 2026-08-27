"""Comparable catalog table-spec projection."""

from streambuild.adapter.models import CatalogSnapshot
from streambuild.compiler.compile.models import TableSpec
from streambuild.compiler.planner._helpers.warehouse_catalog import (
    active_table_specs_from_catalog,
)


class CatalogTableSpecs:
    """Build comparable table specs from neutral catalog snapshots."""

    @staticmethod
    def build(
        *, catalog: CatalogSnapshot, database: str, table_names: tuple[str, ...]
    ) -> dict[str, TableSpec]:
        """Build comparable table specs for named catalog relations."""

        return active_table_specs_from_catalog(
            catalog=catalog,
            database=database,
            table_names=table_names,
        )
