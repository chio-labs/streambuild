"""CLI command for live SQL audits."""

from pathlib import Path

from streambuild.cli.commands.main.audit._helpers.rendering import render_sql_audit_run_result
from streambuild.cli.commands.main.audit._helpers.selection import select_loaded_sql_audits
from streambuild.compiler.auditing.main import validate_sql_audits
from streambuild.compiler.compile._helpers.naming import transform_table_name
from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery._helpers.auditing.main import discover_sql_audits
from streambuild.compiler.discovery.main import discover_pipelines
from streambuild.compiler.shared.models import LoadedPipeline, LoadedSqlAudit
from streambuild.executor.auditing.main import execute_sql_audits
from streambuild.executor.auditing.models import SqlAuditRunResult
from streambuild.integrations.clickhouse.client import ClickHouseClient


def run_audit(
    pipelines_root: Path,
    *,
    project_dir: Path,
    database: str,
    selectors: tuple[str, ...],
    json_output: bool,
    client: ClickHouseClient,
) -> int:
    """Run user-defined SQL audits against published logical views."""

    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)
    compiled_pipelines: tuple[CompiledPipeline, ...] = tuple(
        compile_pipeline(loaded_pipeline) for loaded_pipeline in loaded_pipelines
    )
    loaded_audits: tuple[LoadedSqlAudit, ...] = validate_sql_audits(
        loaded_audits=tuple(discover_sql_audits(project_dir / "audits")),
        compiled_pipelines=compiled_pipelines,
    )
    selected_audits: tuple[LoadedSqlAudit, ...] = select_loaded_sql_audits(
        loaded_audits=loaded_audits,
        compiled_pipelines=compiled_pipelines,
        selectors=selectors,
    )
    result: SqlAuditRunResult = execute_sql_audits(
        loaded_audits=selected_audits,
        resolver={
            compiled_transform.transform.name: (
                f"{database}.{transform_table_name(compiled_transform.transform.name)}"
            )
            for compiled_pipeline in compiled_pipelines
            for compiled_transform in compiled_pipeline.transforms
        },
        client=client,
    )
    print(
        render_sql_audit_run_result(
            result,
            database=database,
            project_dir=project_dir,
            json_output=json_output,
        )
    )
    return 1 if result.error_failure_count else 0
