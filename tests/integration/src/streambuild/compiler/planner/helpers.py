from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.spec.models.pipeline import Pipeline
from streambuild.spec.models.steps import KafkaLandingStep, KafkaSettings, TransformStep
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


def build_changed_schema_variant_compiled_pipeline(kind: str) -> CompiledPipeline:
    if kind == "add_column":
        return build_changed_schema_compiled_pipeline()
    if kind == "remove_column":
        return build_removed_column_compiled_pipeline()
    if kind == "add_and_remove_columns":
        return build_add_and_remove_columns_compiled_pipeline()
    if kind == "type_change":
        return build_type_changed_compiled_pipeline()
    raise ValueError(kind)
