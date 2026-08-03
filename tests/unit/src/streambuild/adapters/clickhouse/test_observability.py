import pytest

from streambuild.adapter.models import AdapterCurrentQualityNode
from streambuild.adapters.clickhouse._helpers.metadata import (
    render_clickhouse_latest_node_status_query,
)
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    LatestNodeStatusQueryTestCase,
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
