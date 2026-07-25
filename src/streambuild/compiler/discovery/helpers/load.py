"""Pipeline and project loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from streambuild.compiler.discovery.helpers.constants import PROJECT_FILE_NAME
from streambuild.compiler.discovery.helpers.model_sql import load_transform_from_sql_file
from streambuild.compiler.shared.models import LoadedPipeline
from streambuild.spec.models.pipeline import Pipeline
from streambuild.spec.models.project import Project, ProjectClickHouseConfig
from streambuild.spec.models.steps import (
    ExternalTableSourceStep,
    KafkaLandingStep,
    KafkaSettings,
    ReplayBoundary,
    ReplayBoundaryColumns,
    TransformStep,
)
from streambuild.spec.models.types import (
    BoundedReplayFallback,
    ReplayBoundaryMode,
    ReplayLineageMode,
    SourceKind,
)


def load_pipeline_file(file_path: Path) -> LoadedPipeline:
    """Load a single pipeline definition file and return its top-level pipeline object."""

    if file_path.name != "pipeline.yml":
        raise ValueError(f"Pipeline file '{file_path}' must be named 'pipeline.yml'")

    pipeline: Pipeline = load_pipeline_yaml(file_path)
    project: Project | None = load_project_for_pipeline_file(file_path)
    return LoadedPipeline(pipeline=pipeline, file_path=file_path, project=project)


def load_pipeline_yaml(file_path: Path) -> Pipeline:
    """Load one authored pipeline folder rooted at `pipeline.yml`."""

    pipeline_values: object = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(pipeline_values, dict) or not all(
        isinstance(key, str) for key in pipeline_values
    ):
        raise ValueError(f"Pipeline file '{file_path}' must define a top-level mapping")
    typed_pipeline_values: dict[str, Any] = pipeline_values

    pipeline_root: Path = file_path.parent
    if "name" in typed_pipeline_values:
        raise ValueError(
            f"Pipeline file '{file_path}' must not define 'name'; pipeline name is inferred "
            f"from folder '{pipeline_root.name}'"
        )
    nested_pipeline_files: list[Path] = sorted(
        nested_file
        for nested_file in pipeline_root.rglob("pipeline.yml")
        if nested_file != file_path
    )
    if nested_pipeline_files:
        nested_file_list: str = ", ".join(str(path) for path in nested_pipeline_files)
        raise ValueError(
            f"Pipeline root '{pipeline_root}' must not contain nested pipeline.yml files: "
            f"{nested_file_list}"
        )

    source: KafkaLandingStep | ExternalTableSourceStep = _load_pipeline_source(
        typed_pipeline_values, file_path
    )
    transforms: list[TransformStep] = _load_pipeline_transforms(pipeline_root)
    replay_lineage_mode_value: object = typed_pipeline_values.get("replay_lineage_mode")
    replay_lineage_mode: ReplayLineageMode | None = None
    if replay_lineage_mode_value is not None:
        try:
            replay_lineage_mode = ReplayLineageMode(replay_lineage_mode_value)
        except ValueError as error:
            raise ValueError(
                f"Pipeline file '{file_path}' has unsupported replay_lineage_mode "
                f"'{replay_lineage_mode_value}'"
            ) from error

    pipeline_name: str = pipeline_root.name

    bounded_replay_fallback_value: object = typed_pipeline_values.get("bounded_replay_fallback")
    bounded_replay_fallback: BoundedReplayFallback | None = None
    if bounded_replay_fallback_value is not None:
        try:
            bounded_replay_fallback = BoundedReplayFallback(bounded_replay_fallback_value)
        except ValueError as error:
            raise ValueError(
                f"Pipeline file '{file_path}' has unsupported bounded_replay_fallback "
                f"'{bounded_replay_fallback_value}'"
            ) from error

    return Pipeline(
        name=pipeline_name,
        source=source,
        transforms=transforms,
        replay_lineage_mode=replay_lineage_mode,
        bounded_replay_fallback=bounded_replay_fallback,
    )


def _load_pipeline_source(
    pipeline_values: dict[str, Any], file_path: Path
) -> KafkaLandingStep | ExternalTableSourceStep:
    source_values: object = pipeline_values.get("source")
    if not isinstance(source_values, dict) or not all(
        isinstance(key, str) for key in source_values
    ):
        raise ValueError(f"Pipeline file '{file_path}' must define 'source' as a mapping")
    typed_source_values: dict[str, Any] = source_values

    source_kind_value: object = typed_source_values.get("kind")
    try:
        source_kind: SourceKind = SourceKind(source_kind_value)
    except ValueError as error:
        raise ValueError(
            f"Pipeline file '{file_path}' currently supports only "
            "source.kind='kafka' or source.kind='stream_table'"
        ) from error

    source_name: object = typed_source_values.get("name")
    broker_list: object = typed_source_values.get("broker_list")
    topic: object = typed_source_values.get("topic")
    table_name: object = typed_source_values.get("table_name")
    replay_boundary_value: object = typed_source_values.get("replay_boundary")
    consumer_group: object = typed_source_values.get("consumer_group")
    format_value: object = typed_source_values.get("format", "JSONAsString")
    settings_value: object = typed_source_values.get("settings")

    if not isinstance(source_name, str) or not source_name:
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.name as a non-empty string"
        )

    uses_managed_kafka_shape: bool = broker_list is not None or topic is not None
    uses_existing_table_shape: bool = table_name is not None or replay_boundary_value is not None
    if uses_managed_kafka_shape and uses_existing_table_shape:
        raise ValueError(
            f"Pipeline file '{file_path}' must not mix managed Kafka landing fields with "
            "adopted source fields"
        )

    if uses_existing_table_shape:
        return _load_existing_table_source(
            typed_source_values=typed_source_values,
            file_path=file_path,
            source_name=source_name,
            source_kind=source_kind,
        )

    if source_kind != SourceKind.KAFKA:
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.table_name and "
            "source.replay_boundary for source.kind='stream_table'"
        )
    if not isinstance(broker_list, str) or not broker_list:
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.broker_list as a non-empty string"
        )
    if not isinstance(topic, str) or not topic:
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.topic as a non-empty string"
        )
    if consumer_group is not None and not isinstance(consumer_group, str):
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.consumer_group as a string"
        )
    if not isinstance(format_value, str) or not format_value:
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.format as a non-empty string"
        )
    if settings_value is not None and not isinstance(settings_value, dict):
        raise ValueError(f"Pipeline file '{file_path}' must define source.settings as a mapping")

    settings: dict[str, str] | None = None
    if settings_value is not None:
        if not all(isinstance(key, str) for key in settings_value):
            raise ValueError(
                f"Pipeline file '{file_path}' must define source.settings with string keys"
            )
        settings = {key: str(value) for key, value in settings_value.items()}

    return KafkaLandingStep(
        name=source_name,
        kafka=KafkaSettings(
            broker_list=broker_list,
            topic=topic,
            consumer_group=consumer_group,
            format=format_value,
            settings=settings,
        ),
    )


def _load_existing_table_source(
    *,
    typed_source_values: dict[str, Any],
    file_path: Path,
    source_name: str,
    source_kind: SourceKind,
) -> ExternalTableSourceStep:
    table_name: object = typed_source_values.get("table_name")
    replay_boundary_value: object = typed_source_values.get("replay_boundary")
    if not isinstance(table_name, str) or not table_name:
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.table_name as a non-empty string"
        )
    if "." in table_name:
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.table_name as a bare table name; "
            "cross-database source adoption is not supported yet"
        )
    if not isinstance(replay_boundary_value, dict) or not all(
        isinstance(key, str) for key in replay_boundary_value
    ):
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.replay_boundary as a mapping"
        )
    typed_replay_boundary_value: dict[str, Any] = replay_boundary_value
    replay_boundary_mode_value: object = typed_replay_boundary_value.get("mode")
    try:
        replay_boundary_mode: ReplayBoundaryMode = ReplayBoundaryMode(replay_boundary_mode_value)
    except ValueError as error:
        raise ValueError(
            f"Pipeline file '{file_path}' has unsupported source.replay_boundary.mode "
            f"'{replay_boundary_mode_value}'"
        ) from error
    if source_kind == SourceKind.KAFKA and replay_boundary_mode not in {
        ReplayBoundaryMode.OFFSETS,
        ReplayBoundaryMode.TIMESTAMP,
    }:
        raise ValueError(
            f"Pipeline file '{file_path}' supports source.kind='kafka' adoption only with "
            "replay_boundary.mode='offsets' or replay_boundary.mode='timestamp'"
        )
    columns_value: object = typed_replay_boundary_value.get("columns")
    if not isinstance(columns_value, dict) or not all(
        isinstance(key, str) for key in columns_value
    ):
        raise ValueError(
            f"Pipeline file '{file_path}' must define source.replay_boundary.columns as a mapping"
        )
    typed_columns_value: dict[str, Any] = columns_value
    replay_boundary_columns: ReplayBoundaryColumns = ReplayBoundaryColumns(
        partition=_optional_string_field(
            typed_columns_value,
            file_path,
            "source.replay_boundary.columns._replay_partition",
        ),
        offset=_optional_string_field(
            typed_columns_value,
            file_path,
            "source.replay_boundary.columns._replay_offset",
        ),
        timestamp=_optional_string_field(
            typed_columns_value,
            file_path,
            "source.replay_boundary.columns._replay_timestamp",
        ),
        landed_at=_optional_string_field(
            typed_columns_value,
            file_path,
            "source.replay_boundary.columns._replay_landed_at",
        ),
        cursor=_optional_string_field(
            typed_columns_value,
            file_path,
            "source.replay_boundary.columns._replay_cursor",
        ),
    )
    _validate_replay_boundary_columns(
        file_path=file_path,
        replay_boundary_mode=replay_boundary_mode,
        replay_boundary_columns=replay_boundary_columns,
    )
    return ExternalTableSourceStep(
        name=source_name,
        kind=source_kind,
        table_name=table_name,
        replay_boundary=ReplayBoundary(
            mode=replay_boundary_mode,
            columns=replay_boundary_columns,
        ),
    )


def _optional_string_field(
    typed_values: dict[str, Any],
    file_path: Path,
    field_name: str,
) -> str | None:
    raw_value: object = typed_values.get(field_name.rsplit(".", 1)[1])
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value:
        raise ValueError(f"Pipeline file '{file_path}' must define {field_name} as a string")
    return raw_value


def _validate_replay_boundary_columns(
    *,
    file_path: Path,
    replay_boundary_mode: ReplayBoundaryMode,
    replay_boundary_columns: ReplayBoundaryColumns,
) -> None:
    if replay_boundary_mode == ReplayBoundaryMode.OFFSETS:
        if replay_boundary_columns.partition is None or replay_boundary_columns.offset is None:
            raise ValueError(
                f"Pipeline file '{file_path}' must define replay boundary partition and offset "
                "columns for source.replay_boundary.mode='offsets'"
            )
        if replay_boundary_columns.timestamp is None:
            raise ValueError(
                f"Pipeline file '{file_path}' must define a replay boundary timestamp column "
                "for source.replay_boundary.mode='offsets'"
            )
        if replay_boundary_columns.landed_at is not None:
            raise ValueError(
                f"Pipeline file '{file_path}' must not define a replay boundary landed_at column "
                "for source.replay_boundary.mode='offsets'"
            )
        return
    if replay_boundary_mode == ReplayBoundaryMode.TIMESTAMP:
        if replay_boundary_columns.timestamp is None:
            raise ValueError(
                f"Pipeline file '{file_path}' must define a replay boundary timestamp column "
                "for source.replay_boundary.mode='timestamp'"
            )
        if replay_boundary_columns.landed_at is not None:
            raise ValueError(
                f"Pipeline file '{file_path}' must not define a replay boundary landed_at column "
                "for source.replay_boundary.mode='timestamp'"
            )
        return
    if replay_boundary_columns.cursor is None:
        raise ValueError(
            f"Pipeline file '{file_path}' must define a replay boundary cursor column for "
            "source.replay_boundary.mode='cursor'"
        )
    if replay_boundary_columns.timestamp is None:
        raise ValueError(
            f"Pipeline file '{file_path}' must define a replay boundary timestamp column "
            "for source.replay_boundary.mode='cursor'"
        )


def _load_pipeline_transforms(pipeline_root: Path) -> list[TransformStep]:
    model_file_paths: list[Path] = sorted(pipeline_root.rglob("*.sql"))
    if not model_file_paths:
        raise ValueError(
            f"Pipeline root '{pipeline_root}' must contain at least one SQL model file"
        )

    transforms: list[TransformStep] = []
    model_paths_by_name: dict[str, Path] = {}
    model_file_path: Path
    for model_file_path in model_file_paths:
        existing_path: Path | None = model_paths_by_name.get(model_file_path.stem)
        if existing_path is not None:
            raise ValueError(
                f"Pipeline root '{pipeline_root}' defines duplicate model filename stem "
                f"'{model_file_path.stem}' in both '{existing_path}' and '{model_file_path}'"
            )
        model_paths_by_name[model_file_path.stem] = model_file_path
        transforms.append(load_transform_from_sql_file(model_file_path))
    return transforms


def load_project_for_pipeline_file(file_path: Path) -> Project | None:
    """Load the nearest project config for a pipeline file, if present."""

    project_file_path: Path | None = find_project_file(file_path)
    if project_file_path is None:
        return None

    return load_project_yaml(project_file_path)


def load_project_for_path(path: Path) -> Project | None:
    """Load the nearest project config for a path, if present."""

    project_file_path: Path | None = find_project_file(path)
    if project_file_path is None:
        return None

    return load_project_yaml(project_file_path)


def find_project_file(path: Path) -> Path | None:
    """Find the nearest `streambuild_project.yml` for a file or directory path."""

    current_path: Path = path if path.is_dir() else path.parent
    candidate_root: Path
    for candidate_root in [current_path, *current_path.parents]:
        project_file_path: Path = candidate_root / PROJECT_FILE_NAME
        if project_file_path.exists():
            return project_file_path
    return None


def load_project_yaml(file_path: Path) -> Project:
    """Load `streambuild_project.yml` into the authored project model."""

    project_values: object = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(project_values, dict) or not all(
        isinstance(key, str) for key in project_values
    ):
        raise ValueError(f"Project file '{file_path}' must define a top-level mapping")
    typed_project_values: dict[str, Any] = project_values

    unknown_keys: list[str] = [
        key
        for key in typed_project_values
        if key
        not in {
            "default_database",
            "replay_lineage_mode",
            "bounded_replay_fallback",
            "clickhouse",
        }
    ]
    if unknown_keys:
        unknown_key_list: str = ", ".join(sorted(unknown_keys))
        raise ValueError(
            f"Project file '{file_path}' contains unsupported keys: {unknown_key_list}"
        )

    default_database_value: object = typed_project_values.get("default_database")
    if default_database_value is not None and (
        not isinstance(default_database_value, str) or not default_database_value
    ):
        raise ValueError(
            f"Project file '{file_path}' must define default_database as a non-empty string"
        )

    replay_lineage_mode_value: object = typed_project_values.get(
        "replay_lineage_mode", ReplayLineageMode.OFFSETS
    )
    try:
        replay_lineage_mode: ReplayLineageMode = ReplayLineageMode(replay_lineage_mode_value)
    except ValueError as error:
        raise ValueError(
            f"Project file '{file_path}' has unsupported replay_lineage_mode "
            f"'{replay_lineage_mode_value}'"
        ) from error

    bounded_replay_fallback_value: object = typed_project_values.get(
        "bounded_replay_fallback", BoundedReplayFallback.FULL_REFRESH
    )
    try:
        bounded_replay_fallback: BoundedReplayFallback = BoundedReplayFallback(
            bounded_replay_fallback_value
        )
    except ValueError as error:
        raise ValueError(
            f"Project file '{file_path}' has unsupported bounded_replay_fallback "
            f"'{bounded_replay_fallback_value}'"
        ) from error

    clickhouse_value: object = typed_project_values.get("clickhouse")
    clickhouse: ProjectClickHouseConfig | None = None
    if clickhouse_value is not None:
        clickhouse = _load_project_clickhouse_config(clickhouse_value, file_path)

    return Project(
        replay_lineage_mode=replay_lineage_mode,
        bounded_replay_fallback=bounded_replay_fallback,
        default_database=default_database_value,
        clickhouse=clickhouse,
    )


def _load_project_clickhouse_config(
    clickhouse_value: object,
    file_path: Path,
) -> ProjectClickHouseConfig:
    if not isinstance(clickhouse_value, dict) or not all(
        isinstance(key, str) for key in clickhouse_value
    ):
        raise ValueError(f"Project file '{file_path}' must define clickhouse as a mapping")
    typed_clickhouse_values: dict[str, Any] = cast(dict[str, Any], clickhouse_value)

    unknown_keys: list[str] = [
        key
        for key in typed_clickhouse_values
        if key not in {"host", "port", "username", "password"}
    ]
    if unknown_keys:
        unknown_key_list: str = ", ".join(sorted(unknown_keys))
        raise ValueError(
            f"Project file '{file_path}' contains unsupported clickhouse keys: {unknown_key_list}"
        )

    host: object = typed_clickhouse_values.get("host")
    port: object = typed_clickhouse_values.get("port")
    username: object = typed_clickhouse_values.get("username")
    password: object = typed_clickhouse_values.get("password")
    if not isinstance(host, str) or not host:
        raise ValueError(
            f"Project file '{file_path}' must define clickhouse.host as a non-empty string"
        )
    if not isinstance(port, int):
        raise ValueError(f"Project file '{file_path}' must define clickhouse.port as an integer")
    if not isinstance(username, str) or not username:
        raise ValueError(
            f"Project file '{file_path}' must define clickhouse.username as a non-empty string"
        )
    if not isinstance(password, str):
        raise ValueError(f"Project file '{file_path}' must define clickhouse.password as a string")

    return ProjectClickHouseConfig(
        host=host,
        port=port,
        username=username,
        password=password,
    )


def validate_unique_logical_names(
    loaded_pipeline: LoadedPipeline,
    logical_node_names: dict[str, Path],
) -> None:
    """Validate that a loaded pipeline does not duplicate logical names."""

    for logical_name in [
        loaded_pipeline.pipeline.source.name,
        *[transform.name for transform in loaded_pipeline.pipeline.transforms],
    ]:
        existing_path: Path | None = logical_node_names.get(logical_name)
        if existing_path is not None:
            raise ValueError(
                "Logical node name "
                f"'{logical_name}' is defined in both "
                f"'{existing_path}' and '{loaded_pipeline.file_path}'"
            )
        logical_node_names[logical_name] = loaded_pipeline.file_path
