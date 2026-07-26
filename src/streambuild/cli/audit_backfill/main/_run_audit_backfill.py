"""CLI command for staged backfill audit."""

import sys
from dataclasses import replace
from pathlib import Path

from clickhouse_connect.driver.exceptions import DatabaseError, OperationalError

from streambuild.cli.audit_backfill._helpers.audit_selection import (
    backfill_audit_resolver,
    selected_backfill_sql_audits,
)
from streambuild.cli.audit_backfill._helpers.candidates import (
    candidate_root_names,
    enrich_candidates,
)
from streambuild.cli.audit_backfill._helpers.rendering import (
    render_audit_backfill_result,
)
from streambuild.cli.shared.main._errors import render_expected_clickhouse_error
from streambuild.cli.shared.main._render_ambiguous_deployment_message import (
    render_ambiguous_deployment_message,
)
from streambuild.cli.shared.main._render_no_deployment_candidates_message import (
    render_no_deployment_candidates_message,
)
from streambuild.clickhouse.inspect.main.inspect_managed_table_state import (
    inspect_managed_table_state,
)
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery.main.discover_pipelines import discover_pipelines
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.executor.audit_backfill.main.build_audit_deployment_candidates import (
    build_audit_deployment_candidates,
)
from streambuild.executor.audit_backfill.main.execute_audit_backfill import execute_audit_backfill
from streambuild.executor.audit_backfill.main.load_audit_deployment import load_audit_deployment
from streambuild.executor.audit_backfill.models import (
    AuditBackfillRequest,
    AuditBackfillResult,
    AuditDeploymentCandidate,
    LoadedAuditDeployment,
)
from streambuild.executor.audit_backfill.types import AuditAssessment
from streambuild.executor.auditing.main.execute_sql_audits import execute_sql_audits
from streambuild.executor.auditing.models import SqlAuditRunResult
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def run_audit_backfill(
    *,
    pipelines_root: Path | None,
    project_dir: Path | None,
    database: str,
    metadata_database: str | None,
    deployment_id: str | None,
    json_output: bool,
    client: ClickHouseClient,
) -> int:
    """Audit a staged backfill deployment and print the result payload."""

    resolved_metadata_database: str = metadata_database or database
    try:
        compiled_pipelines: tuple[CompiledPipeline, ...] = ()
        if pipelines_root is not None:
            loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)
            compiled_pipelines = tuple(
                compile_pipeline(loaded_pipeline) for loaded_pipeline in loaded_pipelines
            )
        if deployment_id is None:
            candidates: tuple[AuditDeploymentCandidate, ...] = build_audit_deployment_candidates(
                client=client,
                metadata_database=resolved_metadata_database,
                default_database=database,
            )
            if not candidates:
                print(
                    render_no_deployment_candidates_message(
                        command_name="audit backfill",
                        database=database,
                    ),
                    file=sys.stderr,
                )
                return 1
            if len(candidates) > 1:
                inspected_state: InspectedManagedTableState = inspect_managed_table_state(
                    client=client,
                    database=database,
                )
                root_names: tuple[str, ...] = candidate_root_names(inspected_state)
                print(
                    render_ambiguous_deployment_message(
                        command_name="audit backfill",
                        database=database,
                        root_names=root_names,
                        candidates=enrich_candidates(
                            client=client,
                            metadata_database=resolved_metadata_database,
                            candidates=candidates,
                        ),
                    ),
                    file=sys.stderr,
                )
                return 1
        result: AuditBackfillResult = execute_audit_backfill(
            request=AuditBackfillRequest(
                deployment_id=deployment_id,
                metadata_database=resolved_metadata_database,
                default_database=database,
            ),
            client=client,
        )
        if project_dir is not None and compiled_pipelines:
            loaded_deployment: LoadedAuditDeployment = load_audit_deployment(
                client=client,
                metadata_database=resolved_metadata_database,
                deployment_id=result.deployment_id,
            )
            quality_check_result: SqlAuditRunResult = execute_sql_audits(
                loaded_audits=selected_backfill_sql_audits(
                    project_dir=project_dir,
                    compiled_pipelines=compiled_pipelines,
                    staged_logical_table_names=frozenset(
                        logical_key.name
                        for logical_key, _physical_name in (
                            loaded_deployment.prepared_object_mappings
                        )
                    ),
                ),
                resolver=backfill_audit_resolver(
                    database=database,
                    compiled_pipelines=compiled_pipelines,
                    loaded_deployment=loaded_deployment,
                ),
                client=client,
            )
            if quality_check_result.error_failure_count:
                result = replace(
                    result,
                    assessment=AuditAssessment.NOT_READY,
                    quality_check_results=quality_check_result.audit_results,
                )
            else:
                result = replace(result, quality_check_results=quality_check_result.audit_results)
    except (DatabaseError, OperationalError) as error:
        rendered_error: str | None = render_expected_clickhouse_error(
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
