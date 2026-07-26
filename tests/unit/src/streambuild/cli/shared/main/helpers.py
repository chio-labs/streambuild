from __future__ import annotations

from pathlib import Path

from streambuild.compiler.compile.main import compile_pipeline
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.discovery.main import discover_pipelines
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.spec.models.pipeline import Pipeline
from streambuild.spec.models.steps import (
    ExternalTableSourceStep,
    ReplayBoundary,
    ReplayBoundaryColumns,
    TransformStep,
)
from streambuild.spec.models.types import ReplayBoundaryMode, ReplayLineageMode, SourceKind

SELECTOR_PIPELINES_ROOT: Path = Path("tests/fixtures/selector_project/pipelines")


def compile_selector_project_pipelines() -> tuple[CompiledPipeline, ...]:
    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(SELECTOR_PIPELINES_ROOT)
    return tuple(compile_pipeline(loaded_pipeline) for loaded_pipeline in loaded_pipelines)


def build_compiled_external_source_pipeline() -> CompiledPipeline:
    pipeline: Pipeline = Pipeline(
        name="orders_pipeline",
        source=ExternalTableSourceStep(
            name="orders",
            kind=SourceKind.KAFKA,
            table_name="orders_existing",
            replay_boundary=ReplayBoundary(
                mode=ReplayBoundaryMode.OFFSETS,
                columns=ReplayBoundaryColumns(
                    partition="event_partition",
                    offset="event_offset",
                    timestamp="event_timestamp",
                ),
            ),
        ),
        transforms=[
            TransformStep(
                name="orders_enriched",
                source="orders",
                engine="MergeTree()",
                order_by=["order_id"],
                query=(
                    "SELECT CAST(order_id AS UInt64) AS order_id, "
                    "CAST(_replay_offset AS UInt64) AS _replay_offset "
                    'FROM __ref("orders")'
                ),
            )
        ],
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
    )
    return compile_pipeline(
        LoadedPipeline(
            pipeline=pipeline,
            file_path=Path("tests/fixtures/selector_project/pipelines/orders/pipeline.yml"),
            project=None,
        )
    )
