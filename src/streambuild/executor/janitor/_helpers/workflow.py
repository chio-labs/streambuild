"""Assemble exact janitor workflow statements."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterResultError
from streambuild.adapter.models import (
    AdapterBindingReplacementRequest,
    AdapterOwnedResourceEvent,
    AdapterRelationCleanupRequest,
)
from streambuild.executor.workflow.models import WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowPhase


def assemble_janitor_workflow(
    *,
    client: AdapterConnection,
    metadata_database: str,
    binding_request: AdapterBindingReplacementRequest,
    cleanup_request: AdapterRelationCleanupRequest,
    binding_events: tuple[AdapterOwnedResourceEvent, ...],
    cleanup_events: tuple[AdapterOwnedResourceEvent, ...],
) -> tuple[WarehouseStatement, ...]:
    """Return every removal immediately followed by its ownership tombstone."""

    migration_sql: tuple[str, ...] = client.render_migrate_metadata_state(metadata_database)
    statements: list[WarehouseStatement] = [
        WarehouseStatement(
            sequence=index,
            step_id=f"migrate_metadata_{index:04d}",
            phase=WorkflowPhase.PREPARATION,
            intent=StatementIntent.MUTATION,
            sql=sql,
        )
        for index, sql in enumerate(migration_sql, start=1)
    ]
    statements.extend(
        _removal_statements(
            sequence_start=len(statements) + 1,
            sql_statements=client.render_replace_stable_bindings(binding_request),
            events=binding_events,
            step_prefix="remove_obsolete_binding",
            client=client,
            metadata_database=metadata_database,
        )
    )
    statements.extend(
        _removal_statements(
            sequence_start=len(statements) + 1,
            sql_statements=client.render_cleanup_relations(cleanup_request),
            events=cleanup_events,
            step_prefix="cleanup_relation",
            client=client,
            metadata_database=metadata_database,
        )
    )
    return tuple(statements)


def _removal_statements(
    *,
    sequence_start: int,
    sql_statements: tuple[str, ...],
    events: tuple[AdapterOwnedResourceEvent, ...],
    step_prefix: str,
    client: AdapterConnection,
    metadata_database: str,
) -> tuple[WarehouseStatement, ...]:
    if len(sql_statements) != len(events):
        raise AdapterResultError("Janitor removals and ownership tombstones do not align")
    statements: list[WarehouseStatement] = []
    for index, (sql, event) in enumerate(zip(sql_statements, events, strict=True), start=1):
        statements.append(
            WarehouseStatement(
                sequence=sequence_start + len(statements),
                step_id=f"{step_prefix}_{index:04d}",
                phase=WorkflowPhase.TEARDOWN,
                intent=StatementIntent.MUTATION,
                sql=sql,
            )
        )
        for event_index, event_sql in enumerate(
            client.render_owned_resource_events(
                database=metadata_database,
                events=(event,),
            ),
            start=1,
        ):
            statements.append(
                WarehouseStatement(
                    sequence=sequence_start + len(statements),
                    step_id=f"record_{step_prefix}_{index:04d}_{event_index:04d}",
                    phase=WorkflowPhase.TEARDOWN,
                    intent=StatementIntent.MUTATION,
                    sql=event_sql,
                )
            )
    return tuple(statements)
