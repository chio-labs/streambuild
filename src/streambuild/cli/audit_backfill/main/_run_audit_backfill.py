"""CLI command for staged backfill audit."""

import sys
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterWarehouseError
from streambuild.cli.audit_backfill._helpers.audit_execution import (
    compile_audit_pipelines,
    execute_audit_quality_checks,
    resolve_deployment_candidate_error,
)
from streambuild.cli.audit_backfill.main.render_audit_backfill_result import (
    render_audit_backfill_result,
)
from streambuild.cli.entry.main._errors import render_expected_warehouse_error
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.executor.audit_backfill.main.execute_audit_backfill import execute_audit_backfill
from streambuild.executor.audit_backfill.models import (
    AuditBackfillRequest,
    AuditBackfillResult,
)


def run_audit_backfill(
    *,
    pipelines_root: Path | None,
    project_dir: Path | None,
    database: str,
    metadata_database: str | None,
    deployment_id: str | None,
    json_output: bool,
    client: AdapterConnection,
) -> int:
    """Audit a staged backfill deployment and print the result payload."""

    resolved_metadata_database: str = metadata_database or database
    try:
        compiled_pipelines: tuple[CompiledPipeline, ...] = compile_audit_pipelines(pipelines_root)
        candidate_error: str | None = resolve_deployment_candidate_error(
            deployment_id=deployment_id,
            client=client,
            metadata_database=resolved_metadata_database,
            database=database,
        )
        if candidate_error is not None:
            print(candidate_error, file=sys.stderr)
            return 1
        result: AuditBackfillResult = execute_audit_backfill(
            request=AuditBackfillRequest(
                deployment_id=deployment_id,
                metadata_database=resolved_metadata_database,
                default_database=database,
            ),
            client=client,
        )
        result = execute_audit_quality_checks(
            result=result,
            project_dir=project_dir,
            compiled_pipelines=compiled_pipelines,
            client=client,
            metadata_database=resolved_metadata_database,
            database=database,
        )
    except AdapterWarehouseError as error:
        rendered_error: str | None = render_expected_warehouse_error(
            command_name="audit backfill",
            database=database,
            error=error,
        )
        if rendered_error is not None:
            print(rendered_error, file=sys.stderr)
            return 1
        raise
    print(
        render_audit_backfill_result(
            result=result,
            database=database,
            json_output=json_output,
            project_dir=project_dir,
        )
    )
    return 0
