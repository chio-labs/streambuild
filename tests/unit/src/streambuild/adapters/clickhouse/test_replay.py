from textwrap import dedent

import pytest

from streambuild.adapter.models import (
    AdapterDeploymentReplayRequest,
    AdapterPhysicalRelationMapping,
    AdapterReplayBoundary,
    AdapterReplayColumns,
    AdapterReplayRelations,
    AdapterReplayRequest,
    AdapterReplayWindow,
)
from streambuild.adapter.types import (
    AdapterReplayBoundaryMode,
    AdapterReplayLowerBoundMode,
    AdapterReplaySeedMode,
)
from streambuild.adapters.clickhouse._helpers.replay import (
    _render_offset_replay,
    _render_scalar_replay,
    render_clickhouse_replay_from_deployment,
)
from streambuild.adapters.clickhouse.models import ClickHouseReplayOffsetFrontier
from streambuild.compiler.planner.main.build_adapter_replay_query import (
    build_adapter_replay_query,
)
from tests.unit.src.streambuild.adapters.clickhouse._test_types import (
    RenderAggregateOffsetPhysicalBoundaryTestCase,
    RenderAggregateScalarPhysicalBoundaryTestCase,
    RenderDeploymentLookbackTestCase,
    RenderOffsetReplayStatementTestCase,
    RenderScalarReplayBoundaryTestCase,
)
from tests.unit.src.streambuild.adapters.clickhouse.helpers import (
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
                SELECT 0 AS _replay_partition, 9709 AS cutoff_offset,
                       true AS cutoff_inclusive
            ),
            active_start_offsets AS (
                SELECT 0 AS _replay_partition, 9000 AS start_offset
            )
            SELECT
                CAST(toStartOfHour(_replay_timestamp) AS DateTime64(3)) AS event_hour,
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
                WHERE (
                    (
                        cutoff_offsets.cutoff_inclusive
                        AND anchor._replay_offset <= cutoff_offsets.cutoff_offset
                    )
                    OR (
                        NOT cutoff_offsets.cutoff_inclusive
                        AND anchor._replay_offset < cutoff_offsets.cutoff_offset
                    )
                )
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
                SELECT 0 AS _replay_partition, 9709 AS cutoff_offset,
                       true AS cutoff_inclusive
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
            WHERE (
                (
                    cutoff_offsets.cutoff_inclusive
                    AND replay_source._replay_offset <= cutoff_offsets.cutoff_offset
                )
                OR (
                    NOT cutoff_offsets.cutoff_inclusive
                    AND replay_source._replay_offset < cutoff_offsets.cutoff_offset
                )
            )
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
                SELECT 0 AS _replay_partition, 9709 AS cutoff_offset,
                       true AS cutoff_inclusive
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
            WHERE (
                (
                    cutoff_offsets.cutoff_inclusive
                    AND replay_source._replay_offset <= cutoff_offsets.cutoff_offset
                )
                OR (
                    NOT cutoff_offsets.cutoff_inclusive
                    AND replay_source._replay_offset < cutoff_offsets.cutoff_offset
                )
            )
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
                SELECT 0 AS _replay_partition, 9709 AS cutoff_offset,
                       true AS cutoff_inclusive
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
            WHERE (
                (
                    cutoff_offsets.cutoff_inclusive
                    AND replay_source._replay_offset <= cutoff_offsets.cutoff_offset
                )
                OR (
                    NOT cutoff_offsets.cutoff_inclusive
                    AND replay_source._replay_offset < cutoff_offsets.cutoff_offset
                )
            )
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
    physical_mappings: tuple[AdapterPhysicalRelationMapping, ...] = tuple(
        AdapterPhysicalRelationMapping(logical_name=logical_name, physical_name=physical_name)
        for logical_name, physical_name in test_case.replay_table_name_by_logical_name.items()
    )
    rendered_statement: str = _render_offset_replay(
        request=AdapterReplayRequest(
            mode=AdapterReplayBoundaryMode.OFFSETS,
            database="orders_demo",
            relations=AdapterReplayRelations(
                root=test_case.target_table_name,
                source=test_case.source_table_name,
                anchor=test_case.anchor_table_name,
                target=test_case.shadow_target_name,
            ),
            replay_query=build_adapter_replay_query(
                query=test_case.query,
                source_relation_name=test_case.source_table_name,
                database="orders_demo",
                physical_relation_mappings=physical_mappings,
            ),
            boundaries=(
                AdapterReplayBoundary(
                    boundary_key="_replay_partition=0",
                    cutoff_value="9709",
                    cutoff_inclusive=True,
                    partition_value="0",
                ),
            ),
            columns=AdapterReplayColumns(
                partition="_replay_partition",
                offset="_replay_offset",
                timestamp="_replay_timestamp",
                landed_at="_replay_landed_at",
                cursor="_replay_cursor",
            ),
            window=AdapterReplayWindow(
                lower_bound_mode=AdapterReplayLowerBoundMode.ACTIVE_FRONTIER,
                lower_bound_inclusive=True,
                boundary_time="2026-04-08 13:00:00.000",
                forced_start_time=None,
                lookback_seconds=None,
            ),
            seed_mode=AdapterReplaySeedMode.NONE,
            target_column_names=(),
        ),
        lower_bound_rows=(ClickHouseReplayOffsetFrontier(partition=0, cutoff_offset="9000"),),
    )

    assert normalize_clickhouse_sql(rendered_statement) == normalize_clickhouse_sql(
        test_case.expected_statement
    )


