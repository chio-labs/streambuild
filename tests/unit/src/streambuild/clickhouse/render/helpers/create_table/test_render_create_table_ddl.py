import pytest

from streambuild.clickhouse.render.helpers.create_table.main import render_create_table_ddl
from tests.unit.src.streambuild.clickhouse.render.helpers.create_table._test_types import (
    RenderCreateTableDdlTestCase,
)
from tests.unit.src.streambuild.clickhouse.render.helpers.create_table.helpers import build_table

TEST_CASES: list[RenderCreateTableDdlTestCase] = [
    RenderCreateTableDdlTestCase(
        description="renders base create table ddl without optional clauses",
        include_partition_by=False,
        include_ttl=False,
        include_settings=False,
        expected_fragments=(
            "CREATE TABLE analytics.tbl__orders_enriched",
            "order_id String",
            "_replay_landed_at DateTime64(3) DEFAULT now64(3)",
            "ENGINE = ReplacingMergeTree(_replay_landed_at)",
            "ORDER BY (order_id, _replay_landed_at)",
        ),
        expected_absent_fragments=("PARTITION BY", "TTL ", "SETTINGS "),
    ),
    RenderCreateTableDdlTestCase(
        description="renders optional partition ttl and sorted settings clauses",
        include_partition_by=True,
        include_ttl=True,
        include_settings=True,
        expected_fragments=(
            "PARTITION BY toYYYYMM(_replay_landed_at)",
            "TTL toDateTime(_replay_landed_at) + INTERVAL 30 DAY",
            "SETTINGS allow_nullable_key = 1, index_granularity = 8192",
        ),
        expected_absent_fragments=(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_desired_table_when_rendering_then_it_returns_expected_create_table_ddl(
    test_case: RenderCreateTableDdlTestCase,
) -> None:
    rendered_ddl: str = render_create_table_ddl(
        build_table(
            include_partition_by=test_case.include_partition_by,
            include_ttl=test_case.include_ttl,
            include_settings=test_case.include_settings,
        ),
        database="analytics",
    )

    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered_ddl
    for expected_absent_fragment in test_case.expected_absent_fragments:
        assert expected_absent_fragment not in rendered_ddl
