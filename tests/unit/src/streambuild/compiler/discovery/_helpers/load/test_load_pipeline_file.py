from pathlib import Path

import pytest

from streambuild.compiler.discovery._helpers.load import load_pipeline_file
from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.models import LoadedPipeline, ReplayOnChangePolicy
from streambuild.compiler.discovery.types import BoundedReplayFallback, ReplayOnChangeMode
from tests.unit.src.streambuild.compiler.discovery._helpers.load._test_types import (
    LoadRegistryPipelineTestCase,
    LoadReplayPoliciesTestCase,
    MismatchedSourceTestCase,
    RemovedPipelineSurfaceTestCase,
)
from tests.unit.src.streambuild.compiler.discovery._helpers.load.helpers import (
    write_registry_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LoadRegistryPipelineTestCase(
            description="resolves the registered source and discovered models",
            expected_pipeline_name="orders",
            expected_source_name="orders",
            expected_transform_names=("orders_enriched",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_registry_project_when_loading_pipeline_then_it_resolves_source(
    test_case: LoadRegistryPipelineTestCase,
) -> None:
    loaded: LoadedPipeline = load_pipeline_file(
        Path("tests/fixtures/basic_project/pipelines/orders/pipeline.yml")
    )

    assert loaded.pipeline.name == test_case.expected_pipeline_name
    assert loaded.pipeline.source.name == test_case.expected_source_name
    assert (
        tuple(transform.name for transform in loaded.pipeline.transforms)
        == test_case.expected_transform_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        LoadReplayPoliciesTestCase(
            description="parses pipeline and model policy with renamed values",
            expected_pipeline_breaking_mode=ReplayOnChangeMode.BOUNDED,
            expected_pipeline_breaking_seconds=1800,
            expected_pipeline_non_breaking_mode=ReplayOnChangeMode.FULL,
            expected_pipeline_fallback=BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
            expected_model_breaking_seconds=8,
            expected_model_fallback=BoundedReplayFallback.FULL,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_replay_policies_when_loading_then_it_uses_renamed_values(
    test_case: LoadReplayPoliciesTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = write_registry_project(
        project_dir=tmp_path,
        pipeline_contents="""
        source: orders
        replay_on_change:
          breaking: bounded-30m
          non_breaking: full
        bounded_replay_fallback: bounded_without_history
        """,
        model_contents="""
        MODEL (
          replay_on_change: {breaking: bounded-8s, non_breaking: full},
          bounded_replay_fallback: full,
        );
        SELECT order_id::UInt64 AS order_id FROM __source("orders")
        """,
    )

    loaded: LoadedPipeline = load_pipeline_file(pipeline_file_path)
    pipeline_policy: ReplayOnChangePolicy | None = loaded.pipeline.replay_on_change
    model_policy: ReplayOnChangePolicy | None = loaded.pipeline.transforms[0].replay_on_change

    assert pipeline_policy is not None
    assert pipeline_policy.breaking is not None
    assert pipeline_policy.breaking.mode == test_case.expected_pipeline_breaking_mode
    assert pipeline_policy.breaking.lookback_seconds == test_case.expected_pipeline_breaking_seconds
    assert pipeline_policy.non_breaking is not None
    assert pipeline_policy.non_breaking.mode == test_case.expected_pipeline_non_breaking_mode
    assert loaded.pipeline.bounded_replay_fallback == test_case.expected_pipeline_fallback
    assert model_policy is not None
    assert model_policy.breaking is not None
    assert model_policy.breaking.lookback_seconds == test_case.expected_model_breaking_seconds
    assert (
        loaded.pipeline.transforms[0].bounded_replay_fallback == test_case.expected_model_fallback
    )


@pytest.mark.parametrize(
    "test_case",
    [
        RemovedPipelineSurfaceTestCase(
            description="rejects an embedded source",
            pipeline_contents="source: {name: orders, kind: kafka}",
            expected_error_fragment="source as one non-empty registry name",
        ),
        RemovedPipelineSurfaceTestCase(
            description="rejects an unknown source",
            pipeline_contents="source: missing",
            expected_error_fragment="references unknown source 'missing'",
        ),
        RemovedPipelineSurfaceTestCase(
            description="rejects a pipeline-owned boundary",
            pipeline_contents="source: orders\nreplay_lineage_mode: offsets",
            expected_error_fragment="unsupported keys: replay_lineage_mode",
        ),
        RemovedPipelineSurfaceTestCase(
            description="rejects the old policy key",
            pipeline_contents="source: orders\nschema_change_backfill: {breaking: full}",
            expected_error_fragment="unsupported keys: schema_change_backfill",
        ),
        RemovedPipelineSurfaceTestCase(
            description="rejects the old bounded value",
            pipeline_contents="source: orders\nreplay_on_change: {breaking: bounded(1h)}",
            expected_error_fragment="'full' or 'bounded-<duration>'",
        ),
        RemovedPipelineSurfaceTestCase(
            description="rejects the old fallback value",
            pipeline_contents="source: orders\nbounded_replay_fallback: full_refresh",
            expected_error_fragment="expected 'full' or 'bounded_without_history'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_removed_pipeline_surface_when_loading_then_it_fails_with_source_diagnostic(
    test_case: RemovedPipelineSurfaceTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = write_registry_project(
        project_dir=tmp_path,
        pipeline_contents=test_case.pipeline_contents,
        model_contents="""
        MODEL ();
        SELECT order_id::UInt64 AS order_id FROM __source("orders")
        """,
    )

    with pytest.raises(PipelineDiscoveryError) as error_info:
        load_pipeline_file(pipeline_file_path)

    assert test_case.expected_error_fragment in str(error_info.value)
    assert str(pipeline_file_path) in str(error_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        MismatchedSourceTestCase(
            description="rejects a model driving from another source",
            model_source_name="customers",
            expected_error_fragment="selects source 'orders'.*'customers'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_wrong_model_source_when_loading_then_it_fails(
    test_case: MismatchedSourceTestCase,
    tmp_path: Path,
) -> None:
    pipeline_file_path: Path = write_registry_project(
        project_dir=tmp_path,
        pipeline_contents="source: orders",
        model_contents=(
            "MODEL ();\n"
            f'SELECT order_id::UInt64 AS order_id FROM __source("{test_case.model_source_name}")'
        ),
    )

    with pytest.raises(PipelineDiscoveryError, match=test_case.expected_error_fragment):
        load_pipeline_file(pipeline_file_path)
