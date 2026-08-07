from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.cli.plan.main._run_plan import run_plan
from streambuild.cli.plan.models import PlanCommandOptions
from streambuild.compiler.compile.main._compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    CompiledPipeline,
    CompiledProject,
    CompiledSource,
    CompilerAdapterProfile,
)
from streambuild.compiler.discovery.main._discover_pipelines import discover_pipelines
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import (
    ExternalTableSourceStep,
    LoadedPipeline,
    Pipeline,
    ReplayBoundary,
    ReplayBoundaryColumns,
    TransformStep,
)
from streambuild.compiler.discovery.types import ReplayBoundaryMode, SourceKind
from streambuild.compiler.pipeline.main._realize_project import realize_project
from streambuild.compiler.pipeline.models import RealizedProject
from streambuild.compiler.planner.models import DirectWarehouseSnapshot
from streambuild.compiler.sql_analysis.classes.sql_model_analyzer import SqlModelAnalyzer
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.compiler.compile.helpers import build_realization_analyzer
from tests.unit.src.streambuild.compiler.planner.helpers import build_settled_direct_snapshot

SELECTOR_PIPELINES_ROOT: Path = Path("tests/fixtures/selector_project/pipelines")


def compile_selector_project_pipelines() -> tuple[CompiledPipeline, ...]:
    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(SELECTOR_PIPELINES_ROOT)
    sql_analyzer: SqlModelAnalyzer = SqlModelAnalyzer(dialect="clickhouse")
    return tuple(
        compile_pipeline(loaded_pipeline=loaded_pipeline, sql_analyzer=sql_analyzer)
        for loaded_pipeline in loaded_pipelines
    )


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
    )
    return compile_pipeline(
        loaded_pipeline=LoadedPipeline(
            pipeline=pipeline,
            file_path=Path("tests/fixtures/selector_project/pipelines/orders"),
            project=None,
        ),
        sql_analyzer=SqlModelAnalyzer(dialect="clickhouse"),
    )


def build_realized_external_source_project() -> RealizedProject:
    compiled_pipeline: CompiledPipeline = build_compiled_external_source_pipeline()
    compiled_project: CompiledProject = CompiledProject(
        sources=(cast(CompiledSource, compiled_pipeline.source),),
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
        sql_analyzer=build_realization_analyzer(compiled_project),
    )


def run_scope_project_plan(
    *,
    project_root: Path,
    json_output: bool,
    selectors: tuple[str, ...] = (),
    full_refresh: bool = False,
    start_time: str | None = None,
    virtual_environments: bool = False,
    deployment_id: str | None = None,
) -> int:
    """Run `stb plan` against the direct scope project with a settled warehouse."""

    snapshot: DirectWarehouseSnapshot = build_settled_direct_snapshot()
    snapshot = replace(
        snapshot,
        catalog=replace(
            snapshot.catalog,
            relations=snapshot.catalog.relations[3:],
        ),
    )
    return run_plan(
        options=PlanCommandOptions(
            pipelines_root=project_root / "pipelines",
            database=None,
            selectors=selectors,
            full_refresh=full_refresh,
            start_time=start_time,
            deployment_id=deployment_id,
            json_output=json_output,
            verbose=False,
        ),
        client=RecordingAdapterConnection(
            relations={
                False: snapshot.catalog.relations,
                True: (),
            }[virtual_environments],
        ),
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )


def read_workflow_artifact(
    *, artifact_root: Path, is_template: bool = False
) -> tuple[bytes, bytes, tuple[str, ...], tuple[bytes, ...]]:
    """Read one complete workflow artifact without interpreting its contents."""

    step_pattern: str = {False: "*.sql", True: "*.sql.template"}[is_template]
    workflow_name: str = {
        False: "workflow.sql",
        True: "workflow.template.sql",
    }[is_template]
    step_paths: tuple[Path, ...] = tuple(sorted((artifact_root / "steps").glob(step_pattern)))
    return (
        (artifact_root / "plan.json").read_bytes(),
        (artifact_root / workflow_name).read_bytes(),
        tuple(path.name for path in step_paths),
        tuple(path.read_bytes() for path in step_paths),
    )


def fail_second_workflow_artifact_replace(
    *, monkeypatch: pytest.MonkeyPatch, error_message: str
) -> None:
    """Fail staged publication after the previous complete artifact has moved."""

    original_replace: Callable[[Path, Path], None] = os.replace

    def fail_replace(_source: Path, _target: Path) -> None:
        raise OSError(error_message)

    replacements: Iterator[Callable[[Path, Path], None]] = iter(
        (original_replace, fail_replace, original_replace)
    )

    def staged_replace(source: Path, target: Path) -> None:
        next(replacements)(source, target)

    monkeypatch.setattr(
        "streambuild.cli.workflow_artifacts._helpers.build_publication.os.replace",
        staged_replace,
    )
