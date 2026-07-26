from typing import cast

import pytest

from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.compile.models import DesiredState
from streambuild.executor.reconcile.constants import RECONCILE_DEPLOYMENT_ID_PREFIX
from streambuild.executor.reconcile.main.execute_reconcile import execute_reconcile
from streambuild.executor.reconcile.models import ReconcilePreview
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from tests.unit.src.streambuild.executor.reconcile._test_types import ExecuteReconcileTestCase
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
            expected_reconcile_id_prefix=RECONCILE_DEPLOYMENT_ID_PREFIX,
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
            expected_reconcile_id_prefix=RECONCILE_DEPLOYMENT_ID_PREFIX,
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
            client=cast(ClickHouseClient, object()),
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
