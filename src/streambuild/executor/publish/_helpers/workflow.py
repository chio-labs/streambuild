"""Assemble exact publish workflow statements."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterBindingReplacementRequest, AdapterMetadataState
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


def assemble_publish_workflow(
    *,
    client: AdapterConnection,
    metadata_database: str,
    binding_request: AdapterBindingReplacementRequest,
    metadata_state: AdapterMetadataState,
) -> tuple[WarehouseStatement, ...]:
    """Return publish mutations in existing lifecycle order."""

    binding_sql: tuple[str, ...] = client.render_replace_stable_bindings(binding_request)
    migration_sql: tuple[str, ...] = client.render_migrate_metadata_state(metadata_database)
    persistence_sql: tuple[str, ...] = client.render_persist_metadata_state(
        database=metadata_database,
        state=metadata_state,
    )
    binding_statements: tuple[WarehouseStatement, ...] = _build_statements(
        sql_statements=binding_sql,
        sequence_start=1,
        step_prefix="replace_stable_binding",
        phase=WorkflowPhase.STABILIZATION,
    )
    migration_statements: tuple[WarehouseStatement, ...] = _build_statements(
        sql_statements=migration_sql,
        sequence_start=len(binding_statements) + 1,
        step_prefix="migrate_metadata",
        phase=WorkflowPhase.FINALIZATION,
    )
    persistence_statements: tuple[WarehouseStatement, ...] = _build_statements(
        sql_statements=persistence_sql,
        sequence_start=len(binding_statements) + len(migration_statements) + 1,
        step_prefix="persist_publish_event",
        phase=WorkflowPhase.FINALIZATION,
    )
    return (*binding_statements, *migration_statements, *persistence_statements)


def _build_statements(
    *,
    sql_statements: tuple[str, ...],
    sequence_start: int,
    step_prefix: str,
    phase: WorkflowPhase,
) -> tuple[WarehouseStatement, ...]:
    return tuple(
        WarehouseStatement(
            sequence=sequence,
            step_id=f"{step_prefix}_{sequence - sequence_start + 1:04d}",
            phase=phase,
            intent=StatementIntent.MUTATION,
            sql=sql,
        )
        for sequence, sql in enumerate(sql_statements, start=sequence_start)
    )
