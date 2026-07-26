"""Repair execution entrypoint."""

from streambuild.clickhouse.render.main.render_create_view_ddl import render_create_view_ddl
from streambuild.compiler.shared.main.build_deployment_physical_name import (
    build_deployment_physical_name,
)
from streambuild.executor.repair.models import RepairActiveViewRequest, RepairActiveViewResult
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def execute_repair_active_view(
    *,
    request: RepairActiveViewRequest,
    client: ClickHouseClient,
) -> RepairActiveViewResult:
    """Explicitly rebind a stable active view to a chosen deployment table."""

    target_table_name: str = build_deployment_physical_name(
        logical_name=request.table_name, deployment_id=request.deployment_id
    )
    client.command(
        render_create_view_ddl(
            database=request.default_database,
            view_name=request.table_name,
            target_table_name=target_table_name,
        )
    )
    return RepairActiveViewResult(
        table_name=request.table_name,
        target_table_name=target_table_name,
    )
