from pathlib import Path
from textwrap import dedent, indent
from typing import cast

from streambuild.adapter.models import AdapterManagedSource, AdapterMaterializedView, AdapterTable
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.compiler.compile.main._compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledPipeline,
    CompiledProject,
    CompiledSource,
    CompilerAdapterProfile,
    LogicalResourceKey,
)
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.discovery.models import (
    KafkaLandingStep,
    KafkaSettings,
    LoadedPipeline,
    Pipeline,
    TransformStep,
)
from streambuild.compiler.pipeline.main._realize_project import realize_project
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from streambuild.compiler.sql_analysis.models import SqlModelAnalysis


def compile_test_pipeline(loaded_pipeline: LoadedPipeline) -> CompiledPipeline:
    return compile_pipeline(
        loaded_pipeline=loaded_pipeline,
        sql_analyzer=SqlModelAnalyzer(dialect="clickhouse"),
    )


def compile_and_realize_pipeline(
    loaded_pipeline: LoadedPipeline,
) -> tuple[CompiledPipeline, RealizedProject]:
    sql_analyzer: SqlModelAnalyzer = SqlModelAnalyzer(dialect="clickhouse")
    compiled_pipeline: CompiledPipeline = compile_pipeline(
        loaded_pipeline=loaded_pipeline,
        sql_analyzer=sql_analyzer,
    )
    return compiled_pipeline, realize_compiled_pipeline(
        compiled_pipeline=compiled_pipeline,
        sql_analyzer=sql_analyzer,
    )


def build_realization_analyzer(compiled_project: CompiledProject) -> SqlModelAnalyzer:
    sql_analyzer: SqlModelAnalyzer = SqlModelAnalyzer(dialect="clickhouse")
    model: CompiledModel
    for model in compiled_project.models:
        analysis: SqlModelAnalysis = sql_analyzer.analyze(
            sql=model.query,
            engine=model.transform.engine,
            order_by=tuple(model.transform.order_by),
            partition_by=model.transform.partition_by,
            ttl=model.transform.ttl,
        )
        assert analysis == model.sql_analysis
    return sql_analyzer


def realize_compiled_pipeline(
    *, compiled_pipeline: CompiledPipeline, sql_analyzer: SqlModelAnalyzer
) -> RealizedProject:
    compiled_project: CompiledProject = CompiledProject(
        sources=(compiled_pipeline.source,),
        models=compiled_pipeline.models,
        pipelines=(compiled_pipeline,),
        tests=(),
        test_cases=(),
        audits=(),
    )
    adapter_profile: CompilerAdapterProfile = build_compiler_adapter_profile(ClickHouseAdapter())
    return realize_project(
        project=compiled_project,
        adapter_profile=adapter_profile,
        sql_analyzer=sql_analyzer,
    )


def realized_model_table(realized_project: RealizedProject, model_name: str) -> AdapterTable:
    key: LogicalResourceKey = LogicalResourceKey(
        resource_type=LogicalResourceType.MODEL,
        name=model_name,
    )
    return cast(AdapterTable, realized_project.resources_by_logical_key[key][0])


def realized_model_view(
    realized_project: RealizedProject, model_name: str
) -> AdapterMaterializedView:
    key: LogicalResourceKey = LogicalResourceKey(
        resource_type=LogicalResourceType.MODEL,
        name=model_name,
    )
    return cast(AdapterMaterializedView, realized_project.resources_by_logical_key[key][1])


def realized_managed_source(realized_project: RealizedProject) -> AdapterManagedSource:
    source: CompiledSource = realized_project.project.sources[0]
    return cast(AdapterManagedSource, realized_project.resources_by_logical_key[source.key][0])


def realized_source_table(realized_project: RealizedProject) -> AdapterTable:
    source: CompiledSource = realized_project.project.sources[0]
    return cast(AdapterTable, realized_project.resources_by_logical_key[source.key][1])


def realized_source_view(realized_project: RealizedProject) -> AdapterMaterializedView:
    source: CompiledSource = realized_project.project.sources[0]
    return cast(AdapterMaterializedView, realized_project.resources_by_logical_key[source.key][2])


def write_registry_pipeline_project(
    *, project_dir: Path, source_contents: str, model_contents: str
) -> Path:
    pipeline_root: Path = project_dir / "pipelines" / "orders"
    pipeline_root.mkdir(parents=True, exist_ok=True)
    (project_dir / "streambuild_project.toml").write_text(
        'name = "test_project"\ndefault_target = "test"\n\n'
        '[targets.test]\ndatabase = "analytics"\n',
        encoding="utf-8",
    )
    source_body: str = dedent(dedent(source_contents).strip().removeprefix("source:\n"))
    source_dir: Path = project_dir / "sources"
    source_dir.mkdir()
    (source_dir / "orders.yml").write_text(
        "sources:\n  - " + indent(source_body, "    ").lstrip() + "\n",
        encoding="utf-8",
    )
    (pipeline_root / "orders_enriched.sql").write_text(
        dedent(model_contents).strip() + "\n",
        encoding="utf-8",
    )
    return pipeline_root


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

    return LoadedPipeline(pipeline=pipeline, file_path=pipeline_root)


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
        file_path=Path("tests/fixtures/basic_project/pipelines/orders"),
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
        file_path=Path("tests/fixtures/basic_project/pipelines/orders"),
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
        file_path=Path("tests/fixtures/basic_project/pipelines/orders"),
    )
