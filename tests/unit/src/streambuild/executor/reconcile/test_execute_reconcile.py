from typing import cast

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterMetadataState
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.models import ActualState
from streambuild.executor.reconcile.main.execute_reconcile import execute_reconcile
from streambuild.executor.reconcile.models import ReconcilePreview, ReconcileResult
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.executor.reconcile._test_types import (
    ApplyReconcileAdapterStateTestCase,
    ExecuteReconcileTestCase,
)
from tests.unit.src.streambuild.executor.reconcile.helpers import (
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
        ApplyReconcileAdapterStateTestCase(
            description="persists the generated reconcile identity through adapter state",
            expected_persisted_state_count=1,
            expected_object_names=("tbl__orders", "mv__orders"),
            expected_reconcile_id_prefix="reconcile_",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_matching_state_when_applying_reconcile_then_adapter_persists_same_snapshot_id(
    test_case: ApplyReconcileAdapterStateTestCase,
) -> None:
    desired_state: DesiredState
    actual_state: ActualState
    desired_state, actual_state = build_matching_reconcile_states()
    connection: RecordingAdapterConnection = RecordingAdapterConnection()

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
    persisted_state: AdapterMetadataState = connection.persisted_metadata_states[0]

    assert len(connection.persisted_metadata_states) == test_case.expected_persisted_state_count
    assert tuple(record.key.name for record in persisted_state.object_states) == (
        test_case.expected_object_names
    )
    assert tuple(record.deployment_id for record in persisted_state.object_states) == (
        result.reconcile_id,
        result.reconcile_id,
    )
    assert result.reconcile_id.startswith(test_case.expected_reconcile_id_prefix)
