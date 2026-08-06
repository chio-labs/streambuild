"""Standalone streaming source registry discovery and parsing."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import yaml
from yaml import YAMLError

from streambuild.compiler.discovery._helpers.interpolation import interpolate_config_value
from streambuild.compiler.discovery.constants import (
    FRESHNESS_DURATION_PATTERN,
    FRESHNESS_KEYS,
    INTERPOLATION_TOKEN_START,
    REPLAY_BOUNDARY_COLUMN_KEYS,
    REPLAY_BOUNDARY_KEYS,
    SECONDS_BY_DURATION_UNIT,
    SOURCE_FILE_KEYS,
    SOURCE_KEYS,
)
from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.models import (
    DiscoveredProjectFile,
    DiscoveredSourceFile,
    ExternalTableSourceStep,
    KafkaLandingStep,
    KafkaSettings,
    ReplayBoundary,
    ReplayBoundaryColumns,
    SourceFreshnessPolicy,
)
from streambuild.compiler.discovery.types import ReplayBoundaryMode, SourceKind


def discover_source_registry(
    *,
    project_dir: Path,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    default_managed_source_ttl: str | None = None,
    default_freshness: SourceFreshnessPolicy | None = None,
) -> tuple[DiscoveredSourceFile, ...]:
    """Load direct sources/*.yml files once in stable order and validate uniqueness."""

    sources_root: Path = project_dir / "sources"
    if not sources_root.is_dir():
        return ()
    discovered_files: tuple[DiscoveredSourceFile, ...] = tuple(
        _load_source_file(
            file_path=file_path,
            project_dir=project_dir,
            variables=variables,
            environment=environment,
            default_managed_source_ttl=default_managed_source_ttl,
            default_freshness=default_freshness,
        )
        for file_path in sorted(sources_root.glob("*.yml"))
    )
    _validate_unique_source_names(discovered_files)
    _validate_consistent_adopted_table_mappings(discovered_files)
    return discovered_files


def parse_freshness_policy(
    *,
    payload: object,
    label: str,
    file_path: Path,
) -> SourceFreshnessPolicy | None:
    """Parse one optional freshness mapping of duration-literal thresholds."""

    if payload is None:
        return None
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise PipelineDiscoveryError(f"'{file_path}' {label} must be a mapping when set")
    mapping: dict[str, object] = cast("dict[str, object]", payload)
    unknown_keys: tuple[str, ...] = tuple(sorted(set(mapping) - FRESHNESS_KEYS))
    if unknown_keys:
        raise PipelineDiscoveryError(
            f"'{file_path}' {label} has unknown keys: {', '.join(unknown_keys)}"
        )
    warn_after: str | None = _optional_duration(
        payload=mapping, key="warn_after", label=label, file_path=file_path
    )
    error_after: str | None = _optional_duration(
        payload=mapping, key="error_after", label=label, file_path=file_path
    )
    if warn_after is None and error_after is None:
        raise PipelineDiscoveryError(
            f"'{file_path}' {label} must set at least one of warn_after or error_after"
        )
    if (
        warn_after is not None
        and error_after is not None
        and _duration_seconds(warn_after) > _duration_seconds(error_after)
    ):
        raise PipelineDiscoveryError(
            f"'{file_path}' {label}.warn_after must not exceed error_after"
        )
    return SourceFreshnessPolicy(warn_after=warn_after, error_after=error_after)


def _optional_duration(
    *,
    payload: dict[str, object],
    key: str,
    label: str,
    file_path: Path,
) -> str | None:
    value: object = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or FRESHNESS_DURATION_PATTERN.fullmatch(value) is None:
        raise PipelineDiscoveryError(
            f"'{file_path}' {label}.{key} must be a duration like '15m', '2h', or '1d'"
        )
    return value


def _duration_seconds(value: str) -> int:
    match: re.Match[str] | None = FRESHNESS_DURATION_PATTERN.fullmatch(value)
    if match is None:
        raise PipelineDiscoveryError(f"invalid freshness duration literal '{value}'")
    return int(match.group(1)) * SECONDS_BY_DURATION_UNIT[match.group(2)]


def source_registry_by_name(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> dict[str, KafkaLandingStep | ExternalTableSourceStep]:
    """Index one validated source registry by project-wide source name."""

    sources_by_name: dict[str, KafkaLandingStep | ExternalTableSourceStep] = {}
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source: KafkaLandingStep | ExternalTableSourceStep
        for source in source_file.sources:
            sources_by_name[source.name] = source
    return sources_by_name


def _validate_consistent_adopted_table_mappings(
    source_files: tuple[DiscoveredSourceFile, ...],
) -> None:
    boundary_by_table_name: dict[str, ReplayBoundary] = {}
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source: KafkaLandingStep | ExternalTableSourceStep
        for source in source_file.sources:
            if not isinstance(source, ExternalTableSourceStep):
                continue
            existing_boundary: ReplayBoundary | None = boundary_by_table_name.get(source.table_name)
            if existing_boundary is not None and existing_boundary != source.replay_boundary:
                raise PipelineDiscoveryError(
                    f"Adopted source table '{source.table_name}' has conflicting replay mappings"
                )
            boundary_by_table_name[source.table_name] = source.replay_boundary


def _load_source_file(
    *,
    file_path: Path,
    project_dir: Path,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    default_managed_source_ttl: str | None,
    default_freshness: SourceFreshnessPolicy | None,
) -> DiscoveredSourceFile:
    contents: str = file_path.read_text(encoding="utf-8")
    source_file: DiscoveredProjectFile = DiscoveredProjectFile(
        file_path=file_path,
        relative_path=file_path.relative_to(project_dir),
        contents=contents,
    )
    return DiscoveredSourceFile(
        source_file=source_file,
        sources=_parse_source_file(
            source_file=source_file,
            variables=variables,
            environment=environment,
            default_managed_source_ttl=default_managed_source_ttl,
            default_freshness=default_freshness,
        ),
    )


def _parse_source_file(
    *,
    source_file: DiscoveredProjectFile,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    default_managed_source_ttl: str | None,
    default_freshness: SourceFreshnessPolicy | None,
) -> tuple[KafkaLandingStep | ExternalTableSourceStep, ...]:
    try:
        raw_payload: object = yaml.safe_load(source_file.contents)
    except YAMLError as error:
        raise PipelineDiscoveryError(
            f"Source file '{source_file.file_path}' contains invalid YAML: {error}"
        ) from error
    payload: dict[str, object] = _mapping(
        value=raw_payload,
        field_path="source file",
        file_path=source_file.file_path,
    )
    _validate_keys(
        mapping=payload,
        allowed=SOURCE_FILE_KEYS,
        field_path="source file",
        file_path=source_file.file_path,
    )
    raw_sources: object = payload.get("sources")
    if not isinstance(raw_sources, list):
        raise PipelineDiscoveryError(
            f"Source file '{source_file.file_path}' must define sources as a list"
        )
    return tuple(
        _parse_source(
            value=raw_source,
            index=index,
            file_path=source_file.file_path,
            variables=variables,
            environment=environment,
            default_managed_source_ttl=default_managed_source_ttl,
            default_freshness=default_freshness,
        )
        for index, raw_source in enumerate(raw_sources)
    )


def _parse_source(
    *,
    value: object,
    index: int,
    file_path: Path,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    default_managed_source_ttl: str | None,
    default_freshness: SourceFreshnessPolicy | None,
) -> KafkaLandingStep | ExternalTableSourceStep:
    label: str = f"sources[{index}]"
    mapping: dict[str, object] = _mapping(
        value=value,
        field_path=label,
        file_path=file_path,
    )
    _validate_keys(mapping=mapping, allowed=SOURCE_KEYS, field_path=label, file_path=file_path)
    name: str = _required_string(
        mapping=mapping,
        key="name",
        field_path=label,
        file_path=file_path,
        variables=variables,
        environment=environment,
    )
    raw_kind: str = _required_string(
        mapping=mapping,
        key="kind",
        field_path=label,
        file_path=file_path,
        variables=variables,
        environment=environment,
    )
    try:
        kind: SourceKind = SourceKind(raw_kind)
    except ValueError as error:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {label}.kind must be 'kafka' or 'stream_table'"
        ) from error
    freshness: SourceFreshnessPolicy | None = (
        parse_freshness_policy(
            payload=mapping.get("freshness"),
            label=f"{label}.freshness",
            file_path=file_path,
        )
        or default_freshness
    )
    if kind == SourceKind.KAFKA:
        return _parse_managed_kafka_source(
            mapping=mapping,
            name=name,
            label=label,
            file_path=file_path,
            variables=variables,
            environment=environment,
            default_managed_source_ttl=default_managed_source_ttl,
            freshness=freshness,
        )
    return _parse_adopted_source(
        mapping=mapping,
        name=name,
        label=label,
        file_path=file_path,
        variables=variables,
        environment=environment,
        freshness=freshness,
    )


def _parse_managed_kafka_source(
    *,
    mapping: dict[str, object],
    name: str,
    label: str,
    file_path: Path,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    default_managed_source_ttl: str | None,
    freshness: SourceFreshnessPolicy | None,
) -> KafkaLandingStep:
    if mapping.get("table_name") is not None:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {label} must not mix Kafka and adopted table fields"
        )
    replay_boundary: ReplayBoundary = _parse_replay_boundary(
        value=mapping.get("replay_boundary"),
        label=f"{label}.replay_boundary",
        file_path=file_path,
        allowed_modes=frozenset(
            {
                ReplayBoundaryMode.OFFSETS,
                ReplayBoundaryMode.TIMESTAMP,
                ReplayBoundaryMode.LANDED_AT,
            }
        ),
        require_columns=False,
        variables=variables,
        environment=environment,
    )
    settings_mapping: dict[str, object] = _mapping(
        value=mapping.get("settings"),
        field_path=f"{label}.settings",
        file_path=file_path,
        optional=True,
    )
    settings: dict[str, str] = {
        key: _interpolated_string(
            value=value,
            field_path=f"{label}.settings.{key}",
            file_path=file_path,
            variables=variables,
            environment=environment,
        )
        for key, value in settings_mapping.items()
    }
    return KafkaLandingStep(
        name=name,
        kafka=KafkaSettings(
            broker_list=_required_string(
                mapping=mapping,
                key="broker_list",
                field_path=label,
                file_path=file_path,
                variables=variables,
                environment=environment,
            ),
            topic=_required_string(
                mapping=mapping,
                key="topic",
                field_path=label,
                file_path=file_path,
                variables=variables,
                environment=environment,
            ),
            consumer_group=_optional_string(
                mapping=mapping,
                key="consumer_group",
                field_path=label,
                file_path=file_path,
                variables=variables,
                environment=environment,
            ),
            format=_optional_string(
                mapping=mapping,
                key="format",
                field_path=label,
                file_path=file_path,
                variables=variables,
                environment=environment,
            )
            or "JSONAsString",
            ttl=_optional_string(
                mapping=mapping,
                key="ttl",
                field_path=label,
                file_path=file_path,
                variables=variables,
                environment=environment,
            )
            or default_managed_source_ttl,
            settings=settings or None,
        ),
        replay_boundary=replay_boundary,
        freshness=freshness,
    )


def _parse_adopted_source(
    *,
    mapping: dict[str, object],
    name: str,
    label: str,
    file_path: Path,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    freshness: SourceFreshnessPolicy | None,
) -> ExternalTableSourceStep:
    managed_fields: tuple[str, ...] = tuple(
        field
        for field in ("broker_list", "topic", "consumer_group", "format", "ttl", "settings")
        if mapping.get(field) is not None
    )
    if managed_fields:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {label} must not mix adopted and Kafka fields: "
            f"{', '.join(managed_fields)}"
        )
    replay_boundary: ReplayBoundary = _parse_replay_boundary(
        value=mapping.get("replay_boundary"),
        label=f"{label}.replay_boundary",
        file_path=file_path,
        allowed_modes=frozenset(
            {ReplayBoundaryMode.OFFSETS, ReplayBoundaryMode.TIMESTAMP, ReplayBoundaryMode.CURSOR}
        ),
        require_columns=True,
        variables=variables,
        environment=environment,
    )
    return ExternalTableSourceStep(
        name=name,
        kind=SourceKind.STREAM_TABLE,
        table_name=_required_string(
            mapping=mapping,
            key="table_name",
            field_path=label,
            file_path=file_path,
            variables=variables,
            environment=environment,
        ),
        replay_boundary=replay_boundary,
        freshness=freshness,
    )


def _parse_replay_boundary(
    *,
    value: object,
    label: str,
    file_path: Path,
    allowed_modes: frozenset[ReplayBoundaryMode],
    require_columns: bool,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
) -> ReplayBoundary:
    mapping: dict[str, object] = _mapping(
        value=value,
        field_path=label,
        file_path=file_path,
    )
    _validate_keys(
        mapping=mapping,
        allowed=REPLAY_BOUNDARY_KEYS,
        field_path=label,
        file_path=file_path,
    )
    raw_mode: str = _required_string(
        mapping=mapping,
        key="mode",
        field_path=label,
        file_path=file_path,
        variables=variables,
        environment=environment,
    )
    try:
        mode: ReplayBoundaryMode = ReplayBoundaryMode(raw_mode)
    except ValueError as error:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {label}.mode is unsupported"
        ) from error
    if mode not in allowed_modes:
        supported: str = ", ".join(sorted(item.value for item in allowed_modes))
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {label}.mode '{mode}' must be one of: {supported}"
        )
    raw_columns: object = mapping.get("columns")
    if not require_columns and raw_columns is not None:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {label}.columns is only valid for adopted sources"
        )
    columns: ReplayBoundaryColumns = _parse_boundary_columns(
        value=raw_columns,
        label=f"{label}.columns",
        file_path=file_path,
        variables=variables,
        environment=environment,
    )
    if require_columns:
        _validate_adopted_boundary_columns(
            mode=mode,
            columns=columns,
            label=label,
            file_path=file_path,
        )
    return ReplayBoundary(mode=mode, columns=columns)


def _parse_boundary_columns(
    *,
    value: object,
    label: str,
    file_path: Path,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
) -> ReplayBoundaryColumns:
    mapping: dict[str, object] = _mapping(
        value=value,
        field_path=label,
        file_path=file_path,
        optional=True,
    )
    _validate_keys(
        mapping=mapping,
        allowed=REPLAY_BOUNDARY_COLUMN_KEYS,
        field_path=label,
        file_path=file_path,
    )
    return ReplayBoundaryColumns(
        partition=_optional_string(
            mapping=mapping,
            key="_replay_partition",
            field_path=label,
            file_path=file_path,
            variables=variables,
            environment=environment,
        ),
        offset=_optional_string(
            mapping=mapping,
            key="_replay_offset",
            field_path=label,
            file_path=file_path,
            variables=variables,
            environment=environment,
        ),
        timestamp=_optional_string(
            mapping=mapping,
            key="_replay_timestamp",
            field_path=label,
            file_path=file_path,
            variables=variables,
            environment=environment,
        ),
        landed_at=_optional_string(
            mapping=mapping,
            key="_replay_landed_at",
            field_path=label,
            file_path=file_path,
            variables=variables,
            environment=environment,
        ),
        cursor=_optional_string(
            mapping=mapping,
            key="_replay_cursor",
            field_path=label,
            file_path=file_path,
            variables=variables,
            environment=environment,
        ),
    )


def _validate_adopted_boundary_columns(
    *, mode: ReplayBoundaryMode, columns: ReplayBoundaryColumns, label: str, file_path: Path
) -> None:
    if mode == ReplayBoundaryMode.OFFSETS:
        if columns.partition is None or columns.offset is None or columns.timestamp is None:
            raise PipelineDiscoveryError(
                f"Source file '{file_path}' {label} offsets mode requires partition, offset, "
                "and timestamp role columns"
            )
        if columns.cursor is not None or columns.landed_at is not None:
            raise PipelineDiscoveryError(
                f"Source file '{file_path}' {label} offsets mode has incompatible role columns"
            )
        return
    if mode == ReplayBoundaryMode.TIMESTAMP:
        if columns.timestamp is None:
            raise PipelineDiscoveryError(
                f"Source file '{file_path}' {label} timestamp mode requires a timestamp role column"
            )
        if any(
            value is not None
            for value in (columns.partition, columns.offset, columns.cursor, columns.landed_at)
        ):
            raise PipelineDiscoveryError(
                f"Source file '{file_path}' {label} timestamp mode has incompatible role columns"
            )
        return
    if columns.cursor is None or columns.timestamp is None:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {label} cursor mode requires cursor and timestamp "
            "role columns"
        )
    if any(value is not None for value in (columns.partition, columns.offset, columns.landed_at)):
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {label} cursor mode has incompatible role columns"
        )


def _validate_unique_source_names(files: tuple[DiscoveredSourceFile, ...]) -> None:
    paths_by_name: dict[str, Path] = {}
    source_file: DiscoveredSourceFile
    for source_file in files:
        source: KafkaLandingStep | ExternalTableSourceStep
        for source in source_file.sources:
            existing_path: Path | None = paths_by_name.get(source.name)
            if existing_path is not None:
                raise PipelineDiscoveryError(
                    f"Duplicate source name '{source.name}' found in '{existing_path}' and "
                    f"'{source_file.source_file.file_path}'"
                )
            paths_by_name[source.name] = source_file.source_file.file_path


def _mapping(
    *, value: object, field_path: str, file_path: Path, optional: bool = False
) -> dict[str, object]:
    if value is None and optional:
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PipelineDiscoveryError(f"Source file '{file_path}' {field_path} must be a mapping")
    mapping: dict[str, object] = cast(dict[str, object], value)
    interpolated_keys: tuple[str, ...] = tuple(
        sorted(key for key in mapping if INTERPOLATION_TOKEN_START in key)
    )
    if interpolated_keys:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {field_path} must not interpolate mapping keys: "
            f"{', '.join(interpolated_keys)}"
        )
    return mapping


def _required_string(
    *,
    mapping: dict[str, object],
    key: str,
    field_path: str,
    file_path: Path,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
) -> str:
    value: str | None = _optional_string(
        mapping=mapping,
        key=key,
        field_path=field_path,
        file_path=file_path,
        variables=variables,
        environment=environment,
    )
    if value is None:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {field_path}.{key} must be a non-empty string"
        )
    return value


def _optional_string(
    *,
    mapping: dict[str, object],
    key: str,
    field_path: str,
    file_path: Path,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
) -> str | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
    return _interpolated_string(
        value=value,
        field_path=f"{field_path}.{key}",
        file_path=file_path,
        variables=variables,
        environment=environment,
    )


def _interpolated_string(
    *,
    value: object,
    field_path: str,
    file_path: Path,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
) -> str:
    interpolated: object = interpolate_config_value(
        value=value,
        variables=variables,
        environment=environment,
        field_path=f"{file_path}:{field_path}",
    )
    if not isinstance(interpolated, str) or not interpolated:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {field_path} must resolve to a non-empty string"
        )
    return interpolated


def _validate_keys(
    *, mapping: dict[str, object], allowed: frozenset[str], field_path: str, file_path: Path
) -> None:
    unknown: tuple[str, ...] = tuple(sorted(set(mapping) - allowed))
    if unknown:
        raise PipelineDiscoveryError(
            f"Source file '{file_path}' {field_path} contains unsupported keys: "
            f"{', '.join(unknown)}"
        )
