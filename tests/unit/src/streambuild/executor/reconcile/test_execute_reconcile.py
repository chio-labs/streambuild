from typing import cast

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.models import ActualState, ObjectStateRecord
from streambuild.executor.reconcile.main.execute_reconcile import execute_reconcile
from streambuild.executor.reconcile.models import ReconcilePreview, ReconcileResult
from tests.unit.src.streambuild.executor.reconcile._test_types import (
    ApplyReconcileWorkflowTestCase,
    ExecuteReconcileTestCase,
)
from tests.unit.src.streambuild.executor.reconcile.helpers import (
    ReconcileWorkflowAdapterConnection,
    build_matching_reconcile_states,
    build_structurally_mismatched_reconcile_states,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteReconcileTestCase(
            description="builds records for a structurally matching target and materialized view",
            build_states=build_matching_reconcile_states,
            expected_eligible_names=("tbl__orders", "mv__orders"),
            expected_rejected_reason_groups=(),
            expected_reconcile_id_prefix="reconcile_",
        ),
        ExecuteReconcileTestCase(
            description="rejects an engine mismatch and missing materialized view",
            build_states=build_structurally_mismatched_reconcile_states,
            expected_eligible_names=(),
            expected_rejected_reason_groups=(
                (
                    "engine does not match",
                    "live transform materialized view not found",
                ),
            ),
            expected_reconcile_id_prefix="reconcile_",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_desired_and_actual_states_when_reconciling_then_classifies_targets(
    test_case: ExecuteReconcileTestCase,
) -> None:
    desired_state: DesiredState
    actual_state: ActualState
    desired_state, actual_state = test_case.build_states()

    result: ReconcilePreview = cast(
        ReconcilePreview,
        execute_reconcile(
            client=cast(AdapterConnection, object()),
            metadata_database="metadata",
            desired_state=desired_state,
            actual_state=actual_state,
            selected_model_keys=frozenset(),
        ),
    )

    assert (
        tuple(record.key.name for record in result.eligible_records)
        == test_case.expected_eligible_names
    )
    assert (
        tuple(rejected.reasons for rejected in result.rejected_targets)
        == test_case.expected_rejected_reason_groups
    )
    assert result.reconcile_id.startswith(test_case.expected_reconcile_id_prefix)


@pytest.mark.parametrize(
    "test_case",
    [
        ApplyReconcileWorkflowTestCase(
            description="executes metadata migration and exact reconcile persistence SQL",
            expected_migration_statement="CREATE DATABASE IF NOT EXISTS metadata;",
            expected_object_names=("tbl__orders", "mv__orders"),
            expected_reconcile_id_prefix="reconcile_",
            expected_table_fingerprint=(
                '{"columns": [{"default": null, "name": "order_id", "type": "String"}], '
                '"storage": {"engine": "MergeTree()", "order_by": ["order_id"], '
                '"partition_by": null, "settings": null, "ttl": null}}'
            ),
            expected_view_fingerprint=(
                '{"database_template": null, "query": "SELECT order_id FROM raw__orders", '
                '"source_table_name": "raw__orders", "target_table_name": "tbl__orders"}'
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_matching_state_when_applying_reconcile_then_exact_workflow_sql_reaches_gateway(
    test_case: ApplyReconcileWorkflowTestCase,
) -> None:
    desired_state: DesiredState
    actual_state: ActualState
    desired_state, actual_state = build_matching_reconcile_states()
    connection: ReconcileWorkflowAdapterConnection = ReconcileWorkflowAdapterConnection()

    result: ReconcileResult = cast(
        ReconcileResult,
        execute_reconcile(
            client=connection,
            metadata_database="metadata",
            desired_state=desired_state,
            actual_state=actual_state,
            selected_model_keys=frozenset(),
            apply=True,
        ),
    )
    table_record: ObjectStateRecord = result.reconciled_records[0]
    view_record: ObjectStateRecord = result.reconciled_records[1]
    expected_persistence_statement: str = (
        "INSERT INTO metadata.streambuild_object_state_snapshots "
        "(deployment_id, database_name, object_type, object_name, normalized_fingerprint, "
        "normalized_query, recorded_at) VALUES\n"
        f"('{result.reconcile_id}', NULL, 'table', 'tbl__orders', "
        f"'{test_case.expected_table_fingerprint}', NULL, '{table_record.recorded_at}'),\n"
        f"('{result.reconcile_id}', NULL, 'materialized_view', 'mv__orders', "
        f"'{test_case.expected_view_fingerprint}', 'SELECT order_id FROM raw__orders', "
        f"'{view_record.recorded_at}');"
    )

    assert connection.statements == [
        test_case.expected_migration_statement,
        expected_persistence_statement,
    ]
    assert tuple(record.key.name for record in result.reconciled_records) == (
        test_case.expected_object_names
    )
    assert tuple(record.deployment_id for record in result.reconciled_records) == (
        result.reconcile_id,
        result.reconcile_id,
    )
    assert result.reconcile_id.startswith(test_case.expected_reconcile_id_prefix)
