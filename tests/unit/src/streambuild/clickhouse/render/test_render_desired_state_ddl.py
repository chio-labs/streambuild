import pytest

from streambuild.clickhouse.render.models import RenderedClickHouseDdl
from tests.unit.src.streambuild.clickhouse.render._test_helpers import (
    render_example_desired_state,
    rendered_keys,
)
from tests.unit.src.streambuild.clickhouse.render._test_types import RenderDesiredStateDdlTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        RenderDesiredStateDdlTestCase(
            description="renders example desired state into deterministic ordered ddl",
            database="analytics",
            expected_rendered_keys=(
                (None, "kafka_table", "kafka__orders"),
                (None, "materialized_view", "mv__orders"),
                (None, "materialized_view", "mv__orders_enriched"),
                (None, "table", "raw__orders"),
                (None, "table", "tbl__orders_enriched"),
            ),
            expected_statement_fragments=(
                "CREATE TABLE analytics.kafka__orders",
                "ENGINE = Kafka",
                "kafka_broker_list = 'kafka:9092'",
                "kafka_topic_list = 'source.orders.created'",
                "kafka_group_name = 'streambuild_orders_orders_analytics'",
                "CREATE MATERIALIZED VIEW analytics.mv__orders",
                "TO analytics.raw__orders AS",
                "FROM analytics.kafka__orders",
                "CREATE MATERIALIZED VIEW analytics.mv__orders_enriched",
                "TO analytics.tbl__orders_enriched AS",
                "FROM analytics.raw__orders",
                "CREATE TABLE analytics.raw__orders",
                "ORDER BY (_replay_partition, _replay_offset)",
                "CREATE TABLE analytics.tbl__orders_enriched",
                "ENGINE = ReplacingMergeTree(updated_at)",
                "PARTITION BY toYYYYMM(created_at)",
                "TTL toDateTime(created_at) + INTERVAL 30 DAY",
            ),
        )
    ],
    ids=["renders example desired state into deterministic ordered ddl"],
)
def test_given_example_desired_state_when_rendering_then_it_returns_expected_ordered_ddl(
    test_case: RenderDesiredStateDdlTestCase,
) -> None:
    rendered_objects: tuple[RenderedClickHouseDdl, ...] = render_example_desired_state(
        database=test_case.database
    )

    assert rendered_keys(rendered_objects) == test_case.expected_rendered_keys
    rendered_statements: tuple[str, ...] = tuple(
        rendered_object.ddl for rendered_object in rendered_objects
    )
    for expected_statement_fragment in test_case.expected_statement_fragments:
        assert any(
            expected_statement_fragment in rendered_statement
            for rendered_statement in rendered_statements
        )
