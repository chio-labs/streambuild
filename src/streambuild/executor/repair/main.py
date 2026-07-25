"""Repair execution entrypoint."""

from streambuild.clickhouse.render.helpers.create_view.main import render_create_view_ddl
from streambuild.compiler.shared.helpers.deployment_names import build_deployment_physical_name
from streambuild.executor.repair.models import RepairActiveViewRequest, RepairActiveViewResult
from streambuild.integrations.clickhouse.client import ClickHouseClient


def execute_repair_active_view(
    request: RepairActiveViewRequest,
    client: ClickHouseClient,
) -> RepairActiveViewResult:
    """Explicitly rebind a stable active view to a chosen deployment table."""

    target_table_name: str = build_deployment_physical_name(
        request.table_name, request.deployment_id
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
