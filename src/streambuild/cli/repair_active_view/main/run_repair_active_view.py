"""CLI command for explicit active-view repair."""

import json
import sys

from clickhouse_connect.driver.exceptions import DatabaseError, OperationalError

from streambuild.cli.shared.main._errors import render_expected_clickhouse_error
from streambuild.executor.repair.main import execute_repair_active_view
from streambuild.executor.repair.models import RepairActiveViewRequest, RepairActiveViewResult
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def run_repair_active_view(
    *,
    database: str,
    table: str,
    deployment_id: str,
    client: ClickHouseClient,
) -> int:
    """Repair a stable active view by rebinding it to a chosen deployment table."""

    try:
        result: RepairActiveViewResult = execute_repair_active_view(
            request=RepairActiveViewRequest(
                default_database=database,
                table_name=table,
                deployment_id=deployment_id,
            ),
            client=client,
        )
    except (DatabaseError, OperationalError) as error:
        rendered_error: str | None = render_expected_clickhouse_error(
            command_name="repair active-view",
            database=database,
            error=error,
        )
        if rendered_error is not None:
            print(rendered_error, file=sys.stderr)
            return 1
        raise
    payload: dict[str, object] = {
        "table_name": result.table_name,
        "target_table_name": result.target_table_name,
    }
    print(json.dumps(payload, indent=2))
    return 0
