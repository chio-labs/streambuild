from pathlib import Path

from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.shared.models import LoadedSqlTest
from streambuild.compiler.test_discovery.main.discover_sql_tests import discover_sql_tests
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import write_pipeline_file
from tests.unit.src.streambuild.compiler.test_discovery.helpers import (
    write_sql_test_file,
)


def build_compiled_pipeline_with_tests(
    *,
    tmp_path: Path,
    test_file_contents: str,
) -> tuple[CompiledPipeline, LoadedSqlTest]:
    pipeline_file_path: Path = tmp_path / "pipelines" / "order_events" / "pipeline.yml"
    transform_file_path: Path = tmp_path / "pipelines" / "order_events" / "order_items.sql"
    downstream_file_path: Path = tmp_path / "pipelines" / "order_events" / "daily_revenue.sql"
    test_file_path: Path = tmp_path / "tests" / "order_events" / "test_case.sql"
    write_pipeline_file(
        pipeline_file_path,
        """
        source:
          kind: kafka
          name: orders
          broker_list: kafka:9092
          topic: source.orders
        """,
    )
    write_pipeline_file(
        transform_file_path,
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(quantity * unit_price AS Nullable(Float64)) AS line_total
        FROM __ref("orders")
        """,
    )
    write_pipeline_file(
        downstream_file_path,
        """
        MODEL (
          order_by: ["order_id"]
        );

        SELECT
          CAST(order_id AS String) AS order_id,
          CAST(line_total AS Nullable(Float64)) AS line_total
        FROM __ref("order_items")
        """,
    )
    write_sql_test_file(test_file_path, test_file_contents)
    compiled_pipeline: CompiledPipeline = compile_pipeline(load_pipeline_file(pipeline_file_path))
    loaded_test: LoadedSqlTest = discover_sql_tests(tmp_path / "tests")[0]
    return compiled_pipeline, loaded_test
