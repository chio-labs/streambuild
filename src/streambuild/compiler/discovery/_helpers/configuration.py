"""Strict TOML project and local configuration loading."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import cast

from streambuild.compiler.discovery._helpers.source_registry import parse_freshness_policy
from streambuild.compiler.discovery.constants import (
    AUDIT_DEFAULT_EVERY_KEY,
    AUDIT_DEFAULT_KEYS,
    AUDIT_DEFAULT_WARMUP_KEY,
    AUDIT_SCHEDULER_KEYS,
    AUDIT_SEVERITIES,
    BUILD_KEYS,
    DEFAULT_ADAPTER_NAME,
    DEFAULTS_KEYS,
    DEPLOYMENT_READINESS_KEYS,
    FULL_REPLAY_POLICY_VALUE,
    INTERPOLATION_TOKEN_START,
    KAFKA_SOURCE_DEFAULT_KEYS,
    LEGACY_LOCAL_CONFIG_FILE_NAME,
    LEGACY_PROJECT_CONFIG_FILE_NAME,
    LOCAL_CONFIG_FILE_NAME,
    LOCAL_CONFIG_KEYS,
    LOCAL_DEFAULTS_KEYS,
    LOCAL_TARGET_KEYS,
    NAMING_KEYS,
    NAMING_TABLE_PREFIX_KEY,
    NAMING_VIEW_PREFIX_KEY,
    PIPELINE_MODE_KEY,
    PROJECT_CONFIG_FILE_NAME,
    PROJECT_CONFIG_KEYS,
    RUN_UNRESPONSIVE_AFTER_SECONDS,
    SECONDS_BY_DURATION_UNIT,
    SOURCE_DEFAULT_KEYS,
    TARGET_KEYS,
)
from streambuild.compiler.discovery.exceptions import ProjectConfigError
from streambuild.compiler.discovery.main._parse_duration_seconds import parse_duration_seconds
from streambuild.compiler.discovery.models import (
    AuditDefaults,
    AuditSchedulerConfig,
    AuditSchedulerOverride,
    AuthoredProjectConfig,
    BuildConfig,
    DeploymentReadinessDefaults,
    DiscoveredProjectFile,
    KafkaSourceDefaults,
    LoadedProjectConfiguration,
    LocalProjectConfig,
    LocalProjectDefaults,
    LocalProjectTarget,
    ProjectDefaults,
    ProjectNaming,
    ProjectTarget,
    RawConnectionConfig,
    ReplayOnChangePolicy,
    ReplayOnChangeRule,
    SourceDefaults,
)
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    PipelineMode,
    ReplayOnChangeMode,
)


def load_project_configuration(*, project_dir: Path) -> LoadedProjectConfiguration:
    """Load one committed project config and optional local overrides."""

    project_path: Path = project_dir / PROJECT_CONFIG_FILE_NAME
    legacy_project_path: Path = project_dir / LEGACY_PROJECT_CONFIG_FILE_NAME
    _validate_config_paths(
        project_path=project_path,
        legacy_project_path=legacy_project_path,
        local_path=project_dir / LOCAL_CONFIG_FILE_NAME,
        legacy_local_path=project_dir / LEGACY_LOCAL_CONFIG_FILE_NAME,
    )
    project_source: DiscoveredProjectFile = _read_config_source(
        file_path=project_path,
        project_dir=project_dir,
    )
    project_payload: dict[str, object] = _parse_toml_source(project_source)
    project: AuthoredProjectConfig = _parse_project_config(
        payload=project_payload,
        file_path=project_path,
    )
    local_path: Path = project_dir / LOCAL_CONFIG_FILE_NAME
    if not local_path.exists():
        return LoadedProjectConfiguration(
            project=project,
            local=LocalProjectConfig(),
            project_source=project_source,
            local_source=None,
        )
    local_source: DiscoveredProjectFile = _read_config_source(
        file_path=local_path,
        project_dir=project_dir,
    )
    return LoadedProjectConfiguration(
        project=project,
        local=_parse_local_config(
            payload=_parse_toml_source(local_source),
            file_path=local_path,
        ),
        project_source=project_source,
        local_source=local_source,
    )


def find_project_configuration_dir(path: Path) -> Path | None:
    """Find the nearest TOML or rejected legacy project configuration directory."""

    current_path: Path = path if path.is_dir() else path.parent
    candidate_dir: Path
    for candidate_dir in (current_path, *current_path.parents):
        if (candidate_dir / PROJECT_CONFIG_FILE_NAME).exists() or (
            candidate_dir / LEGACY_PROJECT_CONFIG_FILE_NAME
        ).exists():
            return candidate_dir
    return None


def _validate_config_paths(
    *,
    project_path: Path,
    legacy_project_path: Path,
    local_path: Path,
    legacy_local_path: Path,
) -> None:
    if legacy_project_path.exists():
        detail: str = (
            "Mixed project config formats are not supported." if project_path.exists() else ""
        )
        raise ProjectConfigError(
            f"{legacy_project_path} is not supported. Convert it to {PROJECT_CONFIG_FILE_NAME}. "
            f"{detail}".rstrip()
        )
    if legacy_local_path.exists():
        detail = "Mixed local config formats are not supported." if local_path.exists() else ""
        raise ProjectConfigError(
            f"{legacy_local_path} is not supported. Convert it to {LOCAL_CONFIG_FILE_NAME}. "
            f"{detail}".rstrip()
        )
    if not project_path.exists():
        raise ProjectConfigError(
            f"Project config not found: {project_path}. Run stb inside a StreamBuild project "
            "or pass --project-dir."
        )


def _read_config_source(*, file_path: Path, project_dir: Path) -> DiscoveredProjectFile:
    return DiscoveredProjectFile(
        file_path=file_path,
        relative_path=file_path.relative_to(project_dir),
        contents=file_path.read_text(encoding="utf-8"),
    )


def _parse_toml_source(source: DiscoveredProjectFile) -> dict[str, object]:
    try:
        payload: object = tomllib.loads(source.contents)
    except tomllib.TOMLDecodeError as error:
        raise ProjectConfigError(f"{source.file_path} contains invalid TOML: {error}") from error
    if not isinstance(payload, dict):
        raise ProjectConfigError(f"{source.file_path} must contain a top-level mapping")
    return cast(dict[str, object], payload)


def _parse_project_config(
    *,
    payload: dict[str, object],
    file_path: Path,
) -> AuthoredProjectConfig:
    _validate_allowed_keys(
        mapping=payload,
        allowed_keys=PROJECT_CONFIG_KEYS,
        label="project",
        file_path=file_path,
    )
    targets: tuple[tuple[str, ProjectTarget], ...] = _parse_project_targets(
        payload=payload.get("targets"), file_path=file_path
    )
    build: BuildConfig = _parse_build_config(
        payload=payload.get("build"),
        label="build",
        file_path=file_path,
    )
    if build.max_pipelines is None and any(
        target.build.max_pipelines is not None for _, target in targets
    ):
        raise ProjectConfigError(
            f"{file_path} target build limits require build.max_pipelines as a project default"
        )
    return AuthoredProjectConfig(
        name=_require_project_name(
            mapping=payload,
            file_path=file_path,
        ),
        adapter=_optional_non_empty_string(
            mapping=payload,
            key="adapter",
            label="project",
            file_path=file_path,
        )
        or DEFAULT_ADAPTER_NAME,
        default_target=_require_non_empty_string(
            mapping=payload,
            key="default_target",
            label="project",
            file_path=file_path,
        ),
        connection=_parse_connection(payload=payload.get("connection"), file_path=file_path),
        variables=_parse_variables(
            payload=payload.get("vars"),
            label="project.vars",
            file_path=file_path,
        ),
        targets=targets,
        defaults=_parse_project_defaults(payload=payload.get("defaults"), file_path=file_path),
        naming=_parse_project_naming(payload=payload.get("naming"), file_path=file_path),
        audit_scheduler=_parse_audit_scheduler_config(
            payload=payload.get("audit_scheduler"),
            label="audit_scheduler",
            file_path=file_path,
        ),
        build=build,
    )


def _parse_local_config(
    *,
    payload: dict[str, object],
    file_path: Path,
) -> LocalProjectConfig:
    _validate_allowed_keys(
        mapping=payload,
        allowed_keys=LOCAL_CONFIG_KEYS,
        label="local project",
        file_path=file_path,
    )
    return LocalProjectConfig(
        target=_optional_non_empty_string(
            mapping=payload,
            key="target",
            label="local project",
            file_path=file_path,
        ),
        adapter=_optional_non_empty_string(
            mapping=payload,
            key="adapter",
            label="local project",
            file_path=file_path,
        ),
        defaults=_parse_local_defaults(payload=payload.get("defaults"), file_path=file_path),
        connection=_parse_connection(payload=payload.get("connection"), file_path=file_path),
        variables=_parse_variables(
            payload=payload.get("vars"),
            label="local project.vars",
            file_path=file_path,
        ),
        targets=_parse_local_targets(payload=payload.get("targets"), file_path=file_path),
    )


def _parse_local_defaults(*, payload: object, file_path: Path) -> LocalProjectDefaults:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label="defaults",
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=LOCAL_DEFAULTS_KEYS,
        label="defaults",
        file_path=file_path,
    )
    return LocalProjectDefaults(
        pipeline_mode=(
            _parse_pipeline_mode(
                value=mapping[PIPELINE_MODE_KEY],
                label="defaults.pipeline_mode",
                file_path=file_path,
            )
            if PIPELINE_MODE_KEY in mapping
            else None
        )
    )


def _parse_project_targets(
    *, payload: object, file_path: Path
) -> tuple[tuple[str, ProjectTarget], ...]:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label="targets",
        file_path=file_path,
    )
    return tuple(
        (
            name,
            _parse_project_target(
                payload=value,
                label=f"targets.{name}",
                file_path=file_path,
            ),
        )
        for name, value in sorted(mapping.items())
    )


def _parse_local_targets(
    *, payload: object, file_path: Path
) -> tuple[tuple[str, LocalProjectTarget], ...]:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label="targets",
        file_path=file_path,
    )
    return tuple(
        (
            name,
            _parse_local_target(
                payload=value,
                label=f"targets.{name}",
                file_path=file_path,
            ),
        )
        for name, value in sorted(mapping.items())
    )


def _parse_project_target(*, payload: object, label: str, file_path: Path) -> ProjectTarget:
    mapping: dict[str, object] = _target_mapping(
        payload=payload,
        label=label,
        file_path=file_path,
        allowed_keys=TARGET_KEYS,
    )
    return ProjectTarget(
        database=_optional_non_empty_string(
            mapping=mapping,
            key="database",
            label=label,
            file_path=file_path,
        ),
        connection=_parse_connection(payload=mapping.get("connection"), file_path=file_path),
        variables=_parse_variables(
            payload=mapping.get("vars"),
            label=f"{label}.vars",
            file_path=file_path,
        ),
        audit_scheduler=_parse_audit_scheduler_override(
            payload=mapping.get("audit_scheduler"),
            label=f"{label}.audit_scheduler",
            file_path=file_path,
        ),
        build=_parse_build_config(
            payload=mapping.get("build"),
            label=f"{label}.build",
            file_path=file_path,
        ),
    )


def _parse_local_target(*, payload: object, label: str, file_path: Path) -> LocalProjectTarget:
    mapping: dict[str, object] = _target_mapping(
        payload=payload,
        label=label,
        file_path=file_path,
        allowed_keys=LOCAL_TARGET_KEYS,
    )
    return LocalProjectTarget(
        database=_optional_non_empty_string(
            mapping=mapping,
            key="database",
            label=label,
            file_path=file_path,
        ),
        connection=_parse_connection(payload=mapping.get("connection"), file_path=file_path),
        variables=_parse_variables(
            payload=mapping.get("vars"),
            label=f"{label}.vars",
            file_path=file_path,
        ),
        audit_scheduler=_parse_audit_scheduler_override(
            payload=mapping.get("audit_scheduler"),
            label=f"{label}.audit_scheduler",
            file_path=file_path,
        ),
    )


def _target_mapping(
    *, payload: object, label: str, file_path: Path, allowed_keys: frozenset[str]
) -> dict[str, object]:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label=label,
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=allowed_keys,
        label=label,
        file_path=file_path,
    )
    return mapping


def _parse_build_config(*, payload: object, label: str, file_path: Path) -> BuildConfig:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label=label,
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=BUILD_KEYS,
        label=label,
        file_path=file_path,
    )
    max_pipelines: object | None = mapping.get("max_pipelines")
    if max_pipelines is not None and (
        isinstance(max_pipelines, bool) or not isinstance(max_pipelines, int) or max_pipelines <= 0
    ):
        raise ProjectConfigError(f"{file_path} {label}.max_pipelines must be a positive integer")
    return BuildConfig(
        max_pipelines=max_pipelines if isinstance(max_pipelines, int) else None,
    )


def _parse_audit_scheduler_config(
    *, payload: object, label: str, file_path: Path
) -> AuditSchedulerConfig:
    override: AuditSchedulerOverride = _parse_audit_scheduler_override(
        payload=payload,
        label=label,
        file_path=file_path,
    )
    return AuditSchedulerConfig(enabled=bool(override.enabled))


def _parse_audit_scheduler_override(
    *, payload: object, label: str, file_path: Path
) -> AuditSchedulerOverride:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label=label,
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=AUDIT_SCHEDULER_KEYS,
        label=label,
        file_path=file_path,
    )
    enabled: object | None = mapping.get("enabled")
    if enabled is not None and not isinstance(enabled, bool):
        raise ProjectConfigError(f"{file_path} {label}.enabled must be a boolean")
    return AuditSchedulerOverride(enabled=enabled if isinstance(enabled, bool) else None)


def _parse_connection(*, payload: object, file_path: Path) -> RawConnectionConfig:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label="connection",
        file_path=file_path,
    )
    return RawConnectionConfig(values=tuple(sorted(mapping.items())))


def _parse_variables(
    *,
    payload: object,
    label: str,
    file_path: Path,
) -> tuple[tuple[str, object], ...]:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label=label,
        file_path=file_path,
    )
    return tuple(sorted(mapping.items()))


def _parse_project_defaults(*, payload: object, file_path: Path) -> ProjectDefaults:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label="defaults",
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=DEFAULTS_KEYS,
        label="defaults",
        file_path=file_path,
    )
    try:
        run_presumed_failed_after_seconds: int = parse_duration_seconds(
            value=mapping.get("run_presumed_failed_after", "10m"),
            field_path=f"{file_path} defaults.run_presumed_failed_after",
            allow_zero=False,
        )
    except ValueError as error:
        raise ProjectConfigError(str(error)) from error
    if run_presumed_failed_after_seconds <= RUN_UNRESPONSIVE_AFTER_SECONDS:
        raise ProjectConfigError(
            f"{file_path} defaults.run_presumed_failed_after must be longer than "
            f"{RUN_UNRESPONSIVE_AFTER_SECONDS}s"
        )
    return ProjectDefaults(
        managed_source_ttl=_optional_non_empty_string(
            mapping=mapping,
            key="managed_source_ttl",
            label="defaults",
            file_path=file_path,
        ),
        model_ttl=_optional_non_empty_string(
            mapping=mapping,
            key="model_ttl",
            label="defaults",
            file_path=file_path,
        ),
        kafka_broker_list=_optional_non_empty_string(
            mapping=mapping,
            key="kafka_broker_list",
            label="defaults",
            file_path=file_path,
        ),
        pipeline_mode=_parse_pipeline_mode(
            value=mapping.get(PIPELINE_MODE_KEY, PipelineMode.DIRECT),
            label="defaults.pipeline_mode",
            file_path=file_path,
        ),
        replay_on_change=_parse_replay_on_change(
            payload=mapping.get("replay_on_change"),
            label="defaults.replay_on_change",
            file_path=file_path,
        ),
        bounded_replay_fallback=_parse_bounded_replay_fallback(
            value=mapping.get("bounded_replay_fallback"),
            label="defaults.bounded_replay_fallback",
            file_path=file_path,
        ),
        run_presumed_failed_after_seconds=run_presumed_failed_after_seconds,
        freshness=parse_freshness_policy(
            payload=mapping.get("freshness"),
            label="defaults.freshness",
            file_path=file_path,
        ),
        audits=_parse_audit_defaults(
            payload=mapping.get("audits"),
            label="defaults.audits",
            file_path=file_path,
        ),
        deployment_readiness=_parse_deployment_readiness_defaults(
            payload=mapping.get("deployment_readiness"),
            file_path=file_path,
        ),
        sources=_parse_source_defaults(payload=mapping.get("sources"), file_path=file_path),
    )


def _parse_deployment_readiness_defaults(
    *, payload: object, file_path: Path
) -> DeploymentReadinessDefaults:
    label: str = "defaults.deployment_readiness"
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label=label,
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=DEPLOYMENT_READINESS_KEYS,
        label=label,
        file_path=file_path,
    )
    try:
        maximum_lag_seconds: float = float(
            parse_duration_seconds(
                value=mapping.get("maximum_lag", "30s"),
                field_path=f"{file_path} {label}.maximum_lag",
                allow_zero=True,
            )
        )
    except ValueError as error:
        raise ProjectConfigError(str(error)) from error
    ratio_value: object = mapping.get("minimum_staged_row_ratio", 0.5)
    if isinstance(ratio_value, bool) or not isinstance(ratio_value, (int, float)):
        raise ProjectConfigError(
            f"{file_path} {label}.minimum_staged_row_ratio must be a number from 0 to 1"
        )
    minimum_staged_row_ratio: float = float(ratio_value)
    if not 0.0 <= minimum_staged_row_ratio <= 1.0:
        raise ProjectConfigError(
            f"{file_path} {label}.minimum_staged_row_ratio must be a number from 0 to 1"
        )
    return DeploymentReadinessDefaults(
        maximum_lag_seconds=maximum_lag_seconds,
        minimum_staged_row_ratio=minimum_staged_row_ratio,
    )


def _parse_source_defaults(*, payload: object, file_path: Path) -> SourceDefaults:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label="defaults.sources",
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=SOURCE_DEFAULT_KEYS,
        label="defaults.sources",
        file_path=file_path,
    )
    kafka_mapping: dict[str, object] = _optional_mapping(
        payload=mapping.get("kafka"),
        label="defaults.sources.kafka",
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=kafka_mapping,
        allowed_keys=KAFKA_SOURCE_DEFAULT_KEYS,
        label="defaults.sources.kafka",
        file_path=file_path,
    )
    return SourceDefaults(
        kafka=KafkaSourceDefaults(
            naming_macro=_optional_non_empty_string(
                mapping=kafka_mapping,
                key="naming_macro",
                label="defaults.sources.kafka",
                file_path=file_path,
            )
        )
    )


def _parse_pipeline_mode(*, value: object, label: str, file_path: Path) -> PipelineMode:
    try:
        return PipelineMode(value)
    except (TypeError, ValueError) as error:
        raise ProjectConfigError(f"{file_path} {label} must be 'direct' or 'virtual'") from error


def _parse_audit_defaults(*, payload: object, label: str, file_path: Path) -> AuditDefaults:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label=label,
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=AUDIT_DEFAULT_KEYS,
        label=label,
        file_path=file_path,
    )
    severity_value: object | None = mapping.get("severity")
    if severity_value is not None and severity_value not in AUDIT_SEVERITIES:
        raise ProjectConfigError(f"{file_path} {label}.severity must be 'error' or 'warning'")
    try:
        cadence_seconds: int | None = (
            parse_duration_seconds(
                value=mapping[AUDIT_DEFAULT_EVERY_KEY],
                field_path=f"{file_path} {label}.every",
                allow_zero=False,
            )
            if AUDIT_DEFAULT_EVERY_KEY in mapping
            else None
        )
        warmup_seconds: int | None = (
            parse_duration_seconds(
                value=mapping[AUDIT_DEFAULT_WARMUP_KEY],
                field_path=f"{file_path} {label}.warmup",
                allow_zero=True,
            )
            if AUDIT_DEFAULT_WARMUP_KEY in mapping
            else None
        )
    except ValueError as error:
        raise ProjectConfigError(str(error)) from None
    return AuditDefaults(
        severity=str(severity_value) if severity_value is not None else None,
        cadence_seconds=cadence_seconds,
        warmup_seconds=warmup_seconds,
    )


def _parse_project_naming(*, payload: object, file_path: Path) -> ProjectNaming:
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label="naming",
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=NAMING_KEYS,
        label="naming",
        file_path=file_path,
    )
    defaults: ProjectNaming = ProjectNaming()
    return ProjectNaming(
        table_prefix=_optional_string_allowing_empty(
            mapping=mapping,
            key=NAMING_TABLE_PREFIX_KEY,
            label="naming",
            file_path=file_path,
        )
        if NAMING_TABLE_PREFIX_KEY in mapping
        else defaults.table_prefix,
        view_prefix=_optional_string_allowing_empty(
            mapping=mapping,
            key=NAMING_VIEW_PREFIX_KEY,
            label="naming",
            file_path=file_path,
        )
        if NAMING_VIEW_PREFIX_KEY in mapping
        else defaults.view_prefix,
    )


def _parse_replay_on_change(
    *, payload: object, label: str, file_path: Path
) -> ReplayOnChangePolicy | None:
    if payload is None:
        return None
    mapping: dict[str, object] = _optional_mapping(
        payload=payload,
        label=label,
        file_path=file_path,
    )
    _validate_allowed_keys(
        mapping=mapping,
        allowed_keys=frozenset({"breaking", "non_breaking"}),
        label=label,
        file_path=file_path,
    )
    return ReplayOnChangePolicy(
        breaking=_parse_replay_on_change_rule(
            value=mapping.get("breaking"),
            label=f"{label}.breaking",
            file_path=file_path,
        ),
        non_breaking=_parse_replay_on_change_rule(
            value=mapping.get("non_breaking"),
            label=f"{label}.non_breaking",
            file_path=file_path,
        ),
    )


def _parse_replay_on_change_rule(
    *, value: object, label: str, file_path: Path
) -> ReplayOnChangeRule | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProjectConfigError(f"{file_path} {label} must be a string")
    if value == FULL_REPLAY_POLICY_VALUE:
        return ReplayOnChangeRule(mode=ReplayOnChangeMode.FULL)
    bounded_match: re.Match[str] | None = re.fullmatch(r"bounded-(\d+)([dhms])", value)
    if bounded_match is None:
        raise ProjectConfigError(f"{file_path} {label} must be 'full' or 'bounded-<duration>'")
    return ReplayOnChangeRule(
        mode=ReplayOnChangeMode.BOUNDED,
        lookback_seconds=(
            int(bounded_match.group(1)) * SECONDS_BY_DURATION_UNIT[bounded_match.group(2)]
        ),
    )


def _parse_bounded_replay_fallback(
    *, value: object, label: str, file_path: Path
) -> BoundedReplayFallback | None:
    if value is None:
        return None
    if value == FULL_REPLAY_POLICY_VALUE:
        return BoundedReplayFallback.FULL
    if value == BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY:
        return BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY
    raise ProjectConfigError(f"{file_path} {label} must be 'full' or 'bounded_without_history'")


def _optional_mapping(*, payload: object, label: str, file_path: Path) -> dict[str, object]:
    if payload is None:
        return {}
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise ProjectConfigError(f"{file_path} {label} must be a mapping")
    mapping: dict[str, object] = cast(dict[str, object], payload)
    interpolated_keys: tuple[str, ...] = tuple(
        sorted(key for key in mapping if INTERPOLATION_TOKEN_START in key)
    )
    if interpolated_keys:
        raise ProjectConfigError(
            f"{file_path} {label} must not interpolate mapping keys: {', '.join(interpolated_keys)}"
        )
    return mapping


def _optional_string_allowing_empty(
    *, mapping: dict[str, object], key: str, label: str, file_path: Path
) -> str:
    value: object = mapping.get(key)
    if not isinstance(value, str):
        raise ProjectConfigError(f"{file_path} {label}.{key} must be a string")
    return value


def _require_non_empty_string(
    *, mapping: dict[str, object], key: str, label: str, file_path: Path
) -> str:
    value: str | None = _optional_non_empty_string(
        mapping=mapping,
        key=key,
        label=label,
        file_path=file_path,
    )
    if value is None:
        raise ProjectConfigError(f"{file_path} {label} must define non-empty string '{key}'")
    return value


def _require_project_name(*, mapping: dict[str, object], file_path: Path) -> str:
    name: str = _require_non_empty_string(
        mapping=mapping,
        key="name",
        label="project",
        file_path=file_path,
    )
    if INTERPOLATION_TOKEN_START in name:
        raise ProjectConfigError(
            f"{file_path} project.name must be a committed literal and cannot be interpolated"
        )
    return name


def _optional_non_empty_string(
    *, mapping: dict[str, object], key: str, label: str, file_path: Path
) -> str | None:
    value: object | None = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProjectConfigError(f"{file_path} {label}.{key} must be a non-empty string")
    return value.strip()


def _validate_allowed_keys(
    *,
    mapping: dict[str, object],
    allowed_keys: frozenset[str],
    label: str,
    file_path: Path,
) -> None:
    unknown_keys: tuple[str, ...] = tuple(sorted(set(mapping) - allowed_keys))
    if unknown_keys:
        raise ProjectConfigError(
            f"{file_path} {label} contains unsupported keys: {', '.join(unknown_keys)}"
        )
