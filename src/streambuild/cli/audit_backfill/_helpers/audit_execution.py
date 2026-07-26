from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.audit_backfill._helpers.audit_selection import (
    backfill_audit_resolver,
    selected_backfill_sql_audits,
)
from streambuild.cli.audit_backfill._helpers.candidates import (
    candidate_root_names,
    enrich_candidates,
)
from streambuild.cli.audit_backfill.main._render_no_deployment_candidates_message import (
    render_no_deployment_candidates_message,
)
from streambuild.cli.audit_backfill.main.render_ambiguous_deployment_message import (
    render_ambiguous_deployment_message,
)
from streambuild.clickhouse.inspect.main.inspect_managed_table_state import (
    inspect_managed_table_state,
)
from streambuild.clickhouse.inspect.models import InspectedManagedTableState
from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery.main.discover_pipelines import discover_pipelines
from streambuild.compiler.discovery.models import LoadedPipeline
from streambuild.executor.audit_backfill.main.build_audit_deployment_candidates import (
    build_audit_deployment_candidates,
)
from streambuild.executor.audit_backfill.main.load_audit_deployment import load_audit_deployment
from streambuild.executor.audit_backfill.models import (
    AuditBackfillResult,
    AuditDeploymentCandidate,
    LoadedAuditDeployment,
)
from streambuild.executor.audit_backfill.types import AuditAssessment
from streambuild.executor.auditing.main.execute_sql_audits import execute_sql_audits
from streambuild.executor.auditing.models import SqlAuditRunResult


def compile_audit_pipelines(pipelines_root: Path | None) -> tuple[CompiledPipeline, ...]:
    if pipelines_root is None:
        return ()
    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)
    return tuple(compile_pipeline(pipeline) for pipeline in loaded_pipelines)


def resolve_deployment_candidate_error(
    *,
    deployment_id: str | None,
    client: AdapterConnection,
    metadata_database: str,
    database: str,
) -> str | None:
    if deployment_id is not None:
        return None
    candidates: tuple[AuditDeploymentCandidate, ...] = build_audit_deployment_candidates(
        client=client,
        metadata_database=metadata_database,
        default_database=database,
    )
    if not candidates:
        return render_no_deployment_candidates_message(
            command_name="audit backfill",
            database=database,
        )
    if len(candidates) == 1:
        return None
    inspected_state: InspectedManagedTableState = inspect_managed_table_state(
        client=client,
        database=database,
    )
    return render_ambiguous_deployment_message(
        command_name="audit backfill",
        database=database,
        root_names=candidate_root_names(inspected_state),
        candidates=enrich_candidates(
            client=client,
            metadata_database=metadata_database,
            candidates=candidates,
        ),
    )


def execute_audit_quality_checks(
    *,
    result: AuditBackfillResult,
    project_dir: Path | None,
    compiled_pipelines: tuple[CompiledPipeline, ...],
    client: AdapterConnection,
    metadata_database: str,
    database: str,
) -> AuditBackfillResult:
    if project_dir is None or not compiled_pipelines:
        return result
    loaded_deployment: LoadedAuditDeployment = load_audit_deployment(
        client=client,
        metadata_database=metadata_database,
        deployment_id=result.deployment_id,
    )
    quality_check_result: SqlAuditRunResult = execute_sql_audits(
        loaded_audits=selected_backfill_sql_audits(
            project_dir=project_dir,
            compiled_pipelines=compiled_pipelines,
            staged_logical_table_names=frozenset(
                logical_key.name
                for logical_key, _physical_name in loaded_deployment.prepared_object_mappings
            ),
        ),
        resolver=backfill_audit_resolver(
            database=database,
            compiled_pipelines=compiled_pipelines,
            loaded_deployment=loaded_deployment,
        ),
        client=client,
    )
    assessment: AuditAssessment | str = (
        AuditAssessment.NOT_READY if quality_check_result.error_failure_count else result.assessment
    )
    return replace(
        result,
        assessment=assessment,
        quality_check_results=quality_check_result.audit_results,
    )
