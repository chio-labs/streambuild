from collections.abc import Callable
from dataclasses import replace
from typing import cast

from clickhouse_connect.driver.client import Client

from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    Column,
    CompiledPipeline,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    MaterializedViewSpec,
)
from streambuild.compiler.discovery.models import (
    KafkaLandingStep,
    KafkaSettings,
    LoadedPipeline,
    Pipeline,
    TransformStep,
)
from streambuild.compiler.planner.models import DeploymentPlan, PlannedObjectChange
from tests.integration.src.streambuild.adapters.clickhouse.helpers import (
    render_create_materialized_view_ddl,
    render_create_table_ddl,
    render_create_view_ddl,
)
from tests.integration.src.streambuild.executor.backfill.helpers import require_managed_source
from tests.unit.src.streambuild.compiler.planner.helpers import EXAMPLE_PIPELINE_FILE_PATH


def build_changed_sql_compiled_pipeline() -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=(
                    "SELECT CAST(kafka_key AS String) AS order_id, "
                    "CAST(toDateTime64(_replay_timestamp, 3) AS DateTime64(3)) "
                    "AS _replay_timestamp "
                    'FROM __ref("orders")'
                ),
                replay_anchor="never",
            )
        ],
        replay_lineage_mode="timestamp",
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_changed_schema_compiled_pipeline() -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=(
                    "SELECT CAST(kafka_key AS String) AS order_id, "
                    "CAST(toDateTime64(_replay_timestamp, 3) AS DateTime64(3)) "
                    "AS _replay_timestamp, "
                    "CAST(kafka_topic AS String) AS kafka_topic "
                    'FROM __ref("orders")'
                ),
                replay_anchor="never",
            )
        ],
        replay_lineage_mode="timestamp",
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_removed_column_compiled_pipeline() -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=('SELECT CAST(kafka_key AS String) AS order_id FROM __ref("orders")'),
                replay_anchor="never",
            )
        ],
        replay_lineage_mode="timestamp",
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_add_and_remove_columns_compiled_pipeline() -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=(
                    "SELECT CAST(kafka_key AS String) AS order_id, "
                    "CAST(kafka_topic AS String) AS kafka_topic "
                    'FROM __ref("orders")'
                ),
                replay_anchor="never",
            )
        ],
        replay_lineage_mode="timestamp",
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


def build_type_changed_compiled_pipeline() -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=(
                    "SELECT CAST(kafka_key AS String) AS order_id, "
                    "CAST(_replay_timestamp AS String) AS _replay_timestamp "
                    'FROM __ref("orders")'
                ),
                replay_anchor="never",
            )
        ],
        replay_lineage_mode="timestamp",
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=EXAMPLE_PIPELINE_FILE_PATH,
            project=None,
        )
    )


CHANGED_SCHEMA_VARIANT_BUILDERS: dict[str, Callable[[], CompiledPipeline]] = {
    "add_column": lambda: build_changed_schema_compiled_pipeline(),
    "remove_column": lambda: build_removed_column_compiled_pipeline(),
    "add_and_remove_columns": lambda: build_add_and_remove_columns_compiled_pipeline(),
    "type_change": lambda: build_type_changed_compiled_pipeline(),
}


def build_changed_schema_variant_compiled_pipeline(kind: str) -> CompiledPipeline:
    """Build the compiled pipeline for a named schema-change variant."""

    return CHANGED_SCHEMA_VARIANT_BUILDERS[kind]()


def normalize_orders_enriched_timestamp_type(desired_state: DesiredState) -> DesiredState:
    object_by_name: dict[str, DesiredKafkaTable | DesiredTable | DesiredMaterializedView] = {
        desired_object.name: desired_object for desired_object in desired_state.objects
    }
    target_table: DesiredTable = cast(DesiredTable, object_by_name["tbl__orders_enriched"])
    column_by_name: dict[str, Column] = {
        column.name: column for column in target_table.spec.columns
    }
    column_by_name["_replay_timestamp"] = replace(
        target_table.spec.columns[1], type="DATETIME64(3)"
    )
    object_by_name[target_table.name] = replace(
        target_table,
        spec=replace(
            target_table.spec,
            columns=tuple(column_by_name[column.name] for column in target_table.spec.columns),
        ),
    )
    return DesiredState(
        objects=tuple(object_by_name[object_.name] for object_ in desired_state.objects),
        replay_anchor_keys=desired_state.replay_anchor_keys,
        mutable_ref_warning_keys=desired_state.mutable_ref_warning_keys,
    )


def get_orders_enriched_change(plan: DeploymentPlan) -> PlannedObjectChange:
    change_by_name: dict[str, PlannedObjectChange] = {
        change.key.name: change for change in plan.object_changes
    }
    return change_by_name["tbl__orders_enriched"]


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


def _create_orders_candidates(*, clickhouse_client: Client, clickhouse_database: str) -> None:
    clickhouse_client.command(
        "CREATE TABLE "
        f"{clickhouse_database}.tbl__orders_enriched__dep_a "
        "(order_id String, _replay_timestamp DateTime64(3)) "
        "ENGINE = MergeTree ORDER BY (order_id)"
    )
    clickhouse_client.command(
        "CREATE MATERIALIZED VIEW "
        f"{clickhouse_database}.mv__orders_enriched__dep_a "
        f"TO {clickhouse_database}.tbl__orders_enriched__dep_a AS "
        "SELECT CAST(kafka_key AS String) AS order_id, "
        "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp "
        f"FROM {clickhouse_database}.raw__orders"
    )


def _create_customers_candidates(*, clickhouse_client: Client, clickhouse_database: str) -> None:
    clickhouse_client.command(
        "CREATE TABLE "
        f"{clickhouse_database}.tbl__customers_enriched__dep_b "
        "(order_id String, _replay_timestamp DateTime64(3)) "
        "ENGINE = MergeTree ORDER BY (order_id)"
    )
    clickhouse_client.command(
        "CREATE MATERIALIZED VIEW "
        f"{clickhouse_database}.mv__customers_enriched__dep_b "
        f"TO {clickhouse_database}.tbl__customers_enriched__dep_b AS "
        "SELECT CAST(kafka_key AS String) AS order_id, "
        "CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp "
        f"FROM {clickhouse_database}.raw__customers"
    )


def _create_orders_active_view(*, clickhouse_client: Client, clickhouse_database: str) -> None:
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__orders_enriched",
            target_table_name="tbl__orders_enriched__dep_a",
        )
    )


def _create_customers_active_view(*, clickhouse_client: Client, clickhouse_database: str) -> None:
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__customers_enriched",
            target_table_name="tbl__customers_enriched__dep_b",
        )
    )


def _create_customers_invalid_view(*, clickhouse_client: Client, clickhouse_database: str) -> None:
    clickhouse_client.command(
        "CREATE TABLE "
        f"{clickhouse_database}.tbl__customers_enriched_manual "
        "(order_id String) ENGINE = MergeTree ORDER BY (order_id)"
    )
    clickhouse_client.command(
        render_create_view_ddl(
            database=clickhouse_database,
            view_name="tbl__customers_enriched",
            target_table_name="tbl__customers_enriched_manual",
        )
    )


MIXED_ROOT_SETUP_STEPS: dict[str, Callable[..., None]] = {
    "orders_candidates": _create_orders_candidates,
    "customers_candidates": _create_customers_candidates,
    "orders_active_view": _create_orders_active_view,
    "customers_active_view": _create_customers_active_view,
    "customers_invalid_view": _create_customers_invalid_view,
}
