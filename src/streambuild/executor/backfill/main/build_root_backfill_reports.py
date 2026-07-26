"""Build the per-root reports describing planned backfill work."""

from streambuild.adapter.models import CatalogSnapshot, InspectedManagedTableState
from streambuild.compiler.compile.constants import (
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.compile.models import DesiredState, DesiredTable, ObjectKey
from streambuild.compiler.planner.main.build_inspected_managed_table_state_from_catalog import (
    build_inspected_managed_table_state_from_catalog,
)
from streambuild.compiler.planner.main.inspect_root_deployment_state import (
    inspect_root_deployment_state,
)
from streambuild.executor.backfill._helpers.reporting import (
    _build_root_backfill_report,
)
from streambuild.executor.backfill.models import RootBackfillReport


def build_root_backfill_reports(
    *,
    catalog: CatalogSnapshot,
    desired_state: DesiredState,
) -> tuple[RootBackfillReport, ...]:
    """Build user-facing rebuild strategy reports for managed roots."""

    inspected_state: InspectedManagedTableState = build_inspected_managed_table_state_from_catalog(
        catalog=catalog
    )
    root_keys: tuple[ObjectKey, ...] = tuple(
        object_.key
        for object_ in desired_state.objects
        if isinstance(object_, DesiredTable)
        and object_.name.startswith(TRANSFORM_TABLE_NAME_PREFIX)
    )
    return tuple(
        _build_root_backfill_report(
            inspection=inspect_root_deployment_state(
                inspected_state=inspected_state,
                root_key=root_key,
            )
        )
        for root_key in root_keys
    )
