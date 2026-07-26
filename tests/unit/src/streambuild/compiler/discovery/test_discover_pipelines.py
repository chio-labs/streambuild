from pathlib import Path

import pytest

from streambuild.compiler.discovery.main.discover_pipelines import discover_pipelines
from streambuild.compiler.shared.models import LoadedPipeline
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
)
from tests.unit.src.streambuild.compiler.discovery._test_types import (
    DiscoverPipelinesErrorTestCase,
    DiscoverPipelinesTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverPipelinesTestCase(
            description="finds example pipeline under pipelines root",
            pipelines_root=Path("tests/fixtures/basic_project/pipelines"),
            expected_pipeline_names=["orders"],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_pipeline_root_when_discovering_pipelines_then_returns_loaded_pipelines(
    test_case: DiscoverPipelinesTestCase,
) -> None:
    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(test_case.pipelines_root)

    assert [
        pipeline.pipeline.name for pipeline in loaded_pipelines
    ] == test_case.expected_pipeline_names


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverPipelinesErrorTestCase(
            description=(
                "raises value error when two pipeline roots define the same source logical name"
            ),
            pipeline_files={
                "alpha/pipeline.yml": """
                source:
                  kind: kafka
                  name: orders
                  broker_list: kafka-alpha:9092
                  topic: source.alpha.orders
                """,
                "alpha/orders_enriched.sql": """
                MODEL (
                  engine: "MergeTree()",
                  order_by: ["order_id"],
                );

                SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
                """,
                "beta/pipeline.yml": """
                source:
                  kind: kafka
                  name: orders
                  broker_list: kafka-beta:9092
                  topic: source.beta.orders
                """,
                "beta/orders_snapshot.sql": """
                MODEL (
                  engine: "MergeTree()",
                  order_by: ["order_id"],
                );

                SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
                """,
            },
            expected_error_type=ValueError,
            expected_error_fragment="Logical node name 'orders' is defined in both",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duplicate_logical_names_when_discovering_then_it_raises_expected_error(
    test_case: DiscoverPipelinesErrorTestCase,
    tmp_path: Path,
) -> None:
    pipelines_root: Path = tmp_path / "pipelines"
    for relative_path, file_contents in test_case.pipeline_files.items():
        write_pipeline_file(pipelines_root / relative_path, file_contents)

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        discover_pipelines(pipelines_root)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
