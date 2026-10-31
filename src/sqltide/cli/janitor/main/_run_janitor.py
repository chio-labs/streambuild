"""CLI command for janitor preview."""

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.cli.janitor._helpers.rendering import render_janitor_result
from sqltide.executor.janitor.main.execute_janitor import execute_janitor
from sqltide.executor.janitor.models import (
    JanitorApplyResult,
    JanitorPreviewResult,
    JanitorRequest,
)


def run_janitor(
    *,
    database: str,
    retention_days: int,
    minimum_rollback_deployments: int,
    apply: bool,
    json_output: bool,
    client: AdapterConnection,
) -> int:
    result: JanitorPreviewResult | JanitorApplyResult = execute_janitor(
        request=JanitorRequest(
            database=database,
            metadata_database=database,
            retention_days=retention_days,
            apply=apply,
            minimum_rollback_deployments=minimum_rollback_deployments,
        ),
        client=client,
    )
    print(render_janitor_result(result=result, apply=apply, json_output=json_output))
    return 0
