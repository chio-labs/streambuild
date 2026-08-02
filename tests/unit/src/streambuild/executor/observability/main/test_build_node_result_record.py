import json

import pytest

from streambuild.adapter.models import AdapterInvocationRecord, AdapterNodeResultRecord
from streambuild.executor.observability.main.build_node_result_record import (
    build_node_result_record,
)
from tests.unit.src.streambuild.executor.observability.main._test_types import (
    AuditSeverityFingerprintTestCase,
    BoundedNodeResultTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BoundedNodeResultTestCase(
            description="replaces oversized payload and truncates concise error",
            payload_size=20_000,
            error_size=3_000,
            expected_payload_json=(
                '{"missing_count":7,"original_bytes":20050,"payload_truncated":true,'
                '"unexpected_count":9}'
            ),
            expected_error_length=2_000,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_oversized_node_diagnostics_when_building_result_then_payload_is_bounded(
    test_case: BoundedNodeResultTestCase,
) -> None:
    invocation: AdapterInvocationRecord = AdapterInvocationRecord(
        invocation_id="inv-1",
        project_identity="project",
        target_identity="analytics",
        command="test",
        mode=None,
        outcome="failed",
        exit_code=1,
        materialized_outcome=None,
        deployment_id=None,
        workflow_id=None,
        selected_node_count=1,
        started_at="2026-08-02 12:00:00.000",
        completed_at="2026-08-02 12:00:01.000",
        duration_ms=1_000,
        error_message=None,
        summary_json="{}",
        tool_version="1.2.3",
    )

    result: AdapterNodeResultRecord = build_node_result_record(
        invocation=invocation,
        node_kind="test",
        node_identity="tests/orders.sql:1",
        definition="SELECT 1",
        status="failed",
        severity=None,
        failure_count=1,
        payload={
            "rows": "x" * test_case.payload_size,
            "missing_count": 7,
            "unexpected_count": 9,
        },
        error_message="x" * test_case.error_size,
    )

    assert result.payload_json == test_case.expected_payload_json
    assert len(str(result.error_message)) == test_case.expected_error_length
    assert json.loads(result.payload_json)["payload_truncated"] is True
    assert json.loads(result.payload_json)["missing_count"] == 7
    assert json.loads(result.payload_json)["unexpected_count"] == 9


@pytest.mark.parametrize(
    "test_case",
    [
        AuditSeverityFingerprintTestCase(
            description="changes audit fingerprint when declared severity changes",
            first_severity="warning",
            second_severity="error",
            expected_fingerprints_differ=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_same_audit_sql_when_severity_changes_then_definition_is_stale(
    test_case: AuditSeverityFingerprintTestCase,
) -> None:
    invocation: AdapterInvocationRecord = AdapterInvocationRecord(
        invocation_id="inv-1",
        project_identity="project",
        target_identity="analytics",
        command="audit",
        mode=None,
        outcome="succeeded",
        exit_code=0,
        materialized_outcome=None,
        deployment_id=None,
        workflow_id=None,
        selected_node_count=1,
        started_at="2026-08-02 12:00:00.000",
        completed_at="2026-08-02 12:00:01.000",
        duration_ms=1_000,
        error_message=None,
        summary_json="{}",
        tool_version="1.2.3",
    )

    first: AdapterNodeResultRecord = build_node_result_record(
        invocation=invocation,
        node_kind="audit",
        node_identity="audits/orders.sql:1",
        definition="SELECT 1",
        status="warning",
        severity=test_case.first_severity,
        failure_count=1,
        payload={},
        error_message=None,
    )
    second: AdapterNodeResultRecord = build_node_result_record(
        invocation=invocation,
        node_kind="audit",
        node_identity="audits/orders.sql:1",
        definition="SELECT 1",
        status="failed",
        severity=test_case.second_severity,
        failure_count=1,
        payload={},
        error_message=None,
    )

    assert (
        first.definition_fingerprint != second.definition_fingerprint
    ) is test_case.expected_fingerprints_differ
