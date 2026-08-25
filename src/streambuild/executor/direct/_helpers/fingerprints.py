"""Build and persist non-authoritative logical direct SQL baselines."""

from __future__ import annotations

import json
from hashlib import sha256

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterDirectFingerprintRecord
from streambuild.compiler.compile.models import CompiledModel
from streambuild.compiler.planner.classes.direct_model_fingerprint import DirectModelFingerprint
from streambuild.executor.direct._helpers.workflow import (
    assemble_direct_fingerprint_statements,
)
from streambuild.executor.direct.models import DirectBuildRequest
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main._execute_observation_workflow import (
    execute_observation_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement


def persist_direct_fingerprints(
    *,
    request: DirectBuildRequest,
    connection: AdapterConnection,
    applied_model_names: frozenset[str] | None = None,
) -> str | None:
    """Best-effort write applied logical SQL without changing command outcome."""

    try:
        records: tuple[AdapterDirectFingerprintRecord, ...] = _fingerprint_records(
            request=request,
            applied_model_names=applied_model_names,
        )
        rendered: tuple[str, ...] = connection.render_direct_fingerprint_observations(
            database=request.metadata_database,
            fingerprints=records,
        )
        statements: tuple[WarehouseStatement, ...] = assemble_direct_fingerprint_statements(
            rendered=rendered
        )
        _ = execute_observation_workflow(statements=statements, connection=connection)
    except (AdapterError, WorkflowExecutionError) as error:
        cause: BaseException = error.cause if isinstance(error, WorkflowExecutionError) else error
        return f"Direct SQL baseline was not recorded: {cause}"
    return None


def _fingerprint_records(
    *, request: DirectBuildRequest, applied_model_names: frozenset[str] | None
) -> tuple[AdapterDirectFingerprintRecord, ...]:
    model_by_name: dict[str, CompiledModel] = {
        model.key.name: model for model in request.realized_project.project.models
    }
    records: list[AdapterDirectFingerprintRecord] = []
    for entry in request.plan.entries:
        if applied_model_names is not None and entry.model_key.name not in applied_model_names:
            continue
        model: CompiledModel = model_by_name[entry.model_key.name]
        definition_sql: str = model.query
        definition_hash: str = DirectModelFingerprint.query_hash(definition_sql)
        logical_identity: str = f"{request.database}.{model.key.name}"
        identity_metadata: str = json.dumps(
            DirectModelFingerprint.identity(
                model=model,
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint_identity: str = f"{logical_identity}:{definition_hash}:{request.workflow_id}"
        records.append(
            AdapterDirectFingerprintRecord(
                fingerprint_id=sha256(fingerprint_identity.encode()).hexdigest(),
                logical_model_identity=logical_identity,
                definition_sql=definition_sql,
                definition_hash=definition_hash,
                identity_metadata=identity_metadata,
                workflow_id=request.workflow_id,
                tool_version=request.tool_version,
            )
        )
    return tuple(records)
