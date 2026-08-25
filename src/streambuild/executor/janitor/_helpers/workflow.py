"""Assemble exact janitor workflow statements."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterRelationCleanupRequest,
)
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


def assemble_janitor_workflow(
    *,
    client: AdapterConnection,
    binding_request: AdapterBindingReplacementRequest,
    cleanup_request: AdapterRelationCleanupRequest,
) -> tuple[WarehouseStatement, ...]:
    """Return obsolete binding removals before physical relation cleanup."""

    binding_sql: tuple[str, ...] = client.render_replace_stable_bindings(binding_request)
    cleanup_sql: tuple[str, ...] = client.render_cleanup_relations(cleanup_request)
    binding_statements: tuple[WarehouseStatement, ...] = _build_statements(
        sql_statements=binding_sql,
        sequence_start=1,
        step_prefix="remove_obsolete_binding",
    )
    cleanup_statements: tuple[WarehouseStatement, ...] = _build_statements(
        sql_statements=cleanup_sql,
        sequence_start=len(binding_statements) + 1,
        step_prefix="cleanup_relation",
    )
    return (*binding_statements, *cleanup_statements)


def _build_statements(
    *, sql_statements: tuple[str, ...], sequence_start: int, step_prefix: str
) -> tuple[WarehouseStatement, ...]:
    return tuple(
        WarehouseStatement(
            sequence=sequence,
            step_id=f"{step_prefix}_{sequence - sequence_start + 1:04d}",
            phase=WorkflowPhase.TEARDOWN,
            intent=StatementIntent.MUTATION,
            sql=sql,
        )
        for sequence, sql in enumerate(sql_statements, start=sequence_start)
    )
