from textwrap import dedent

import pytest

from streambuild.compiler.compile.models import (
    DesiredMaterializedView,
    MaterializedViewSpec,
    ObjectKey,
)
from streambuild.compiler.metadata_state.models import DeploymentWatermarkRecord
from streambuild.executor.backfill._helpers.replay import _render_offset_replay_statement
from streambuild.executor.backfill.models import ActiveOffsetFrontierQueryRow
from tests.unit.src.streambuild.executor.backfill._helpers._test_types import (
    RenderOffsetReplayStatementTestCase,
)
from tests.unit.src.streambuild.executor.backfill._helpers.helpers import (
    normalize_clickhouse_sql,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderOffsetReplayStatementTestCase(
            description="renders aggregate offset replay against filtered anchor rows",
            source_table_name="tbl__order_items",
            target_table_name="tbl__hourly_order_volume",
            shadow_target_name="tbl__hourly_order_volume__dep",
            anchor_table_name="tbl__order_items",
            query=(
                "SELECT CAST(toStartOfHour(_replay_timestamp) AS DateTime64(3)) AS event_hour, "
                "CAST(category AS String) AS category, "
                "CAST(count() AS UInt64) AS order_event_count "
                "FROM tbl__order_items AS item_rows "
                "WHERE status = 'created' "
                "GROUP BY event_hour, category"
            ),
            expected_statement=dedent(
                """
            INSERT INTO orders_demo.tbl__hourly_order_volume__dep
            WITH cutoff_offsets AS (
                SELECT 0 AS _replay_partition, 9709 AS cutoff_offset
            ),
            active_start_offsets AS (
                SELECT 0 AS _replay_partition, 9000 AS start_offset
            )
            SELECT
                CAST(dateTrunc('HOUR', _replay_timestamp) AS DateTime64(3)) AS event_hour,
                CAST(category AS String) AS category,
                CAST(count() AS UInt64) AS order_event_count
            FROM (
                SELECT anchor.*
                FROM orders_demo.tbl__order_items AS anchor
                INNER JOIN cutoff_offsets
                    ON anchor._replay_partition = cutoff_offsets._replay_partition
                LEFT JOIN active_start_offsets
                    ON anchor._replay_partition =
                       active_start_offsets._replay_partition
                WHERE anchor._replay_offset <= cutoff_offsets.cutoff_offset
                  AND (
                    active_start_offsets.start_offset IS NULL
                    OR anchor._replay_offset >= active_start_offsets.start_offset
                  )
            ) AS item_rows
            WHERE status = 'created'
            GROUP BY event_hour, category
            """
            ).strip(),
            replay_table_name_by_logical_name={
                "tbl__order_items": "tbl__order_items",
            },
        ),
        RenderOffsetReplayStatementTestCase(
            description=(
                "renders offset replay with staged reference joins and preserved source alias"
            ),
            source_table_name="tbl__orders",
            target_table_name="tbl__enriched_orders",
            shadow_target_name="tbl__enriched_orders__dep",
            anchor_table_name="tbl__orders__dep",
            query=(
                "SELECT CAST(o.order_id AS String) AS order_id, "
                "CAST(r.region_display AS String) AS region_display, "
                "CAST(o._replay_partition AS Int64) AS _replay_partition, "
                "CAST(o._replay_offset AS Int64) AS _replay_offset "
                "FROM tbl__orders AS o "
                "LEFT JOIN tbl__region_lookup AS r ON o.order_id = r.region"
            ),
            expected_statement=dedent(
                """
            INSERT INTO orders_demo.tbl__enriched_orders__dep
            WITH cutoff_offsets AS (
                SELECT 0 AS _replay_partition, 9709 AS cutoff_offset
            ),
            active_start_offsets AS (
                SELECT 0 AS _replay_partition, 9000 AS start_offset
            )
            SELECT replay_source.*
            FROM (
                SELECT
                    CAST(o.order_id AS String) AS order_id,
                    CAST(r.region_display AS String) AS region_display,
                    CAST(o._replay_partition AS Int64) AS _replay_partition,
                    CAST(o._replay_offset AS Int64) AS _replay_offset
                FROM orders_demo.tbl__orders__dep AS o
                LEFT JOIN orders_demo.tbl__region_lookup__dep AS r
                    ON o.order_id = r.region
            ) AS replay_source
            INNER JOIN cutoff_offsets
                ON replay_source._replay_partition = cutoff_offsets._replay_partition
            LEFT JOIN active_start_offsets
                ON replay_source._replay_partition = active_start_offsets._replay_partition
            WHERE replay_source._replay_offset <= cutoff_offsets.cutoff_offset
              AND (
                active_start_offsets.start_offset IS NULL
                OR replay_source._replay_offset >= active_start_offsets.start_offset
              )
            """
            ).strip(),
            replay_table_name_by_logical_name={
                "tbl__orders": "tbl__orders__dep",
                "tbl__region_lookup": "tbl__region_lookup__dep",
            },
        ),
        RenderOffsetReplayStatementTestCase(
            description=(
                "renders offset replay with unstaged reference joins against active logical tables"
            ),
            source_table_name="tbl__orders",
            target_table_name="tbl__enriched_orders",
            shadow_target_name="tbl__enriched_orders__dep",
            anchor_table_name="tbl__orders__dep",
            query=(
                "SELECT CAST(o.order_id AS String) AS order_id, "
                "CAST(r.region_display AS String) AS region_display, "
                "CAST(o._replay_partition AS Int64) AS _replay_partition, "
                "CAST(o._replay_offset AS Int64) AS _replay_offset "
                "FROM tbl__orders AS o "
                "LEFT JOIN tbl__region_lookup AS r ON o.order_id = r.region"
            ),
            expected_statement=dedent(
                """
            INSERT INTO orders_demo.tbl__enriched_orders__dep
            WITH cutoff_offsets AS (
                SELECT 0 AS _replay_partition, 9709 AS cutoff_offset
            ),
            active_start_offsets AS (
                SELECT 0 AS _replay_partition, 9000 AS start_offset
            )
            SELECT replay_source.*
            FROM (
                SELECT
                    CAST(o.order_id AS String) AS order_id,
                    CAST(r.region_display AS String) AS region_display,
                    CAST(o._replay_partition AS Int64) AS _replay_partition,
                    CAST(o._replay_offset AS Int64) AS _replay_offset
                FROM orders_demo.tbl__orders__dep AS o
                LEFT JOIN orders_demo.tbl__region_lookup AS r
                    ON o.order_id = r.region
            ) AS replay_source
            INNER JOIN cutoff_offsets
                ON replay_source._replay_partition = cutoff_offsets._replay_partition
            LEFT JOIN active_start_offsets
                ON replay_source._replay_partition = active_start_offsets._replay_partition
            WHERE replay_source._replay_offset <= cutoff_offsets.cutoff_offset
              AND (
                active_start_offsets.start_offset IS NULL
                OR replay_source._replay_offset >= active_start_offsets.start_offset
              )
            """
            ).strip(),
            replay_table_name_by_logical_name={
                "tbl__orders": "tbl__orders__dep",
                "tbl__region_lookup": "tbl__region_lookup",
            },
        ),
        RenderOffsetReplayStatementTestCase(
            description="renders offset replay with mixed staged and active reference joins",
            source_table_name="tbl__orders",
            target_table_name="tbl__enriched_orders",
            shadow_target_name="tbl__enriched_orders__dep",
            anchor_table_name="tbl__orders__dep",
            query=(
                "SELECT CAST(o.order_id AS String) AS order_id, "
                "CAST(r.region_display AS String) AS region_display, "
                "CAST(c.tier_name AS String) AS tier_name, "
                "CAST(o._replay_partition AS Int64) AS _replay_partition, "
                "CAST(o._replay_offset AS Int64) AS _replay_offset "
                "FROM tbl__orders AS o "
                "LEFT JOIN tbl__region_lookup AS r ON o.order_id = r.region "
                "LEFT JOIN tbl__customer_tier AS c ON o.order_id = c.customer_id"
            ),
            expected_statement=dedent(
                """
            INSERT INTO orders_demo.tbl__enriched_orders__dep
            WITH cutoff_offsets AS (
                SELECT 0 AS _replay_partition, 9709 AS cutoff_offset
            ),
            active_start_offsets AS (
                SELECT 0 AS _replay_partition, 9000 AS start_offset
            )
            SELECT replay_source.*
            FROM (
                SELECT
                    CAST(o.order_id AS String) AS order_id,
                    CAST(r.region_display AS String) AS region_display,
                    CAST(c.tier_name AS String) AS tier_name,
                    CAST(o._replay_partition AS Int64) AS _replay_partition,
                    CAST(o._replay_offset AS Int64) AS _replay_offset
                FROM orders_demo.tbl__orders__dep AS o
                LEFT JOIN orders_demo.tbl__region_lookup__dep AS r
                    ON o.order_id = r.region
                LEFT JOIN orders_demo.tbl__customer_tier AS c
                    ON o.order_id = c.customer_id
            ) AS replay_source
            INNER JOIN cutoff_offsets
                ON replay_source._replay_partition = cutoff_offsets._replay_partition
            LEFT JOIN active_start_offsets
                ON replay_source._replay_partition = active_start_offsets._replay_partition
            WHERE replay_source._replay_offset <= cutoff_offsets.cutoff_offset
              AND (
                active_start_offsets.start_offset IS NULL
                OR replay_source._replay_offset >= active_start_offsets.start_offset
              )
            """
            ).strip(),
            replay_table_name_by_logical_name={
                "tbl__orders": "tbl__orders__dep",
                "tbl__region_lookup": "tbl__region_lookup__dep",
                "tbl__customer_tier": "tbl__customer_tier",
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_offset_replay_query_when_rendering_then_it_rewrites_anchor_and_reference_tables(
    test_case: RenderOffsetReplayStatementTestCase,
) -> None:
    rendered_statement: str = _render_offset_replay_statement(
        root_materialized_view=DesiredMaterializedView(
            key=ObjectKey(None, "materialized_view", "mv__hourly_order_volume"),
            deps=(ObjectKey(None, "table", test_case.source_table_name),),
            spec=MaterializedViewSpec(
                source_table_name=test_case.source_table_name,
                target_table_name=test_case.target_table_name,
                query=test_case.query,
            ),
        ),
        shadow_target_name=test_case.shadow_target_name,
        anchor_table_name=test_case.anchor_table_name,
        database="orders_demo",
        replay_table_name_by_logical_name=test_case.replay_table_name_by_logical_name,
        deployment_watermarks=(
            DeploymentWatermarkRecord(
                deployment_id="dep",
                root_key=ObjectKey(None, "table", test_case.target_table_name),
                anchor_key=ObjectKey(None, "table", test_case.source_table_name),
                boundary_key="_replay_partition=0",
                cutoff_value="9709",
            ),
        ),
        lower_bound_rows=(ActiveOffsetFrontierQueryRow(_replay_partition=0, cutoff_offset="9000"),),
    )

    assert normalize_clickhouse_sql(rendered_statement) == normalize_clickhouse_sql(
        test_case.expected_statement
    )
