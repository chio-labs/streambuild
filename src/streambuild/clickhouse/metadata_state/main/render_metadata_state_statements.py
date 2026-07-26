"""Build ClickHouse metadata-state DDL statements."""

from streambuild.clickhouse.metadata_state._helpers.runtime_details import (
    render_create_deployment_runtime_details_table_ddl,
)
from streambuild.clickhouse.metadata_state._helpers.table_ddl import (
    render_create_deployment_watermarks_table_ddl,
    render_create_deployments_table_ddl,
    render_create_object_state_table_ddl,
    render_create_publish_history_table_ddl,
)
from streambuild.clickhouse.metadata_state.models import RenderedClickHouseStatement


def render_metadata_state_statements(database: str) -> tuple[RenderedClickHouseStatement, ...]:
    """Render metadata-state DDL statements for ClickHouse persistence."""

    return (
        RenderedClickHouseStatement(sql=render_create_object_state_table_ddl(database)),
        RenderedClickHouseStatement(sql=render_create_deployments_table_ddl(database)),
        RenderedClickHouseStatement(sql=render_create_deployment_watermarks_table_ddl(database)),
        RenderedClickHouseStatement(
            sql=render_create_deployment_runtime_details_table_ddl(database)
        ),
        RenderedClickHouseStatement(sql=render_create_publish_history_table_ddl(database)),
    )
