from pathlib import Path

from streambuild.compiler.discovery.models import (
    KafkaLandingStep,
    KafkaSettings,
    LoadedPipeline,
    Pipeline,
    TransformStep,
)


def build_sql_file_pipeline(
    tmp_path: Path, sql_relative_path: str, sql_contents: str
) -> LoadedPipeline:
    pipeline_root: Path = tmp_path / "pipelines" / "shop"
    sql_file_path: Path = pipeline_root / sql_relative_path
    sql_file_path.parent.mkdir(parents=True)
    sql_file_path.write_text(sql_contents, encoding="utf-8")

    pipeline: Pipeline = Pipeline(
        name="tmp_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders",
                consumer_group="streambuild_tmp_pipeline_orders",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                sql_file=sql_relative_path,
            )
        ],
    )

    return LoadedPipeline(pipeline=pipeline, file_path=pipeline_root / "pipeline.yml")


def build_missing_source_ref_pipeline(transform_query: str) -> LoadedPipeline:
    pipeline: Pipeline = Pipeline(
        name="tmp_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders",
                consumer_group="streambuild_tmp_pipeline_orders",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=transform_query,
            )
        ],
    )

    return LoadedPipeline(
        pipeline=pipeline,
        file_path=Path("tests/fixtures/basic_project/pipelines/orders/pipeline.yml"),
    )


def build_inline_sql_pipeline(transform_query: str) -> LoadedPipeline:
    pipeline: Pipeline = Pipeline(
        name="tmp_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders",
                consumer_group="streambuild_tmp_pipeline_orders",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=transform_query,
            )
        ],
    )

    return LoadedPipeline(
        pipeline=pipeline,
        file_path=Path("tests/fixtures/basic_project/pipelines/orders/pipeline.yml"),
    )


def build_invalid_order_by_pipeline(transform_query: str, order_by: list[str]) -> LoadedPipeline:
    return build_invalid_storage_expression_pipeline(
        transform_query=transform_query,
        order_by=order_by,
    )


def build_invalid_storage_expression_pipeline(
    transform_query: str,
    order_by: list[str],
    partition_by: str | None = None,
    ttl: str | None = None,
) -> LoadedPipeline:
    pipeline: Pipeline = Pipeline(
        name="tmp_pipeline",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders",
                consumer_group="streambuild_tmp_pipeline_orders",
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=order_by,
                partition_by=partition_by,
                ttl=ttl,
                query=transform_query,
            )
        ],
    )

    return LoadedPipeline(
        pipeline=pipeline,
        file_path=Path("tests/fixtures/basic_project/pipelines/orders/pipeline.yml"),
    )
