"""Assemble the exact deployment-promotion workflow statements."""

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
    binding_statements: tuple[WarehouseStatement, ...] = _build_named_statements(
        sql_statements=binding_sql,
        step_ids=_binding_step_ids(binding_request=binding_request),
        sequence_start=1,
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


def _binding_step_ids(*, binding_request: AdapterBindingReplacementRequest) -> tuple[str, ...]:
    """Name each switchover after the relation it rebinds, as other phases do."""

    return tuple(
        f"replace_stable_binding_{binding.logical_name}" for binding in binding_request.bindings
    ) + tuple(
        f"remove_stable_binding_{removal.logical_name}" for removal in binding_request.removals
    )


def _build_named_statements(
    *,
    sql_statements: tuple[str, ...],
    step_ids: tuple[str, ...],
    sequence_start: int,
    phase: WorkflowPhase,
) -> tuple[WarehouseStatement, ...]:
    return tuple(
        WarehouseStatement(
            sequence=sequence_start + index,
            step_id=step_ids[index],
            phase=phase,
            intent=StatementIntent.MUTATION,
            sql=sql,
        )
        for index, sql in enumerate(sql_statements)
    )
