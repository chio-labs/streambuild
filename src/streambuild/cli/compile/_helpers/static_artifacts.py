"""Build one complete deterministic static compile target in memory."""

from pathlib import Path

from streambuild.adapter.models import AdapterManagedSource, AdapterMaterializedView, AdapterTable
from streambuild.cli.compile._helpers.content import (
    normalized_sql,
    static_test_sql,
    workflow_json,
    workflow_sql,
)
from streambuild.cli.compile._helpers.manifest import build_manifest_json
from streambuild.cli.compile._helpers.paths import (
    audit_path,
    model_query_path,
    model_table_path,
    model_view_path,
    source_resource_path,
    static_test_path,
    workflow_json_path,
    workflow_sql_path,
    workflow_step_path,
)
from streambuild.cli.compile._helpers.redaction import redacted_managed_source
from streambuild.cli.compile.exceptions import CompileArtifactError
from streambuild.cli.compile.models import StaticArtifactFile, StaticCompileArtifacts
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledPipeline,
    CompiledSource,
    LogicalResourceKey,
)
from streambuild.compiler.dag.main.build_dag_json import build_dag_json
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.pipeline.types import AdapterResource
from streambuild.compiler.testing.models import SqlTestCase


def build_static_compile_artifacts(*, analysis: CompileAnalysis) -> StaticCompileArtifacts:
    """Build all static files before any target path is changed."""

    rendered_by_key: dict[LogicalResourceKey, tuple[tuple[AdapterResource, str], ...]] = (
        _rendered_resources_by_logical_key(analysis=analysis)
    )
    compiled_files: list[StaticArtifactFile] = []
    compiled_files.extend(
        _source_resource_files(analysis=analysis, rendered_by_key=rendered_by_key)
    )
    compiled_files.extend(_model_files(analysis=analysis, rendered_by_key=rendered_by_key))
    compiled_files.extend(_workflow_files(analysis=analysis, rendered_by_key=rendered_by_key))
    compiled_files.extend(_audit_and_test_files(analysis=analysis))
    ordered_files: tuple[StaticArtifactFile, ...] = tuple(
        sorted(compiled_files, key=lambda file: file.relative_path.as_posix())
    )
    _validate_unique_paths(files=ordered_files)
    return StaticCompileArtifacts(
        compiled_files=ordered_files,
        manifest_json=build_manifest_json(analysis=analysis, compiled_files=ordered_files),
        dag_json=build_dag_json(
            graph=analysis.graph,
            macro_registry=analysis.compile_inputs.macro_registry,
        ),
    )


def _rendered_resources_by_logical_key(
    *, analysis: CompileAnalysis
) -> dict[LogicalResourceKey, tuple[tuple[AdapterResource, str], ...]]:
    database_by_key: dict[LogicalResourceKey, str] = {}
    pipeline: CompiledPipeline
    for pipeline in analysis.compiled_project.pipelines:
        database: str = _pipeline_database(analysis=analysis, pipeline=pipeline)
        database_by_key.setdefault(pipeline.source.key, database)
        model: CompiledModel
        for model in pipeline.models:
            database_by_key[model.key] = database
    rendered_by_key: dict[LogicalResourceKey, tuple[tuple[AdapterResource, str], ...]] = {}
    logical_key: LogicalResourceKey
    resources: tuple[AdapterResource, ...]
    for logical_key, resources in analysis.realized_project.resources_by_logical_key.items():
        database = database_by_key[logical_key]
        rendered_by_key[logical_key] = tuple(
            (
                resource,
                normalized_sql(
                    analysis.adapter_profile.render_resource(
                        resource=(
                            redacted_managed_source(resource)
                            if isinstance(resource, AdapterManagedSource)
                            else resource
                        ),
                        database=database,
                    )
                ),
            )
            for resource in resources
        )
    return rendered_by_key


def _source_resource_files(
    *,
    analysis: CompileAnalysis,
    rendered_by_key: dict[LogicalResourceKey, tuple[tuple[AdapterResource, str], ...]],
) -> list[StaticArtifactFile]:
    files: list[StaticArtifactFile] = []
    source: CompiledSource
    for source in analysis.compiled_project.sources:
        resource: AdapterResource
        sql: str
        for resource, sql in rendered_by_key[source.key]:
            files.append(
                StaticArtifactFile(
                    relative_path=source_resource_path(
                        source_name=source.key.name,
                        resource_name=resource.name,
                    ),
                    contents=sql,
                )
            )
    return files


def _model_files(
    *,
    analysis: CompileAnalysis,
    rendered_by_key: dict[LogicalResourceKey, tuple[tuple[AdapterResource, str], ...]],
) -> list[StaticArtifactFile]:
    files: list[StaticArtifactFile] = []
    model: CompiledModel
    for model in analysis.compiled_project.models:
        files.append(
            StaticArtifactFile(
                relative_path=model_query_path(
                    pipeline_name=model.pipeline_name,
                    model_name=model.key.name,
                ),
                contents=normalized_sql(
                    analysis.realized_project.resolved_query_by_model_key[model.key]
                ),
            )
        )
        resource: AdapterResource
        sql: str
        for resource, sql in rendered_by_key[model.key]:
            files.append(
                StaticArtifactFile(
                    relative_path=_model_resource_path(model=model, resource=resource),
                    contents=sql,
                )
            )
    return files


