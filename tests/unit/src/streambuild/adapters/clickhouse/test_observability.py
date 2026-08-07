import pytest

from streambuild.adapter.models import AdapterCurrentQualityNode, AdapterRunEventRecord
from streambuild.adapters.clickhouse._helpers.metadata import (
    render_clickhouse_latest_node_status_query,
    render_clickhouse_run_event_inserts,
)
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    LatestNodeStatusQueryTestCase,
    RunEventInsertsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LatestNodeStatusQueryTestCase(
            description="joins current manifest nodes to current stale and never-run history",
            expected_current_status_fragment=(
                "multiIf(matching.node_identity != '', matching.latest.1, "
                "latest.node_identity = '', 'never_run', 'stale') AS current_status"
            ),
            expected_node_values_fragment=(
                "('audit', 'audits/orders.sql:1', 'current-fingerprint')"
            ),
            expected_target_fragment=("WHERE result.target_identity = 'analytics'"),
            expected_project_fragment=("invocation.project_identity = '/project/current'"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_current_manifest_nodes_when_rendering_status_query_then_all_ui_states_are_explicit(
    test_case: LatestNodeStatusQueryTestCase,
) -> None:
    query: str = render_clickhouse_latest_node_status_query(
        database="metadata",
        project_identity="/project/current",
        target_identity="analytics",
        nodes=(
            AdapterCurrentQualityNode(
                node_kind="audit",
                node_identity="audits/orders.sql:1",
                definition_fingerprint="current-fingerprint",
            ),
        ),
    )

    assert test_case.expected_current_status_fragment in query
    assert test_case.expected_node_values_fragment in query
    assert test_case.expected_target_fragment in query
    assert test_case.expected_project_fragment in query


@pytest.mark.parametrize(
    "test_case",
    [
        RunEventInsertsTestCase(
            description="renders one bare insert for a mid-run event",
            include_migration=False,
            expected_statement_count=1,
            expected_insert_fragment=(
                "INSERT INTO metadata._streambuild_run_events "
                "(invocation_id, sequence, event_kind, step_id, phase, payload_json)"
            ),
            expected_values_fragment=(
                "('inv-1', 3, 'statement_completed', "
                "'replay_orders', 'replay', '{\"writtenRows\": 42}')"
            ),
        ),
        RunEventInsertsTestCase(
            description="prepends the idempotent migration for the first event",
            include_migration=True,
            expected_statement_count=12,
            expected_insert_fragment="CREATE DATABASE IF NOT EXISTS metadata;",
            expected_values_fragment=("emitted_at DateTime64(3, 'UTC') DEFAULT now64(3, 'UTC')"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_run_event_when_rendering_inserts_then_sql_is_exact(
    test_case: RunEventInsertsTestCase,
) -> None:
    rendered: tuple[str, ...] = render_clickhouse_run_event_inserts(
        database="metadata",
        events=(
            AdapterRunEventRecord(
                invocation_id="inv-1",
                sequence=3,
                event_kind="statement_completed",
                step_id="replay_orders",
                phase="replay",
                payload_json='{"writtenRows": 42}',
            ),
        ),
        include_migration=test_case.include_migration,
    )

    assert len(rendered) == test_case.expected_statement_count
    assert test_case.expected_insert_fragment in rendered[0]
    assert any(test_case.expected_values_fragment in statement for statement in rendered)
