from pathlib import Path

from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.compiler.compile.main._compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from streambuild.compiler.sql_analysis.classes.sql_reference_rewriter import (
    SqlReferenceRewriter,
)
from streambuild.compiler.test_discovery.main._discover_sql_tests import discover_sql_tests
from streambuild.compiler.test_discovery.models import LoadedSqlTest
from streambuild.compiler.testing.main._build_sql_test_cases import build_sql_test_cases
from streambuild.compiler.testing.models import SqlTestCase
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
    write_project_configuration_and_source,
)
from tests.unit.src.streambuild.compiler.test_discovery.helpers import (
    write_sql_test_file,
)

MODEL_SQL_BY_NAME: tuple[tuple[str, str], ...] = (
    (
        "order_items",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __ref("orders")
        """,
    ),
    (
        "daily_revenue",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(line_total AS Nullable(Float64)) AS line_total
        FROM __ref("order_items")
        """,
    ),
    (
        "revenue_report",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(line_total AS Nullable(Float64)) AS reported_total
        FROM __ref("daily_revenue")
        """,
    ),
    (
        "order_tax",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(line_total * 0.1 AS Nullable(Float64)) AS tax_total
        FROM __ref("order_items")
        """,
    ),
    (
        "order_summary",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(daily.order_id AS String) AS order_id,
          CAST(daily.line_total + tax.tax_total AS Nullable(Float64)) AS total_with_tax
        FROM __ref("daily_revenue") AS daily
        JOIN __ref("order_tax", ref_type='reference') AS tax ON daily.order_id = tax.order_id
        """,
    ),
)


def write_sql_test_project(*, tmp_path: Path, test_file_contents: str) -> Path:
    pipeline_dir: Path = tmp_path / "pipelines" / "order_events"
    write_project_configuration_and_source(project_dir=tmp_path)
    write_pipeline_file(pipeline_dir / "pipeline.yml", "source: orders")
    model_name: str
    model_sql: str
    for model_name, model_sql in MODEL_SQL_BY_NAME:
        write_pipeline_file(pipeline_dir / f"{model_name}.sql", model_sql)
    write_sql_test_file(tmp_path / "tests" / "order_events" / "test_case.sql", test_file_contents)
    return pipeline_dir / "pipeline.yml"


def build_compiled_pipeline_with_tests(
    *,
    tmp_path: Path,
    test_file_contents: str,
) -> tuple[CompiledPipeline, LoadedSqlTest]:
    pipeline_file_path: Path = write_sql_test_project(
        tmp_path=tmp_path, test_file_contents=test_file_contents
    )
    compiled_pipeline: CompiledPipeline = compile_pipeline(
        loaded_pipeline=load_pipeline_file(pipeline_file_path),
        sql_analyzer=SqlModelAnalyzer(dialect="clickhouse"),
    )
    loaded_test: LoadedSqlTest = discover_sql_tests(root=tmp_path / "tests")[0]
    return compiled_pipeline, loaded_test


def build_single_sql_test_case(*, tmp_path: Path, test_file_contents: str) -> SqlTestCase:
    compiled_pipeline: CompiledPipeline
    loaded_test: LoadedSqlTest
    compiled_pipeline, loaded_test = build_compiled_pipeline_with_tests(
        tmp_path=tmp_path,
        test_file_contents=test_file_contents,
    )
    return build_sql_test_cases(
        loaded_tests=(loaded_test,),
        compiled_pipelines=(compiled_pipeline,),
        reference_rewriter=SqlReferenceRewriter(dialect="clickhouse"),
        comparison_renderer=ClickHouseAdapter().render_set_difference_comparison,
        dialect="clickhouse",
    )[0]


CYCLIC_MODEL_SQL_BY_NAME: tuple[tuple[str, str], ...] = (
    (
        "loop_a",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT CAST(order_id AS String) AS order_id FROM __ref("loop_b")
        """,
    ),
    (
        "loop_b",
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT CAST(order_id AS String) AS order_id FROM __ref("loop_a")
        """,
    ),
)


def build_cyclic_sql_test_case(*, tmp_path: Path, test_file_contents: str) -> SqlTestCase:
    pipeline_dir: Path = tmp_path / "pipelines" / "order_events"
    write_project_configuration_and_source(project_dir=tmp_path)
    write_pipeline_file(pipeline_dir / "pipeline.yml", "source: orders")
    model_name: str
    model_sql: str
    for model_name, model_sql in CYCLIC_MODEL_SQL_BY_NAME:
        write_pipeline_file(pipeline_dir / f"{model_name}.sql", model_sql)
    write_sql_test_file(tmp_path / "tests" / "order_events" / "test_case.sql", test_file_contents)
    compiled_pipeline: CompiledPipeline = compile_pipeline(
        loaded_pipeline=load_pipeline_file(pipeline_dir / "pipeline.yml"),
        sql_analyzer=SqlModelAnalyzer(dialect="clickhouse"),
    )
    loaded_test: LoadedSqlTest = discover_sql_tests(root=tmp_path / "tests")[0]
    return build_sql_test_cases(
        loaded_tests=(loaded_test,),
        compiled_pipelines=(compiled_pipeline,),
        reference_rewriter=SqlReferenceRewriter(dialect="clickhouse"),
        comparison_renderer=ClickHouseAdapter().render_set_difference_comparison,
        dialect="clickhouse",
    )[0]
