from collections.abc import Callable
from pathlib import Path

from streambuild.compiler.audit_discovery.main._discover_sql_audits import discover_sql_audits
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile._helpers.audit_validation import validated_sql_audits
from streambuild.compiler.compile.main._compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery.main._discover_pipelines import discover_pipelines
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from tests.unit.src.streambuild.compiler.audit_discovery.helpers import (
    write_schema_yaml_file,
    write_sql_audit_file,
)
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
    write_project_configuration_and_source,
)

AUDIT_FILE_PATH: str = "audits/order_events/audit.sql"
GENERIC_DEFINITION_FILE_PATH: str = "audits/generic/not_null.sql"
SCHEMA_FILE_PATH: str = "pipelines/order_events/schema.yml"

_WRITER_BY_SUFFIX: dict[str, Callable[[Path, str], None]] = {
    ".sql": write_sql_audit_file,
    ".yml": write_schema_yaml_file,
}


def validate_project_sql_audits(
    *,
    tmp_path: Path,
    project_files: tuple[tuple[str, str], ...],
) -> tuple[LoadedSqlAudit, ...]:
    write_project_configuration_and_source(project_dir=tmp_path)
    write_pipeline_file(
        tmp_path / "pipelines" / "order_events" / "pipeline.yml",
        "source: orders",
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
    relative_path: str
    file_contents: str
    for relative_path, file_contents in project_files:
        file_path: Path = tmp_path / relative_path
        _WRITER_BY_SUFFIX[file_path.suffix](file_path, file_contents)
    sql_analyzer: SqlModelAnalyzer = SqlModelAnalyzer(dialect="clickhouse")
    compiled_pipelines: tuple[CompiledPipeline, ...] = tuple(
        compile_pipeline(loaded_pipeline=loaded_pipeline, sql_analyzer=sql_analyzer)
        for loaded_pipeline in discover_pipelines(tmp_path / "pipelines")
    )
    loaded_audits: tuple[LoadedSqlAudit, ...] = tuple(discover_sql_audits(root=tmp_path / "audits"))
    return validated_sql_audits(
        loaded_audits=loaded_audits,
        compiled_pipelines=compiled_pipelines,
    )
