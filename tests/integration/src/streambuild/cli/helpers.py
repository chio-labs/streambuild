from pathlib import Path

from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings

BACKFILL_PIPELINES_ROOT: Path = Path("tests/fixtures/basic_project/pipelines")
SELECTOR_PIPELINES_ROOT: Path = Path("tests/fixtures/selector_project/pipelines")


def build_managed_clickhouse_client(
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    *,
    database: str,
) -> ClickHouseClient:
    return ClickHouseClient.from_config(
        ClickHouseConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
            database=database,
        )
    )


def build_deployment_status_query(database: str) -> str:
    return (
        "SELECT name FROM system.tables "
        f"WHERE database = '{database}' AND name = 'streambuild_deployments'"
    )


def build_runtime_details_table_query(database: str) -> str:
    return (
        "SELECT name FROM system.tables "
        f"WHERE database = '{database}' AND name = 'streambuild_deployment_runtime_details'"
    )


def write_audit_project_files(project_dir: Path) -> None:
    from tests.unit.src.streambuild.compiler.discovery._helpers.auditing.helpers import (
        write_sql_audit_file,
    )
    from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
        write_pipeline_file,
    )

    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "pipeline.yml",
        """
        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders
        """,
    )
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "order_items.sql",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __ref("orders")
        """,
    )
    write_sql_audit_file(
        project_dir / "audits" / "singular" / "order_events" / "negative_line_totals.sql",
        """
        AUDIT (
          severity: "warning",
          description: "Line totals should not be negative",
        );

        SELECT order_id, line_total
        FROM __ref("order_items")
        WHERE line_total < 0
        """,
    )


def write_backfill_audit_project_files(project_dir: Path) -> None:
    from tests.unit.src.streambuild.compiler.discovery._helpers.auditing.helpers import (
        write_sql_audit_file,
    )
    from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
        write_pipeline_file,
    )

    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "pipeline.yml",
        """
        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders.created
        """,
    )
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "orders_enriched.sql",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(kafka_key AS String) AS order_id,
          CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp
        FROM __ref("orders")
        """,
    )
    write_sql_audit_file(
        project_dir / "audits" / "singular" / "order_events" / "known_order_id.sql",
        """
        AUDIT (
          description: "ord_001 should be flagged by the staged quality check",
        );

        SELECT order_id
        FROM __ref("orders_enriched")
        WHERE order_id = 'ord_001'
        """,
    )


def write_generic_audit_project_files(project_dir: Path) -> None:
    from tests.unit.src.streambuild.compiler.discovery._helpers.auditing.helpers import (
        write_schema_yaml_file,
        write_sql_audit_file,
    )
    from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
        write_pipeline_file,
    )

    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "pipeline.yml",
        """
        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders
        """,
    )
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "order_items.sql",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __ref("orders")
        """,
    )
    write_sql_audit_file(
        project_dir / "audits" / "generic" / "not_null.sql",
        """
        AUDIT ();

        SELECT @column
        FROM __ref("@model")
        WHERE @column IS NULL
        """,
    )
    write_schema_yaml_file(
        project_dir / "pipelines" / "order_events" / "schema.yml",
        """
        models:
          - name: order_items
            columns:
              - name: order_id
                audits:
                  - not_null:
                      name: order items order id not null
                      severity: warning
        """,
    )


def write_multi_audit_project_files(project_dir: Path) -> None:
    from tests.unit.src.streambuild.compiler.discovery._helpers.auditing.helpers import (
        write_sql_audit_file,
    )
    from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
        write_pipeline_file,
    )

    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "pipeline.yml",
        """
        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders
        """,
    )
    write_pipeline_file(
        project_dir / "pipelines" / "order_events" / "order_items.sql",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __ref("orders")
        """,
    )
    write_sql_audit_file(
        project_dir / "audits" / "singular" / "order_events" / "quality.sql",
        """
        AUDIT (
          name: "negative line totals",
          severity: "warning",
        );

        SELECT order_id, line_total
        FROM __ref("order_items")
        WHERE line_total < 0;

        AUDIT (
          name: "missing order ids",
          severity: "warning",
        );

        SELECT order_id
        FROM __ref("order_items")
        WHERE order_id = 'ord_missing'
        """,
    )