def _workflow_files(
    *,
    analysis: CompileAnalysis,
    rendered_by_key: dict[LogicalResourceKey, tuple[tuple[AdapterResource, str], ...]],
) -> list[StaticArtifactFile]:
    files: list[StaticArtifactFile] = []
    pipeline: CompiledPipeline
    for pipeline in analysis.compiled_project.pipelines:
        model_by_key: dict[LogicalResourceKey, CompiledModel] = {
            model.key: model for model in pipeline.models
        }
        ordered_models: tuple[CompiledModel, ...] = tuple(
            model_by_key[key] for key in analysis.graph.ordered_keys if key in model_by_key
        )
        entries: tuple[tuple[str, str], ...] = _workflow_entries(
            pipeline=pipeline,
            ordered_models=ordered_models,
            rendered_by_key=rendered_by_key,
        )
        files.extend(
            StaticArtifactFile(
                relative_path=workflow_step_path(
                    pipeline_name=pipeline.pipeline.name,
                    step_name=file_name,
                ),
                contents=contents,
            )
            for file_name, contents in entries
        )
        files.append(
            StaticArtifactFile(
                relative_path=workflow_sql_path(pipeline_name=pipeline.pipeline.name),
                contents=workflow_sql(entries=entries),
            )
        )
        files.append(
            StaticArtifactFile(
                relative_path=workflow_json_path(pipeline_name=pipeline.pipeline.name),
                contents=workflow_json(
                    pipeline_name=pipeline.pipeline.name,
                    entries=entries,
                ),
            )
        )
    return files


def _audit_and_test_files(*, analysis: CompileAnalysis) -> list[StaticArtifactFile]:
    files: list[StaticArtifactFile] = []
    audit: LoadedSqlAudit
    for audit in analysis.compiled_project.audits:
        files.append(
            StaticArtifactFile(
                relative_path=audit_path(
                    audit=audit,
                    project_dir=analysis.discovered_inputs.project_dir,
                ),
                contents=normalized_sql(audit.query),
            )
        )
    test_case: SqlTestCase
    for test_case in analysis.compiled_project.test_cases:
        files.append(
            StaticArtifactFile(
                relative_path=static_test_path(test_case=test_case),
                contents=static_test_sql(test_case=test_case),
            )
        )
    return files


def _workflow_entries(
    *,
    pipeline: CompiledPipeline,
    ordered_models: tuple[CompiledModel, ...],
    rendered_by_key: dict[LogicalResourceKey, tuple[tuple[AdapterResource, str], ...]],
) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    source_index: int
    source_resource: AdapterResource
    source_sql: str
    for source_index, (source_resource, source_sql) in enumerate(
        rendered_by_key[pipeline.source.key], start=1
    ):
        entries.append(
            (f"{source_index:04d}_{_resource_step_name(source_resource)}.sql", source_sql)
        )
    model_index: int
    model: CompiledModel
    for model_index, model in enumerate(ordered_models, start=1):
        resource: AdapterResource
        sql: str
        for resource, sql in rendered_by_key[model.key]:
            step_number: int = model_index * 10 + int(isinstance(resource, AdapterMaterializedView))
            entries.append(
                (f"{step_number:04d}_{model.key.name}.{_resource_suffix(resource)}.sql", sql)
            )
    return tuple(entries)


def _model_resource_path(*, model: CompiledModel, resource: AdapterResource) -> Path:
    if isinstance(resource, AdapterTable):
        return model_table_path(pipeline_name=model.pipeline_name, model_name=model.key.name)
    return model_view_path(pipeline_name=model.pipeline_name, model_name=model.key.name)


def _resource_step_name(resource: AdapterResource) -> str:
    if isinstance(resource, AdapterManagedSource):
        return "kafka_table"
    if isinstance(resource, AdapterTable):
        return "raw_table"
    return "landing_mv"


def _resource_suffix(resource: AdapterResource) -> str:
    return "table" if isinstance(resource, AdapterTable) else "mv"


def _pipeline_database(*, analysis: CompileAnalysis, pipeline: CompiledPipeline) -> str:
    if pipeline.project is not None and pipeline.project.default_database is not None:
        return pipeline.project.default_database
    return analysis.compile_inputs.effective_target.default_database or "default"


def _validate_unique_paths(*, files: tuple[StaticArtifactFile, ...]) -> None:
    seen_paths: set[Path] = set()
    file: StaticArtifactFile
    for file in files:
        if file.relative_path in seen_paths:
            raise CompileArtifactError(
                f"Multiple compile artifacts resolve to '{file.relative_path.as_posix()}'"
            )
        seen_paths.add(file.relative_path)
