"""Run deployment lifecycle mutations as recorded, observable invocations."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic_ns

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.dev_server.models import DeploymentOperationRecord
from streambuild.executor.deployment.main.execute_deployment_diff import execute_deployment_diff
from streambuild.executor.deployment.models import (
    DeploymentDiffRelation,
    DeploymentDiffRequest,
    DeploymentDiffResult,
)
from streambuild.executor.janitor.main.execute_janitor import execute_janitor
from streambuild.executor.janitor.models import (
    JanitorApplyResult,
    JanitorPreviewResult,
    JanitorRequest,
)
from streambuild.executor.observability.classes.run_event_sink import RunEventSink
from streambuild.executor.observability.main.build_invocation_record import (
    build_invocation_record,
)
from streambuild.executor.observability.main.persist_terminal_observations import (
    persist_terminal_observations,
)
from streambuild.executor.observability.models import TerminalInvocation
from streambuild.executor.promotion.main.execute_deployment_promotion import execute_publish
from streambuild.executor.promotion.models import PublishRequest, PublishResult

_PROMOTE_COMMAND: str = "deployment promote"
_CLEANUP_COMMAND: str = "janitor"


def run_deployment_promotion(
    *,
    connection: AdapterConnection,
    database: str,
    metadata_database: str,
    deployment_id: str,
    project_dir: Path,
) -> dict[str, object]:
    """Promote one deployment, recording it as a run the UI can follow."""

    started: tuple[str, str, int] = _start()
    sink: RunEventSink = RunEventSink(
        connection=connection, database=metadata_database, invocation_id=started[0]
    )
    sink.run_started(
        command=_PROMOTE_COMMAND,
        display_command=f"stb {_PROMOTE_COMMAND} {deployment_id}",
        mode="virtual_environment",
        total_statements=0,
        selected_node_count=0,
    )
    try:
        result: PublishResult = execute_publish(
            request=PublishRequest(
                deployment_id=deployment_id,
                metadata_database=metadata_database,
                default_database=database,
            ),
            client=connection,
            emitter=sink,
        )
    except Exception as error:
        sink.run_completed(outcome="failed", exit_code=1, error_message=str(error))
        _persist(
            connection=connection,
            metadata_database=metadata_database,
            started=started,
            project_dir=project_dir,
            database=database,
            record=DeploymentOperationRecord(
                command=_PROMOTE_COMMAND,
                deployment_id=deployment_id,
                outcome="failed",
                exit_code=1,
                materialized_outcome=None,
                error_message=str(error),
                summary={},
            ),
        )
        raise
    sink.run_completed(outcome="succeeded", exit_code=0, error_message=None)
    _persist(
        connection=connection,
        metadata_database=metadata_database,
        started=started,
        project_dir=project_dir,
        database=database,
        record=DeploymentOperationRecord(
            command=_PROMOTE_COMMAND,
            deployment_id=result.deployment_id,
            outcome="succeeded",
            exit_code=0,
            materialized_outcome="applied",
            error_message=None,
            summary={"publishedViews": len(result.published_views)},
        ),
    )
    return {
        "invocationId": started[0],
        "deploymentId": result.deployment_id,
        "publishedViews": [
            {"logicalName": view.view_name, "physicalName": view.target_table_name}
            for view in result.published_views
        ],
        "graphAtomicPublish": result.graph_atomic_publish,
    }


def run_deployment_cleanup(
    *,
    connection: AdapterConnection,
    database: str,
    metadata_database: str,
    retention_days: int,
    project_dir: Path,
) -> dict[str, object]:
    """Apply janitor cleanup, recording it as a run the UI can follow."""

    started: tuple[str, str, int] = _start()
    result: JanitorApplyResult | JanitorPreviewResult = execute_janitor(
        request=JanitorRequest(
            database=database,
            metadata_database=metadata_database,
            retention_days=retention_days,
            apply=True,
        ),
        client=connection,
    )
    removed: int = len(result.deleted_object_names) if isinstance(result, JanitorApplyResult) else 0
    removed_deployments: int = (
        len(result.deleted_deployment_ids) if isinstance(result, JanitorApplyResult) else 0
    )
    _persist(
        connection=connection,
        metadata_database=metadata_database,
        started=started,
        project_dir=project_dir,
        database=database,
        record=DeploymentOperationRecord(
            command=_CLEANUP_COMMAND,
            deployment_id=None,
            outcome="succeeded",
            exit_code=0,
            materialized_outcome="applied",
            error_message=None,
            summary={"removedRelations": removed, "removedDeployments": removed_deployments},
        ),
    )
    return {
        "invocationId": started[0],
        "removedRelations": removed,
        "removedDeployments": removed_deployments,
    }


def build_deployment_diff_payload(
    *,
    connection: AdapterConnection,
    database: str,
    metadata_database: str,
    comparison: str,
) -> dict[str, object]:
    """Compare two deployment endpoints for the deployment detail view."""

    return diff_payload(
        result=execute_deployment_diff(
            request=DeploymentDiffRequest(
                database=database,
                metadata_database=metadata_database,
                comparison=comparison,
            ),
            client=connection,
        )
    )


def diff_payload(*, result: DeploymentDiffResult) -> dict[str, object]:
    """Serialize one deployment comparison for the deployment detail view."""

    return {
        "database": result.database,
        "fromEndpoint": result.from_endpoint,
        "toEndpoint": result.to_endpoint,
        "relations": [_relation_payload(relation) for relation in result.relations],
    }


def _relation_payload(relation: DeploymentDiffRelation) -> dict[str, object]:
    return {
        "logicalName": relation.logical_name,
        "status": str(relation.status),
        "fromPhysicalName": relation.from_physical_name,
        "toPhysicalName": relation.to_physical_name,
        "fromRowCount": relation.from_row_count,
        "toRowCount": relation.to_row_count,
        "addedColumns": _column_names(left=relation.to_columns, right=relation.from_columns),
        "removedColumns": _column_names(left=relation.from_columns, right=relation.to_columns),
    }


def _column_names(
    *,
    left: tuple[object, ...],
    right: tuple[object, ...],
) -> list[str]:
    right_names: set[str] = {str(getattr(column, "name", "")) for column in right}
    return [
        str(getattr(column, "name", ""))
        for column in left
        if str(getattr(column, "name", "")) not in right_names
    ]


def _start() -> tuple[str, str, int]:
    return (
        str(uuid.uuid4()),
        datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        monotonic_ns(),
    )


def _persist(
    *,
    connection: AdapterConnection,
    metadata_database: str,
    started: tuple[str, str, int],
    project_dir: Path,
    database: str,
    record: DeploymentOperationRecord,
) -> None:
    persist_terminal_observations(
        client=connection,
        database=metadata_database,
        invocation=build_invocation_record(
            started=started,
            terminal=TerminalInvocation(
                project_dir=project_dir,
                target_identity=database,
                command=record.command,
                mode="virtual_environment",
                outcome=record.outcome,
                exit_code=record.exit_code,
                materialized_outcome=record.materialized_outcome,
                deployment_id=record.deployment_id,
                workflow_id=None,
                selected_node_count=0,
                error_message=record.error_message,
                summary=record.summary,
            ),
        ),
        node_results=(),
    )
