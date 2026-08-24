"""Assemble exact repair workflow statements."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterOwnedResourceEvent,
    AdapterStableBinding,
)
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


def assemble_repair_workflow(
    *,
    binding: AdapterStableBinding,
    ownership_event: AdapterOwnedResourceEvent,
    metadata_database: str,
    client: AdapterConnection,
) -> tuple[WarehouseStatement, ...]:
    """Return metadata preparation, exact replacement, and adjacent ownership evidence."""

    migration_sql: tuple[str, ...] = client.render_migrate_metadata_state(metadata_database)
    rendered_sql: tuple[str, ...] = client.render_replace_stable_bindings(
        AdapterBindingReplacementRequest(bindings=(binding,))
    )
    ownership_sql: tuple[str, ...] = client.render_owned_resource_events(
        database=metadata_database,
        events=(ownership_event,),
    )
    preparation: tuple[WarehouseStatement, ...] = tuple(
        WarehouseStatement(
            sequence=index,
            step_id=f"migrate_metadata_{index:04d}",
            phase=WorkflowPhase.PREPARATION,
            intent=StatementIntent.MUTATION,
            sql=sql,
        )
        for index, sql in enumerate(migration_sql, start=1)
    )
    replace_sequence: int = len(preparation) + 1
    replacement: WarehouseStatement = WarehouseStatement(
        sequence=replace_sequence,
        step_id="replace_active_view",
        phase=WorkflowPhase.FINALIZATION,
        intent=StatementIntent.MUTATION,
        sql=rendered_sql[0],
    )
    evidence: tuple[WarehouseStatement, ...] = tuple(
        WarehouseStatement(
            sequence=replace_sequence + index,
            step_id=f"record_active_view_ownership_{index:04d}",
            phase=WorkflowPhase.FINALIZATION,
            intent=StatementIntent.MUTATION,
            sql=sql,
        )
        for index, sql in enumerate(ownership_sql, start=1)
    )
    return (*preparation, replacement, *evidence)
