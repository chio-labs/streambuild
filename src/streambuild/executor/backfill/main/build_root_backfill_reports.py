"""Build the per-root reports describing planned backfill work."""

from streambuild.clickhouse.inspect.main.inspect_managed_table_state import (
    inspect_managed_table_state,
)
from streambuild.clickhouse.inspect.main.inspect_root_deployment_state import (
    inspect_root_deployment_state,
)
from streambuild.clickhouse.inspect.models import (
    InspectedManagedTableState,
)
from streambuild.compiler.compile.constants import (
    TRANSFORM_TABLE_NAME_PREFIX,
)
from streambuild.compiler.compile.models import DesiredState, DesiredTable, ObjectKey
from streambuild.executor.backfill._helpers.reporting import (
    _build_root_backfill_report,
)
from streambuild.executor.backfill.models import RootBackfillReport
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def build_root_backfill_reports(
    *,
    client: ClickHouseClient,
    desired_state: DesiredState,
    database: str,
) -> tuple[RootBackfillReport, ...]:
    """Build user-facing rebuild strategy reports for managed roots."""

    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=database,
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
