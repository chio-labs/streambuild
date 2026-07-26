"""Warehouse setup steps for actual-state integration tests."""

from collections.abc import Callable
from dataclasses import replace

from clickhouse_connect.driver.client import Client

from streambuild.clickhouse.render._helpers.create_materialized_view import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render._helpers.create_table import render_create_table_ddl
from streambuild.clickhouse.render._helpers.create_view import render_create_view_ddl
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.shared.models import DesiredMaterializedView, MaterializedViewSpec
from tests.integration.src.streambuild.executor.backfill.helpers import (
    require_managed_source,
)


def _create_standard_raw_landing(
    *, clickhouse_client: Client, clickhouse_database: str, compiled_pipeline: CompiledPipeline
) -> None:
    clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table,
            database=clickhouse_database,
        )
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=clickhouse_database,
        )
    )


def _create_suffixed_raw_landing(
    *, clickhouse_client: Client, clickhouse_database: str, compiled_pipeline: CompiledPipeline
) -> None:
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.raw__orders__dep_a "
        "(kafka_key String, kafka_value String, kafka_topic String, "
        "_replay_partition Int64, _replay_offset Int64, "
        "_replay_timestamp DateTime64(3), kafka_headers String, "
        "_replay_landed_at DateTime64(3)) "
        "ENGINE = MergeTree ORDER BY (_replay_partition, _replay_offset)"
    )
    source_materialized_view: DesiredMaterializedView = require_managed_source(
        compiled_pipeline
    ).materialized_view
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=replace(
                source_materialized_view,
                key=replace(source_materialized_view.key, name="mv__orders__dep_a"),
                spec=MaterializedViewSpec(
                    source_table_name=source_materialized_view.source_table_name,
                    target_table_name="raw__orders__dep_a",
                    query=source_materialized_view.query,
                ),
            ),
            database=clickhouse_database,
        )
    )


def _create_target_table(
    *, clickhouse_client: Client, clickhouse_database: str, compiled_pipeline: CompiledPipeline
) -> None:
    clickhouse_client.command(
        render_create_table_ddl(
            table=compiled_pipeline.transforms[0].target_table, database=clickhouse_database
        )
    )


def _create_physical_candidates(
    *, clickhouse_client: Client, clickhouse_database: str, compiled_pipeline: CompiledPipeline
) -> None:
    del compiled_pipeline
    clickhouse_client.command(
        f"CREATE TABLE {clickhouse_database}.tbl__orders_enriched__dep_a "
        "(order_id String, _replay_timestamp DateTime64(3)) "
        "ENGINE = MergeTree ORDER BY (order_id)"
    )


def _create_candidate_materialized_view(
    *, clickhouse_client: Client, clickhouse_database: str, compiled_pipeline: CompiledPipeline
) -> None:
    del compiled_pipeline
    clickhouse_client.command(
        f"CREATE MATERIALIZED VIEW {clickhouse_database}.mv__orders_enriched__dep_a "
        f"TO {clickhouse_database}.tbl__orders_enriched__dep_a AS "
        "SELECT CAST(kafka_key AS String) AS order_id, "
        "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp "
        f"FROM {clickhouse_database}.raw__orders"
    )


def _create_stable_view(
    *, clickhouse_client: Client, clickhouse_database: str, compiled_pipeline: CompiledPipeline
) -> None:
    del compiled_pipeline
    clickhouse_client.command(f"DROP TABLE {clickhouse_database}.tbl__orders_enriched")
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__orders_enriched",
            target_table_name="tbl__orders_enriched__dep_a",
        )
    )


ACTUAL_STATE_SETUP_STEPS: dict[str, Callable[..., None]] = {
    "standard_raw_landing": _create_standard_raw_landing,
    "suffixed_raw_landing": _create_suffixed_raw_landing,
    "target_table": _create_target_table,
    "physical_candidates": _create_physical_candidates,
    "candidate_materialized_view": _create_candidate_materialized_view,
    "stable_view": _create_stable_view,
}
