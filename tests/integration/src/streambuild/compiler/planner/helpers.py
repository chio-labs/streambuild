from collections.abc import Callable
from dataclasses import replace
from typing import cast

from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    Column,
    CompiledPipeline,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
)
from streambuild.compiler.discovery.models import (
    KafkaLandingStep,
    KafkaSettings,
    LoadedPipeline,
    Pipeline,
    TransformStep,
)
from streambuild.compiler.planner.models import DeploymentPlan, PlannedObjectChange
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
