from pathlib import Path

from streambuild.compiler.auditing.main import validate_sql_audits
from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery._helpers.auditing.main import discover_sql_audits
from streambuild.compiler.discovery.main import discover_pipelines
from streambuild.compiler.shared.models import LoadedSqlAudit
from tests.unit.src.streambuild.compiler.discovery._helpers.auditing.helpers import (
    write_schema_yaml_file,
    write_sql_audit_file,
)
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import write_pipeline_file


def validate_project_sql_audits(
    *,
    tmp_path: Path,
    audit_file_contents: str | None = None,
    generic_definition_file_contents: str | None = None,
    schema_file_contents: str | None = None,
) -> tuple[LoadedSqlAudit, ...]:
    write_pipeline_file(
        tmp_path / "pipelines" / "order_events" / "pipeline.yml",
        """
        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders
        """,
    )
    write_pipeline_file(
        tmp_path / "pipelines" / "order_events" / "orders_clean.sql",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT CAST(order_id AS String) AS order_id
        FROM __ref("orders")
        """,
    )
    write_pipeline_file(
        tmp_path / "pipelines" / "order_events" / "order_items.sql",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(1 AS Nullable(Float64)) AS line_total
        FROM __ref("orders_clean")
        """,
    )
    if audit_file_contents:
        write_sql_audit_file(
            tmp_path / "audits" / "order_events" / "audit.sql", audit_file_contents
        )
    if generic_definition_file_contents is not None:
        write_sql_audit_file(
            tmp_path / "audits" / "generic" / "not_null.sql",
            generic_definition_file_contents,
        )
    if schema_file_contents is not None:
        write_schema_yaml_file(
            tmp_path / "pipelines" / "order_events" / "schema.yml",
            schema_file_contents,
        )
    compiled_pipelines: tuple[CompiledPipeline, ...] = tuple(
        compile_pipeline(loaded_pipeline)
        for loaded_pipeline in discover_pipelines(tmp_path / "pipelines")
    )
    loaded_audits: tuple[LoadedSqlAudit, ...] = tuple(discover_sql_audits(tmp_path / "audits"))
    return validate_sql_audits(
        loaded_audits=loaded_audits,
        compiled_pipelines=compiled_pipelines,
    )
