"""CLI command for janitor preview."""

from streambuild.cli.commands.main.janitor._helpers.rendering import render_janitor_result
from streambuild.executor.janitor.main import execute_janitor
from streambuild.executor.janitor.models import (
    JanitorApplyResult,
    JanitorPreviewResult,
    JanitorRequest,
)
from streambuild.integrations.clickhouse.client import ClickHouseClient


def run_janitor(
    *,
    database: str,
    retention_days: int,
    apply: bool,
    json_output: bool,
    client: ClickHouseClient,
) -> int:
    result: JanitorPreviewResult | JanitorApplyResult = execute_janitor(
        JanitorRequest(
            database=database,
            metadata_database=database,
            retention_days=retention_days,
            apply=apply,
        ),
        client,
    )
    print(render_janitor_result(result, apply=apply, json_output=json_output))
    return 0
