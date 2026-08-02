"""Assemble exact reconcile workflow statements."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterMetadataState
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


def assemble_reconcile_workflow(
    *, client: AdapterConnection, database: str, metadata_state: AdapterMetadataState
) -> tuple[WarehouseStatement, ...]:
    """Return metadata migration and persistence statements in order."""

    migration_sql: tuple[str, ...] = client.render_migrate_metadata_state(database)
    persistence_sql: tuple[str, ...] = client.render_persist_metadata_state(
        database=database,
        state=metadata_state,
    )
    migration_statements: tuple[WarehouseStatement, ...] = _build_statements(
        sql_statements=migration_sql,
        sequence_start=1,
        step_prefix="migrate_metadata",
    )
    persistence_statements: tuple[WarehouseStatement, ...] = _build_statements(
        sql_statements=persistence_sql,
        sequence_start=len(migration_statements) + 1,
        step_prefix="persist_reconcile_state",
    )
    return (*migration_statements, *persistence_statements)


def _build_statements(
    *, sql_statements: tuple[str, ...], sequence_start: int, step_prefix: str
) -> tuple[WarehouseStatement, ...]:
    return tuple(
        WarehouseStatement(
            sequence=sequence,
            step_id=f"{step_prefix}_{sequence - sequence_start + 1:04d}",
            phase=WorkflowPhase.FINALIZATION,
            intent=StatementIntent.MUTATION,
            sql=sql,
        )
        for sequence, sql in enumerate(sql_statements, start=sequence_start)
    )