@pytest.mark.parametrize(
    "test_case",
    [
        RenderAggregateOffsetPhysicalBoundaryTestCase(
            description=(
                "filters every adopted aggregate source with its physical columns and "
                "partition-specific inclusivity"
            ),
            expected_inclusive_cte_fragment=(
                "0 AS _replay_partition, 10 AS cutoff_offset, TRUE AS cutoff_inclusive"
            ),
            expected_exclusive_cte_fragment=(
                "1 AS _replay_partition, 20 AS cutoff_offset, FALSE AS cutoff_inclusive"
            ),
            expected_partition_predicate=(
                "anchor.event_partition = cutoff_offsets._replay_partition"
            ),
            expected_offset_predicate=("anchor.event_offset <= cutoff_offsets.cutoff_offset"),
            expected_source_fragment="FROM orders_demo.orders_existing AS anchor",
            expected_occurrence_count=2,
            expected_absent_fragment="anchor._replay_offset",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_repeated_adopted_aggregate_source_when_rendering_then_each_source_is_filtered(
    test_case: RenderAggregateOffsetPhysicalBoundaryTestCase,
) -> None:
    rendered_statement: str = _render_offset_replay(
        request=AdapterReplayRequest(
            mode=AdapterReplayBoundaryMode.OFFSETS,
            database="orders_demo",
            relations=AdapterReplayRelations(
                root="tbl__order_pairs",
                source="orders_existing",
                anchor="orders_existing",
                target="tbl__order_pairs__dep",
            ),
            replay_query=build_adapter_replay_query(
                query=(
                    "SELECT CAST(count() AS UInt64) AS pair_count "
                    "FROM orders_existing AS left_orders "
                    "INNER JOIN orders_existing AS right_orders "
                    "ON left_orders.order_id = right_orders.order_id"
                ),
                source_relation_name="orders_existing",
                database="orders_demo",
                physical_relation_mappings=(
                    AdapterPhysicalRelationMapping(
                        logical_name="orders_existing",
                        physical_name="orders_existing",
                    ),
                ),
            ),
            boundaries=(
                AdapterReplayBoundary(
                    boundary_key="_replay_partition=0",
                    cutoff_value="10",
                    cutoff_inclusive=True,
                    partition_value="0",
                ),
                AdapterReplayBoundary(
                    boundary_key="_replay_partition=1",
                    cutoff_value="20",
                    cutoff_inclusive=False,
                    partition_value="1",
                ),
            ),
            columns=AdapterReplayColumns(
                partition="event_partition",
                offset="event_offset",
                timestamp="event_timestamp",
                landed_at="event_landed_at",
                cursor="event_cursor",
            ),
            window=AdapterReplayWindow(
                lower_bound_mode=AdapterReplayLowerBoundMode.ACTIVE_FRONTIER,
                lower_bound_inclusive=True,
                boundary_time="2026-04-08 13:00:00.000",
                forced_start_time=None,
                lookback_seconds=None,
            ),
            seed_mode=AdapterReplaySeedMode.NONE,
            target_column_names=(),
        ),
        lower_bound_rows=(ClickHouseReplayOffsetFrontier(partition=0, cutoff_offset="5"),),
    )
    normalized_statement: str = normalize_clickhouse_sql(rendered_statement)

    assert test_case.expected_inclusive_cte_fragment in normalized_statement
    assert test_case.expected_exclusive_cte_fragment in normalized_statement
    assert (
        normalized_statement.count(test_case.expected_partition_predicate)
        == test_case.expected_occurrence_count
    )
    assert (
        normalized_statement.count(test_case.expected_offset_predicate)
        == test_case.expected_occurrence_count
    )
    assert (
        normalized_statement.count(test_case.expected_source_fragment)
        == test_case.expected_occurrence_count
    )
    assert test_case.expected_absent_fragment not in normalized_statement


@pytest.mark.parametrize(
    "test_case",
    [
        RenderScalarReplayBoundaryTestCase(
            description="renders inclusive timestamp replay boundaries",
            mode=AdapterReplayBoundaryMode.TIMESTAMP,
            boundary_key="_replay_timestamp",
            boundary_column_type="DateTime64(3)",
            cutoff_value="2026-04-08 13:00:00.000",
            lower_bound_value="2026-04-08 12:00:00.000",
            cutoff_inclusive=True,
            lower_bound_inclusive=True,
            query=(
                "SELECT order_id, _replay_timestamp, _replay_landed_at, _replay_cursor "
                "FROM raw__orders"
            ),
            expected_lower_fragment=(
                "_replay_timestamp >= CAST('2026-04-08 12:00:00.000' AS DateTime64(3))"
            ),
            expected_upper_fragment=(
                "_replay_timestamp <= CAST('2026-04-08 13:00:00.000' AS DateTime64(3))"
            ),
            expected_where_fragment="WHERE _replay_timestamp >=",
        ),
        RenderScalarReplayBoundaryTestCase(
            description="renders inclusive landed-at replay boundaries",
            mode=AdapterReplayBoundaryMode.LANDED_AT,
            boundary_key="_replay_landed_at",
            boundary_column_type="DateTime64(3)",
            cutoff_value="2026-04-08 13:00:00.000",
            lower_bound_value="2026-04-08 12:00:00.000",
            cutoff_inclusive=True,
            lower_bound_inclusive=True,
            query=(
                "SELECT order_id, _replay_timestamp, _replay_landed_at, _replay_cursor "
                "FROM raw__orders"
            ),
            expected_lower_fragment=(
                "_replay_landed_at >= CAST('2026-04-08 12:00:00.000' AS DateTime64(3))"
            ),
            expected_upper_fragment=(
                "_replay_landed_at <= CAST('2026-04-08 13:00:00.000' AS DateTime64(3))"
            ),
            expected_where_fragment="WHERE _replay_landed_at >=",
        ),
        RenderScalarReplayBoundaryTestCase(
            description="renders inclusive cursor replay boundaries",
            mode=AdapterReplayBoundaryMode.CURSOR,
            boundary_key="_replay_cursor",
            boundary_column_type="UInt64",
            cutoff_value="20",
            lower_bound_value="10",
            cutoff_inclusive=True,
            lower_bound_inclusive=True,
            query=(
                "SELECT order_id, _replay_timestamp, _replay_landed_at, _replay_cursor "
                "FROM raw__orders"
            ),
            expected_lower_fragment="_replay_cursor >= CAST('10' AS UInt64)",
            expected_upper_fragment="_replay_cursor <= CAST('20' AS UInt64)",
            expected_where_fragment="WHERE _replay_cursor >=",
        ),
        RenderScalarReplayBoundaryTestCase(
            description="preserves authored disjunction before cursor replay boundaries",
            mode=AdapterReplayBoundaryMode.CURSOR,
            boundary_key="_replay_cursor",
            boundary_column_type="UInt64",
            cutoff_value="20",
            lower_bound_value="10",
            cutoff_inclusive=True,
            lower_bound_inclusive=True,
            query=(
                "SELECT order_id, _replay_cursor FROM raw__orders "
                "WHERE status = 'open' OR status = 'held'"
            ),
            expected_lower_fragment="_replay_cursor >= CAST('10' AS UInt64)",
            expected_upper_fragment="_replay_cursor <= CAST('20' AS UInt64)",
            expected_where_fragment=(
                "WHERE (status = 'open' OR status = 'held') "
                "AND (_replay_cursor >= CAST('10' AS UInt64)"
            ),
        ),
        RenderScalarReplayBoundaryTestCase(
            description="renders exclusive scalar replay boundaries",
            mode=AdapterReplayBoundaryMode.CURSOR,
            boundary_key="_replay_cursor",
            boundary_column_type="UInt64",
            cutoff_value="20",
            lower_bound_value="10",
            cutoff_inclusive=False,
            lower_bound_inclusive=False,
            query="SELECT order_id, _replay_cursor FROM raw__orders",
            expected_lower_fragment="_replay_cursor > CAST('10' AS UInt64)",
            expected_upper_fragment="_replay_cursor < CAST('20' AS UInt64)",
            expected_where_fragment="WHERE _replay_cursor >",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scalar_replay_boundary_when_rendering_then_expected_edges_are_used(
    test_case: RenderScalarReplayBoundaryTestCase,
) -> None:
    boundary: AdapterReplayBoundary = AdapterReplayBoundary(
        boundary_key=test_case.boundary_key,
        cutoff_value=test_case.cutoff_value,
        cutoff_inclusive=test_case.cutoff_inclusive,
    )
    request: AdapterReplayRequest = AdapterReplayRequest(
        mode=test_case.mode,
        database="orders_demo",
        relations=AdapterReplayRelations(
            root="tbl__orders_enriched",
            source="raw__orders",
            anchor="raw__orders",
            target="tbl__orders_enriched__dep",
        ),
        replay_query=build_adapter_replay_query(
            query=test_case.query,
            source_relation_name="raw__orders",
            database="orders_demo",
            physical_relation_mappings=(
                AdapterPhysicalRelationMapping(
                    logical_name="raw__orders",
                    physical_name="raw__orders",
                ),
            ),
        ),
        boundaries=(boundary,),
        columns=AdapterReplayColumns(
            partition="_replay_partition",
            offset="_replay_offset",
            timestamp="_replay_timestamp",
            landed_at="_replay_landed_at",
            cursor="_replay_cursor",
        ),
        window=AdapterReplayWindow(
            lower_bound_mode=AdapterReplayLowerBoundMode.ACTIVE_FRONTIER,
            lower_bound_inclusive=test_case.lower_bound_inclusive,
            boundary_time="2026-04-08 13:00:00.000",
            forced_start_time=None,
            lookback_seconds=None,
        ),
        seed_mode=AdapterReplaySeedMode.NONE,
        target_column_names=("order_id",),
    )

    rendered_statement: str = _render_scalar_replay(
        request=request,
        boundary=boundary,
        boundary_column_type=test_case.boundary_column_type,
        lower_bound_value=test_case.lower_bound_value,
    )
    normalized_statement: str = normalize_clickhouse_sql(rendered_statement)

    assert test_case.expected_lower_fragment in normalized_statement
    assert test_case.expected_upper_fragment in normalized_statement
    assert test_case.expected_where_fragment in normalized_statement


@pytest.mark.parametrize(
    "test_case",
    [
        RenderAggregateScalarPhysicalBoundaryTestCase(
            description="filters adopted anchor rows before scalar aggregation",
            expected_source_fragment=(
                "FROM (SELECT anchor.* FROM orders_demo.orders_existing AS anchor"
            ),
            expected_lower_fragment="anchor.event_cursor >= CAST('10' AS UInt64)",
            expected_upper_fragment="anchor.event_cursor <= CAST('20' AS UInt64)",
            expected_outer_where_fragment="AS item_rows WHERE status = 'created' GROUP BY category",
            expected_absent_fragment="WHERE _replay_cursor >=",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_aggregate_scalar_replay_when_rendering_then_anchor_is_filtered_before_grouping(
    test_case: RenderAggregateScalarPhysicalBoundaryTestCase,
) -> None:
    boundary: AdapterReplayBoundary = AdapterReplayBoundary(
        boundary_key="_replay_cursor",
        cutoff_value="20",
        cutoff_inclusive=True,
    )
    request: AdapterReplayRequest = AdapterReplayRequest(
        mode=AdapterReplayBoundaryMode.CURSOR,
        database="orders_demo",
        relations=AdapterReplayRelations(
            root="tbl__order_counts",
            source="orders_existing",
            anchor="orders_existing",
            target="tbl__order_counts__dep",
        ),
        replay_query=build_adapter_replay_query(
            query=(
                "SELECT category, count() AS order_count "
                "FROM orders_existing AS item_rows "
                "WHERE status = 'created' GROUP BY category"
            ),
            source_relation_name="orders_existing",
            database="orders_demo",
            physical_relation_mappings=(
                AdapterPhysicalRelationMapping(
                    logical_name="orders_existing",
                    physical_name="orders_existing",
                ),
            ),
        ),
        boundaries=(boundary,),
        columns=AdapterReplayColumns(
            partition="event_partition",
            offset="event_offset",
            timestamp="event_timestamp",
            landed_at="event_landed_at",
            cursor="event_cursor",
        ),
        window=AdapterReplayWindow(
            lower_bound_mode=AdapterReplayLowerBoundMode.ACTIVE_FRONTIER,
            lower_bound_inclusive=True,
            boundary_time="2026-04-08 13:00:00.000",
            forced_start_time=None,
            lookback_seconds=None,
        ),
        seed_mode=AdapterReplaySeedMode.NONE,
        target_column_names=(),
    )

    rendered_statement: str = _render_scalar_replay(
        request=request,
        boundary=boundary,
        boundary_column_type="UInt64",
        lower_bound_value="10",
    )
    normalized_statement: str = normalize_clickhouse_sql(rendered_statement)

    assert test_case.expected_source_fragment in normalized_statement
    assert test_case.expected_lower_fragment in normalized_statement
    assert test_case.expected_upper_fragment in normalized_statement
    assert test_case.expected_outer_where_fragment in normalized_statement
    assert test_case.expected_absent_fragment not in normalized_statement


@pytest.mark.parametrize(
    "test_case",
    [
        RenderDeploymentLookbackTestCase(
            description="uses deployment-wide boundary time and root-scoped replay cutoff",
            expected_boundary_lookup_fragment=(
                "FROM metadata._streambuild_virtual_deployments WHERE deployment_id = 'dep-1'"
            ),
            expected_root_filter_fragment="root_object_name = 'tbl__orders_enriched'",
            expected_root_filter_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_deployment_lookback_when_rendering_then_boundary_time_is_deployment_wide(
    test_case: RenderDeploymentLookbackTestCase,
) -> None:
    replay: AdapterReplayRequest = AdapterReplayRequest(
        mode=AdapterReplayBoundaryMode.OFFSETS,
        database="orders_demo",
        relations=AdapterReplayRelations(
            root="tbl__orders_enriched",
            source="raw__orders",
            anchor="raw__orders",
            target="tbl__orders_enriched__dep",
        ),
        replay_query=build_adapter_replay_query(
            query="SELECT order_id, _replay_partition, _replay_offset FROM raw__orders",
            source_relation_name="raw__orders",
            database="orders_demo",
            physical_relation_mappings=(
                AdapterPhysicalRelationMapping(
                    logical_name="raw__orders",
                    physical_name="raw__orders",
                ),
            ),
        ),
        boundaries=(),
        columns=AdapterReplayColumns(
            partition="_replay_partition",
            offset="_replay_offset",
            timestamp="_replay_timestamp",
            landed_at="_replay_landed_at",
            cursor="_replay_cursor",
        ),
        window=AdapterReplayWindow(
            lower_bound_mode=AdapterReplayLowerBoundMode.LOOKBACK,
            lower_bound_inclusive=True,
            boundary_time="2026-04-08 13:00:00.000",
            forced_start_time=None,
            lookback_seconds=8,
        ),
        seed_mode=AdapterReplaySeedMode.NONE,
        target_column_names=("order_id", "_replay_partition", "_replay_offset"),
    )
    rendered_statements: tuple[str, ...] = render_clickhouse_replay_from_deployment(
        AdapterDeploymentReplayRequest(
            replay=replay,
            metadata_database="metadata",
            deployment_id="dep-1",
            boundary_column_type=None,
            active_relation_name="tbl__orders_enriched",
            active_column_names=replay.target_column_names,
            anchor_column_names=replay.target_column_names,
        )
    )
    normalized_statement: str = normalize_clickhouse_sql(rendered_statements[0])

    assert test_case.expected_boundary_lookup_fragment in normalized_statement
    assert (
        normalized_statement.count(test_case.expected_root_filter_fragment)
        == test_case.expected_root_filter_count
    )
