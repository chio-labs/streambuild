"""CLI command for pipeline compilation."""

import json
import sys
from pathlib import Path

from streambuild.adapter.classes.adapter import Adapter
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.compile._helpers.artifacts import (
    format_clickhouse_sql,
    write_text,
)
from streambuild.cli.compile._helpers.manifest import (
    pipeline_manifest_entry,
)
from streambuild.compiler.audit_discovery.main.discover_sql_audits import discover_sql_audits
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.auditing.main.validated_sql_audits import validated_sql_audits
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    CompiledManagedSource,
    CompiledPipeline,
    CompiledTransformStep,
)
from streambuild.compiler.discovery.main.discover_pipelines import discover_pipelines
from streambuild.compiler.discovery.models import LoadedPipeline
from streambuild.compiler.planner.main.build_adapter_resource import build_adapter_resource
from streambuild.compiler.test_discovery.main.discover_sql_tests import discover_sql_tests
from streambuild.compiler.testing.main.build_sql_test_cases import build_sql_test_cases


def run_compile(*, pipelines_root: Path, target_dir: Path | None = None) -> int:
    """Compile discovered pipeline folders and write artifact outputs."""

    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(pipelines_root)
    adapter: Adapter = ClickHouseAdapter()

    try:
        compiled: list[CompiledPipeline] = [
            compile_pipeline(pipeline) for pipeline in loaded_pipelines
        ]
        loaded_tests: tuple[object, ...] = tuple(
            discover_sql_tests(pipelines_root.parent / "tests")
        )
        loaded_audits: tuple[LoadedSqlAudit, ...] = tuple(
            discover_sql_audits(pipelines_root.parent / "audits")
        )
        _ = build_sql_test_cases(
            loaded_tests=loaded_tests,
            compiled_pipelines=tuple(compiled),
        )
        _ = validated_sql_audits(
            loaded_audits=loaded_audits,
            compiled_pipelines=tuple(compiled),
        )
    except TransformSqlContractError as error:
        print(str(error), file=sys.stderr)
        return 1

    resolved_target_dir: Path = target_dir or (pipelines_root.parent / "target")
    compiled_pipeline: CompiledPipeline
    for compiled_pipeline in compiled:
        _write_pipeline_artifacts(
            adapter=adapter,
            compiled_pipeline=compiled_pipeline,
            target_dir=resolved_target_dir,
        )
    _write_manifest(compiled=compiled, target_dir=resolved_target_dir)

    print(
        f"Wrote compile artifacts to {resolved_target_dir}\n"
        f"Pipelines: {len(compiled)}\n"
        f"Models: {sum(len(item.transforms) for item in compiled)}"
    )
    return 0


def _write_pipeline_artifacts(
    *, adapter: Adapter, compiled_pipeline: CompiledPipeline, target_dir: Path
) -> None:
    pipeline_dir: Path = target_dir / compiled_pipeline.pipeline.name
    compile_models_dir: Path = pipeline_dir / "compile" / "models"
    run_models_dir: Path = pipeline_dir / "run" / "models"
    run_workflow_dir: Path = pipeline_dir / "run" / "workflow"
    resolved_database: str = (
        compiled_pipeline.project.default_database
        if compiled_pipeline.project is not None
        and compiled_pipeline.project.default_database is not None
        else "default"
    )
    compile_models_dir.mkdir(parents=True, exist_ok=True)
    run_models_dir.mkdir(parents=True, exist_ok=True)
    run_workflow_dir.mkdir(parents=True, exist_ok=True)

    transform: CompiledTransformStep
    for transform in compiled_pipeline.transforms:
        write_text(
            path=compile_models_dir / f"{transform.transform.name}.sql",
            contents=format_clickhouse_sql(transform.resolved_query) + "\n",
        )
        write_text(
            path=run_models_dir / f"{transform.transform.name}.table.sql",
            contents=format_clickhouse_sql(
                adapter.render_resource(
                    resource=build_adapter_resource(transform.target_table),
                    database=resolved_database,
                )
            )
            + "\n",
        )
        write_text(
            path=run_models_dir / f"{transform.transform.name}.mv.sql",
            contents=format_clickhouse_sql(
                adapter.render_resource(
                    resource=build_adapter_resource(transform.materialized_view),
                    database=resolved_database,
                )
            )
            + "\n",
        )

    workflow_entries: list[tuple[str, str]] = []
    if isinstance(compiled_pipeline.source, CompiledManagedSource):
        workflow_entries.extend(
            [
                (
                    "01_kafka_table.sql",
                    format_clickhouse_sql(
                        adapter.render_resource(
                            resource=build_adapter_resource(compiled_pipeline.source.kafka_table),
                            database=resolved_database,
                        )
                    )
                    + "\n",
                ),
                (
                    "02_raw_table.sql",
                    format_clickhouse_sql(
                        adapter.render_resource(
                            resource=build_adapter_resource(compiled_pipeline.source.raw_table),
                            database=resolved_database,
                        )
                    )
                    + "\n",
                ),
                (
                    "03_landing_mv.sql",
                    format_clickhouse_sql(
                        adapter.render_resource(
                            resource=build_adapter_resource(
                                compiled_pipeline.source.materialized_view
                            ),
                            database=resolved_database,
                        )
                    )
                    + "\n",
                ),
            ]
        )
    for index, transform in enumerate(compiled_pipeline.transforms, start=1):
        workflow_entries.extend(
            [
                (
                    f"{index * 10:02d}_{transform.transform.name}.table.sql",
                    format_clickhouse_sql(
                        adapter.render_resource(
                            resource=build_adapter_resource(transform.target_table),
                            database=resolved_database,
                        )
                    )
                    + "\n",
                ),
                (
                    f"{index * 10 + 1:02d}_{transform.transform.name}.mv.sql",
                    format_clickhouse_sql(
                        adapter.render_resource(
                            resource=build_adapter_resource(transform.materialized_view),
                            database=resolved_database,
                        )
                    )
                    + "\n",
                ),
            ]
        )
    file_name: str
    contents: str
    for file_name, contents in workflow_entries:
        write_text(path=run_workflow_dir / file_name, contents=contents)

    workflow_sql: str = "\n".join(
        f"-- {file_name}\n{contents.rstrip()}" for file_name, contents in workflow_entries
    )
    write_text(path=run_workflow_dir / "workflow.sql", contents=workflow_sql + "\n")
    workflow_json: str = json.dumps(
        {
            "pipeline": compiled_pipeline.pipeline.name,
            "steps": [{"file": file_name} for file_name, _contents in workflow_entries],
        },
        indent=2,
    )
    write_text(path=run_workflow_dir / "workflow.json", contents=workflow_json + "\n")


def _write_manifest(*, compiled: list[CompiledPipeline], target_dir: Path) -> None:
    manifest_payload: dict[str, object] = {
        "metadata": {
            "manifest_version": 1,
            "tool": "streambuild",
        },
        "pipelines": {
            compiled_pipeline.pipeline.name: pipeline_manifest_entry(
                compiled_pipeline=compiled_pipeline, target_dir=target_dir
            )
            for compiled_pipeline in compiled
        },
    }
    write_text(
        path=target_dir / "manifest.json", contents=json.dumps(manifest_payload, indent=2) + "\n"
    )
