from pathlib import Path
from typing import cast

import pytest

from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.main._discover_pipelines import discover_pipelines
from streambuild.compiler.discovery.models import KafkaLandingStep, LoadedPipeline
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_pipeline_file,
)
from tests.unit.src.streambuild.compiler.discovery._test_types import (
    DiscoverPipelinesErrorTestCase,
    DiscoverPipelinesTestCase,
    PipelineSourceInferenceErrorTestCase,
    PipelineSourceInferenceTestCase,
    ViewPipelineSourceInferenceTestCase,
)
from tests.unit.src.streambuild.compiler.discovery.helpers import (
    write_project_toml,
    write_source_yml,
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
        PipelineSourceInferenceTestCase(
            description="infers one source through a model in another pipeline",
            project_files={
                "alpha/alpha_model.sql": """
                MODEL (order_by ["order_id"]);
                SELECT order_id::UInt64 AS order_id FROM __ref("orders")
                """,
                "alpha/bridge_model.sql": """
                MODEL (order_by ["order_id"]);
                SELECT order_id::UInt64 AS order_id FROM __ref("alpha_model")
                """,
                "beta/beta_model.sql": """
                MODEL (order_by ["order_id"]);
                SELECT order_id::UInt64 AS order_id FROM __ref("bridge_model")
                """,
            },
            source_contents="""
            sources:
              - name: orders
                kind: kafka
                broker_list: kafka:9092
                topic: source.orders
                replay_boundary: {mode: offsets}
            """,
            expected_pipeline_sources=(("alpha", "orders"), ("beta", "orders")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_transitive_driving_inputs_when_discovering_then_infers_pipeline_sources(
    test_case: PipelineSourceInferenceTestCase,
    tmp_path: Path,
) -> None:
    pipelines_root: Path = tmp_path / "pipelines"
    relative_path: str
    file_contents: str
    for relative_path, file_contents in test_case.project_files.items():
        write_pipeline_file(pipelines_root / relative_path, file_contents)
    write_project_toml(
        project_dir=tmp_path,
        contents='name = "test"\ndefault_target = "test"\n[targets.test]\n',
    )
    write_source_yml(
        project_dir=tmp_path,
        relative_path="sources.yml",
        contents=test_case.source_contents,
    )

    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)

    assert (
        tuple(
            (loaded.pipeline.name, cast(KafkaLandingStep, loaded.pipeline.source).name)
            for loaded in loaded_pipelines
        )
        == test_case.expected_pipeline_sources
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ViewPipelineSourceInferenceTestCase(
            description="ignores view upstreams when inferring a mixed pipeline source",
            project_files={
                "mixed/table_model.sql": (
                    'MODEL (); SELECT order_id::UInt64 AS order_id FROM __source("orders")'
                ),
                "mixed/terminal.sql": (
                    "MODEL (kind view); SELECT payment_id::UInt64 AS payment_id FROM "
                    '__source("payments")'
                ),
            },
            source_contents="""
            sources:
              - name: orders
                kind: kafka
                broker_list: kafka:9092
                topic: source.orders
                replay_boundary: {mode: offsets}
              - name: payments
                kind: kafka
                broker_list: kafka:9092
                topic: source.payments
                replay_boundary: {mode: offsets}
            """,
            expected_pipeline_sources=(("mixed", "orders"),),
        ),
        ViewPipelineSourceInferenceTestCase(
            description="accepts a source-less view-only pipeline",
            project_files={
                "views/terminal.sql": (
                    "MODEL (kind view); SELECT order_id::UInt64 AS order_id FROM "
                    '__source("orders") JOIN __source("payments") ON 1 = 1'
                ),
            },
            source_contents="""
            sources:
              - name: orders
                kind: kafka
                broker_list: kafka:9092
                topic: source.orders
                replay_boundary: {mode: offsets}
              - name: payments
                kind: kafka
                broker_list: kafka:9092
                topic: source.payments
                replay_boundary: {mode: offsets}
            """,
            expected_pipeline_sources=(("views", None),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_views_when_discovering_then_ignores_them_for_pipeline_source_inference(
    test_case: ViewPipelineSourceInferenceTestCase,
    tmp_path: Path,
) -> None:
    pipelines_root: Path = tmp_path / "pipelines"
    relative_path: str
    file_contents: str
    for relative_path, file_contents in test_case.project_files.items():
        write_pipeline_file(pipelines_root / relative_path, file_contents)
    write_project_toml(
        project_dir=tmp_path,
        contents='name = "test"\ndefault_target = "test"\n[targets.test]\n',
    )
    write_source_yml(
        project_dir=tmp_path,
        relative_path="sources.yml",
        contents=test_case.source_contents,
    )

    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)

    assert (
        tuple(
            (loaded.pipeline.name, getattr(loaded.pipeline.source, "name", None))
            for loaded in loaded_pipelines
        )
        == test_case.expected_pipeline_sources
    )


@pytest.mark.parametrize(
    "test_case",
    [
        PipelineSourceInferenceErrorTestCase(
            description="rejects a pipeline whose models resolve to multiple sources",
            project_files={
                "mixed/orders_model.sql": """
                MODEL (order_by ["order_id"]);
                SELECT order_id::UInt64 AS order_id FROM __ref("orders")
                """,
                "mixed/payments_model.sql": """
                MODEL (order_by ["payment_id"]);
                SELECT payment_id::UInt64 AS payment_id FROM __ref("payments")
                """,
            },
            source_contents="""
            sources:
              - name: orders
                kind: kafka
                broker_list: kafka:9092
                topic: source.orders
                replay_boundary: {mode: offsets}
              - name: payments
                kind: kafka
                broker_list: kafka:9092
                topic: source.payments
                replay_boundary: {mode: offsets}
            """,
            expected_error_fragment="must resolve to exactly one source; found orders, payments",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multiple_source_roots_when_discovering_then_rejects_pipeline(
    test_case: PipelineSourceInferenceErrorTestCase,
    tmp_path: Path,
) -> None:
    pipelines_root: Path = tmp_path / "pipelines"
    relative_path: str
    file_contents: str
    for relative_path, file_contents in test_case.project_files.items():
        write_pipeline_file(pipelines_root / relative_path, file_contents)
    write_project_toml(
        project_dir=tmp_path,
        contents='name = "test"\ndefault_target = "test"\n[targets.test]\n',
    )
    write_source_yml(
        project_dir=tmp_path,
        relative_path="sources.yml",
        contents=test_case.source_contents,
    )

    with pytest.raises(PipelineDiscoveryError, match=test_case.expected_error_fragment):
        discover_pipelines(pipelines_root)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoverPipelinesErrorTestCase(
            description="raises value error when two pipelines define the same model name",
            project_files={
                "alpha/shared.sql": """
                MODEL (
                  engine "MergeTree()",
                  order_by ["order_id"],
                );

                SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
                """,
                "beta/shared.sql": """
                MODEL (
                  engine "MergeTree()",
                  order_by ["order_id"],
                );

                SELECT CAST(order_id AS UInt64) AS order_id FROM __ref("orders")
                """,
            },
            expected_error_type=ValueError,
            expected_error_fragment="Logical node name 'shared' is defined in both",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_duplicate_logical_names_when_discovering_then_it_raises_expected_error(
    test_case: DiscoverPipelinesErrorTestCase,
    tmp_path: Path,
) -> None:
    pipelines_root: Path = tmp_path / "pipelines"
    for relative_path, file_contents in test_case.project_files.items():
        write_pipeline_file(pipelines_root / relative_path, file_contents)
    write_project_toml(
        project_dir=tmp_path,
        contents='name = "test"\ndefault_target = "test"\n[targets.test]\n',
    )
    write_source_yml(
        project_dir=tmp_path,
        relative_path="sources.yml",
        contents="""
        sources:
          - name: orders
            kind: kafka
            broker_list: kafka:9092
            topic: source.orders
            replay_boundary: {mode: offsets}
        """,
    )

    with pytest.raises(test_case.expected_error_type, match=test_case.expected_error_fragment):
        discover_pipelines(pipelines_root)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
