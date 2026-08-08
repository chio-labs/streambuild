"""Pipeline loading helpers."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from streambuild.compiler.discovery._helpers.configuration import (
    find_project_configuration_dir,
    load_project_configuration,
)
from streambuild.compiler.discovery._helpers.effective_configuration import (
    resolve_effective_project_configuration,
)
from streambuild.compiler.discovery._helpers.model_sql import load_transform_from_sql_file
from streambuild.compiler.discovery._helpers.replay_policy_validation import (
    validate_replay_policies_for_mode,
)
from streambuild.compiler.discovery._helpers.source_registry import (
    discover_source_registry,
    source_registry_by_name,
)
from streambuild.compiler.discovery.constants import (
    AUDIT_DEFAULT_EVERY_KEY,
    AUDIT_DEFAULT_KEYS,
    AUDIT_DEFAULT_WARMUP_KEY,
    AUDIT_SEVERITIES,
    FULL_REPLAY_POLICY_VALUE,
    NAMING_KEYS,
    PIPELINE_CONFIG_FILE_NAME,
    PIPELINE_CONFIG_KEYS,
    PROTECTION_CONFIRMATION_PATTERN,
    PROTECTION_CONFIRMATION_UNSAFE_PATTERN,
    PROTECTION_KEYS,
    SCHEMA_CHANGE_RULE_KEYS,
    SECONDS_BY_DURATION_UNIT,
)
from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.main._parse_duration_seconds import parse_duration_seconds
from streambuild.compiler.discovery.models import (
    AuditDefaults,
    DiscoveredPipelineDirectory,
    DiscoveredProjectFile,
    EffectiveProjectConfiguration,
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedPipeline,
    Pipeline,
    PipelineNaming,
    PipelineProtection,
    Project,
    ReplayOnChangePolicy,
    ReplayOnChangeRule,
    TransformStep,
    ViewStep,
)
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    PipelineMode,
    ReplayOnChangeMode,
)
from streambuild.compiler.macros.models import MacroContext, MacroRegistry


@dataclass(frozen=True)
class _PipelineDraft:
    pipeline_dir: Path
    config_path: Path
    transforms: tuple[TransformStep | ViewStep, ...]
    mode: PipelineMode
    replay_on_change: ReplayOnChangePolicy | None
    bounded_replay_fallback: BoundedReplayFallback | None
    naming: PipelineNaming
    protection: PipelineProtection | None
    audit_defaults: AuditDefaults


def load_pipeline_directory(pipeline_dir: Path) -> LoadedPipeline:
    """Load one pipeline directory without the project compiler's macro expansion phase."""

    project_dir: Path | None = find_project_configuration_dir(pipeline_dir)
    if project_dir is None:
        raise PipelineDiscoveryError(
            f"Pipeline directory '{pipeline_dir}' is not inside a streambuild_project.toml project"
        )
    effective: EffectiveProjectConfiguration = resolve_effective_project_configuration(
        loaded=load_project_configuration(project_dir=project_dir),
        selected_target=None,
        cli_variables={},
        environment={},
    )
    sources_by_name: dict[str, KafkaLandingStep | ExternalTableSourceStep] = (
        source_registry_by_name(
            discover_source_registry(
                project_dir=project_dir,
                variables=dict(effective.variables),
                environment={},
                default_managed_source_ttl=effective.defaults.managed_source_ttl,
                default_kafka_broker_list=effective.defaults.kafka_broker_list,
                default_freshness=effective.defaults.freshness,
            )
        )
    )
    config_path: Path = pipeline_dir / PIPELINE_CONFIG_FILE_NAME
    config_file: DiscoveredProjectFile | None = (
        DiscoveredProjectFile(
            file_path=config_path,
            relative_path=config_path.relative_to(project_dir),
            contents=config_path.read_text(encoding="utf-8"),
        )
        if config_path.is_file()
        else None
    )
    pipeline: Pipeline = load_pipeline_directories(
        pipeline_directories=(
            DiscoveredPipelineDirectory(
                pipeline_dir=pipeline_dir,
                config_file=config_file,
            ),
        ),
        sources_by_name=sources_by_name,
        default_mode=PipelineMode(effective.defaults.pipeline_mode),
    )[0]
    loaded_pipeline: LoadedPipeline = LoadedPipeline(
        pipeline=pipeline,
        file_path=pipeline_dir,
        project=Project(
            replay_on_change=effective.defaults.replay_on_change,
            bounded_replay_fallback=effective.defaults.bounded_replay_fallback,
            model_ttl=effective.defaults.model_ttl,
            default_database=effective.database,
            adapter=effective.adapter,
            naming=effective.naming,
            audit_defaults=effective.defaults.audits,
            audit_scheduler=effective.audit_scheduler,
        ),
    )
    validate_replay_policies_for_mode(
        default_pipeline_mode=PipelineMode(effective.defaults.pipeline_mode),
        project=loaded_pipeline.project,
        project_file_path=project_dir / "streambuild_project.toml",
        loaded_pipelines=(loaded_pipeline,),
    )
    return loaded_pipeline


def load_pipeline_directories(
    *,
    pipeline_directories: tuple[DiscoveredPipelineDirectory, ...],
    model_contents_by_path: Mapping[Path, str] | None = None,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
    sources_by_name: Mapping[str, KafkaLandingStep | ExternalTableSourceStep],
    default_mode: PipelineMode = PipelineMode.DIRECT,
) -> tuple[Pipeline, ...]:
    """Load pipeline directories and infer each source from driving-input chains."""

    drafts: tuple[_PipelineDraft, ...] = tuple(
        _load_pipeline_draft(
            pipeline_directory=pipeline_directory,
            model_contents_by_path=model_contents_by_path,
            macro_registry=macro_registry,
            macro_context=macro_context,
            default_mode=default_mode,
        )
        for pipeline_directory in pipeline_directories
    )
    transforms_by_name: dict[str, TransformStep] = _transforms_by_name(drafts=drafts)
    source_names_by_transform: dict[str, str] = {}
    pipelines: list[Pipeline] = []
    draft: _PipelineDraft
    for draft in drafts:
        pipeline_source: KafkaLandingStep | ExternalTableSourceStep | None
        pipeline_source, source_names_by_transform = _infer_pipeline_source(
            draft=draft,
            transforms_by_name=transforms_by_name,
            sources_by_name=sources_by_name,
            source_names_by_transform=source_names_by_transform,
        )
        pipelines.append(
            Pipeline(
                name=draft.pipeline_dir.name,
                source=pipeline_source,
                transforms=draft.transforms,
                mode=draft.mode,
                replay_on_change=draft.replay_on_change,
                bounded_replay_fallback=draft.bounded_replay_fallback,
                naming=draft.naming,
                protection=draft.protection,
                audit_defaults=draft.audit_defaults,
            )
        )
    return tuple(pipelines)


def _load_pipeline_draft(
    *,
    pipeline_directory: DiscoveredPipelineDirectory,
    model_contents_by_path: Mapping[Path, str] | None,
    macro_registry: MacroRegistry | None,
    macro_context: MacroContext | None,
    default_mode: PipelineMode,
) -> _PipelineDraft:
    pipeline_values: dict[str, object] = _load_pipeline_config(
        pipeline_directory=pipeline_directory
    )
    config_path: Path = (
        pipeline_directory.pipeline_dir / PIPELINE_CONFIG_FILE_NAME
        if pipeline_directory.config_file is None
        else pipeline_directory.config_file.file_path
    )
    mode: PipelineMode = _load_pipeline_mode(
        value=pipeline_values.get("mode"),
        default=default_mode,
        file_path=config_path,
    )
    effective_macro_context: MacroContext | None = (
        macro_context
        if macro_context is None
        or macro_context.virtual_environments == (mode == PipelineMode.VIRTUAL)
        else replace(
            macro_context,
            virtual_environments=mode == PipelineMode.VIRTUAL,
        )
    )
    transforms: tuple[TransformStep | ViewStep, ...] = _load_pipeline_transforms(
        pipeline_root=pipeline_directory.pipeline_dir,
        model_contents_by_path=model_contents_by_path,
        macro_registry=macro_registry,
        macro_context=effective_macro_context,
    )
    return _PipelineDraft(
        pipeline_dir=pipeline_directory.pipeline_dir,
        config_path=config_path,
        transforms=transforms,
        mode=mode,
        replay_on_change=_load_replay_on_change(
            value=pipeline_values.get("replay_on_change"),
            file_path=config_path,
        ),
        bounded_replay_fallback=_load_bounded_replay_fallback(
            value=pipeline_values.get("bounded_replay_fallback"),
            file_path=config_path,
        ),
        naming=_load_pipeline_naming(
            value=pipeline_values.get("naming"),
            file_path=config_path,
        ),
        protection=_load_pipeline_protection(
            value=pipeline_values.get("protection"),
            pipeline_name=pipeline_directory.pipeline_dir.name,
            file_path=config_path,
        ),
        audit_defaults=_load_pipeline_audit_defaults(
            value=pipeline_values.get("audit_defaults"),
            file_path=config_path,
        ),
    )


def _load_pipeline_config(*, pipeline_directory: DiscoveredPipelineDirectory) -> dict[str, object]:
    config_file: DiscoveredProjectFile | None = pipeline_directory.config_file
    if config_file is None:
        return {}
    try:
        pipeline_values: dict[str, object] = tomllib.loads(config_file.contents)
    except tomllib.TOMLDecodeError as error:
        raise PipelineDiscoveryError(
            f"Pipeline config '{config_file.file_path}' contains invalid TOML: {error}"
        ) from error
    unknown_keys: list[str] = [key for key in pipeline_values if key not in PIPELINE_CONFIG_KEYS]
    if unknown_keys:
        raise PipelineDiscoveryError(
            f"Pipeline config '{config_file.file_path}' contains unsupported keys: "
            f"{', '.join(sorted(unknown_keys))}"
        )
    return pipeline_values


def _load_pipeline_mode(*, value: object, default: PipelineMode, file_path: Path) -> PipelineMode:
    if value is None:
        return default
    if not isinstance(value, str):
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' must define mode as 'direct' or 'virtual'"
        )
    try:
        return PipelineMode(value)
    except ValueError as error:
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' has unsupported mode '{value}'; "
            "expected 'direct' or 'virtual'"
        ) from error


def _transforms_by_name(*, drafts: tuple[_PipelineDraft, ...]) -> dict[str, TransformStep]:
    transforms_by_name: dict[str, TransformStep] = {}
    transform_paths_by_name: dict[str, Path] = {}
    draft: _PipelineDraft
    for draft in drafts:
        model: TransformStep | ViewStep
        for model in draft.transforms:
            existing_path: Path | None = transform_paths_by_name.get(model.name)
            if existing_path is not None:
                raise PipelineDiscoveryError(
                    f"Logical node name '{model.name}' is defined in both "
                    f"'{existing_path}' and '{model.source_file_path}'"
                )
            if isinstance(model, TransformStep):
                transforms_by_name[model.name] = model
            transform_paths_by_name[model.name] = model.source_file_path or draft.pipeline_dir
    return transforms_by_name


def _infer_pipeline_source(
    *,
    draft: _PipelineDraft,
    transforms_by_name: Mapping[str, TransformStep],
    sources_by_name: Mapping[str, KafkaLandingStep | ExternalTableSourceStep],
    source_names_by_transform: Mapping[str, str],
) -> tuple[KafkaLandingStep | ExternalTableSourceStep | None, dict[str, str]]:
    resolved_source_names: dict[str, str] = dict(source_names_by_transform)
    source_names: set[str] = set()
    transform: TransformStep
    for model in draft.transforms:
        if isinstance(model, ViewStep):
            continue
        transform: TransformStep = model
        source_name: str
        resolved_transform_names: tuple[str, ...]
        source_name, resolved_transform_names = _source_name_for_transform(
            transform=transform,
            transforms_by_name=transforms_by_name,
            sources_by_name=sources_by_name,
            source_names_by_transform=resolved_source_names,
            pipeline_dir=draft.pipeline_dir,
        )
        source_names.add(source_name)
        resolved_transform_name: str
        for resolved_transform_name in resolved_transform_names:
            resolved_source_names[resolved_transform_name] = source_name
    if not source_names:
        return None, resolved_source_names
    if len(source_names) != 1:
        raise PipelineDiscoveryError(
            f"Pipeline directory '{draft.pipeline_dir}' must resolve to exactly one source; "
            f"found {', '.join(sorted(source_names))}"
        )
    return sources_by_name[next(iter(source_names))], resolved_source_names


def _source_name_for_transform(
    *,
    transform: TransformStep,
    transforms_by_name: Mapping[str, TransformStep],
    sources_by_name: Mapping[str, KafkaLandingStep | ExternalTableSourceStep],
    source_names_by_transform: Mapping[str, str],
    pipeline_dir: Path,
) -> tuple[str, tuple[str, ...]]:
    path: list[str] = []
    visiting: set[str] = set()
    current_transform: TransformStep = transform
    source_name: str
    while True:
        cached_source_name: str | None = source_names_by_transform.get(current_transform.name)
        if cached_source_name is not None:
            source_name = cached_source_name
            break
        if current_transform.name in visiting:
            cycle_names: str = ", ".join(sorted(visiting))
            raise PipelineDiscoveryError(
                f"Pipeline directory '{pipeline_dir}' has a driving-input cycle: {cycle_names}"
            )
        visiting.add(current_transform.name)
        path.append(current_transform.name)
        input_name: str = current_transform.source
        if input_name in sources_by_name:
            source_name = input_name
            break
        next_transform: TransformStep | None = transforms_by_name.get(input_name)
        if next_transform is None:
            raise PipelineDiscoveryError(
                f"Pipeline directory '{pipeline_dir}' references unknown driving input "
                f"'{input_name}'"
            )
        current_transform = next_transform
    return source_name, tuple(path)


def _load_replay_on_change(*, value: object, file_path: Path) -> ReplayOnChangePolicy | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' must define replay_on_change as a mapping"
        )
    typed_value: dict[str, object] = cast(dict[str, object], value)
    unknown_keys: list[str] = [key for key in typed_value if key not in SCHEMA_CHANGE_RULE_KEYS]
    if unknown_keys:
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' contains unsupported replay_on_change keys: "
            f"{', '.join(sorted(unknown_keys))}"
        )
    return ReplayOnChangePolicy(
        breaking=_load_replay_on_change_rule(
            value=typed_value.get("breaking"), key="breaking", file_path=file_path
        ),
        non_breaking=_load_replay_on_change_rule(
            value=typed_value.get("non_breaking"), key="non_breaking", file_path=file_path
        ),
    )


def _load_replay_on_change_rule(
    *, value: object, key: str, file_path: Path
) -> ReplayOnChangeRule | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' must define replay_on_change.{key} as a string"
        )
    if value == FULL_REPLAY_POLICY_VALUE:
        return ReplayOnChangeRule(mode=ReplayOnChangeMode.FULL)
    bounded_match: re.Match[str] | None = re.fullmatch(r"bounded-(\d+)([dhms])", value)
    if bounded_match is None:
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' must define replay_on_change.{key} as 'full' "
            "or 'bounded-<duration>'"
        )
    return ReplayOnChangeRule(
        mode=ReplayOnChangeMode.BOUNDED,
        lookback_seconds=(
            int(bounded_match.group(1)) * SECONDS_BY_DURATION_UNIT[bounded_match.group(2)]
        ),
    )


def _load_bounded_replay_fallback(
    *, value: object, file_path: Path
) -> BoundedReplayFallback | None:
    if value is None:
        return None
    try:
        return BoundedReplayFallback(value)
    except ValueError as error:
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' has unsupported bounded_replay_fallback '{value}'; "
            "expected 'full' or 'bounded_without_history'"
        ) from error


def _load_pipeline_naming(*, value: object, file_path: Path) -> PipelineNaming:
    if value is None:
        return PipelineNaming()
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' must define naming as a mapping"
        )
    typed_value: dict[str, object] = cast(dict[str, object], value)
    unknown_keys: list[str] = [key for key in typed_value if key not in NAMING_KEYS]
    if unknown_keys:
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' contains unsupported naming keys: "
            f"{', '.join(sorted(unknown_keys))}"
        )
    return PipelineNaming(
        table_prefix=_pipeline_prefix(
            values=typed_value,
            key="table_prefix",
            file_path=file_path,
        ),
        view_prefix=_pipeline_prefix(
            values=typed_value,
            key="view_prefix",
            file_path=file_path,
        ),
    )


def _pipeline_prefix(*, values: dict[str, object], key: str, file_path: Path) -> str | None:
    value: object = values.get(key)
    if value is None and key not in values:
        return None
    if not isinstance(value, str):
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' must define naming.{key} as a string"
        )
    return value


def _load_pipeline_protection(
    *, value: object, pipeline_name: str, file_path: Path
) -> PipelineProtection | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' must define protection as a mapping"
        )
    typed_value: dict[str, object] = cast(dict[str, object], value)
    unknown_keys: list[str] = [key for key in typed_value if key not in PROTECTION_KEYS]
    if unknown_keys:
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' contains unsupported protection keys: "
            f"{', '.join(sorted(unknown_keys))}"
        )
    default_warning: str = (
        f"Pipeline '{pipeline_name}' is protected. Confirm its operational impact before building."
    )
    warning: str = _protection_string(
        values=typed_value,
        key="warning",
        default=default_warning,
        file_path=file_path,
    )
    confirmation: str = _protection_string(
        values=typed_value,
        key="confirmation",
        default=_default_protection_confirmation(pipeline_name=pipeline_name),
        file_path=file_path,
    )
    if PROTECTION_CONFIRMATION_PATTERN.fullmatch(confirmation) is None:
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' protection.confirmation must contain only letters, "
            "numbers, '.', '_', ':', or '-' and must start with a letter or number"
        )
    return PipelineProtection(warning=warning, confirmation=confirmation)


def _load_pipeline_audit_defaults(*, value: object, file_path: Path) -> AuditDefaults:
    if value is None:
        return AuditDefaults()
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' must define audit_defaults as a mapping"
        )
    values: dict[str, object] = cast(dict[str, object], value)
    unknown_keys: list[str] = [key for key in values if key not in AUDIT_DEFAULT_KEYS]
    if unknown_keys:
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' contains unsupported audit_defaults keys: "
            f"{', '.join(sorted(unknown_keys))}"
        )
    severity_value: object | None = values.get("severity")
    if severity_value is not None and severity_value not in AUDIT_SEVERITIES:
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' audit_defaults.severity must be 'error' or 'warning'"
        )
    try:
        cadence_seconds: int | None = (
            parse_duration_seconds(
                value=values[AUDIT_DEFAULT_EVERY_KEY],
                field_path=f"Pipeline config '{file_path}' audit_defaults.every",
                allow_zero=False,
            )
            if AUDIT_DEFAULT_EVERY_KEY in values
            else None
        )
        warmup_seconds: int | None = (
            parse_duration_seconds(
                value=values[AUDIT_DEFAULT_WARMUP_KEY],
                field_path=f"Pipeline config '{file_path}' audit_defaults.warmup",
                allow_zero=True,
            )
            if AUDIT_DEFAULT_WARMUP_KEY in values
            else None
        )
    except ValueError as error:
        raise PipelineDiscoveryError(str(error)) from None
    return AuditDefaults(
        severity=str(severity_value) if severity_value is not None else None,
        cadence_seconds=cadence_seconds,
        warmup_seconds=warmup_seconds,
    )


def _default_protection_confirmation(*, pipeline_name: str) -> str:
    if PROTECTION_CONFIRMATION_PATTERN.fullmatch(pipeline_name) is not None:
        return pipeline_name
    sanitized_name: str = PROTECTION_CONFIRMATION_UNSAFE_PATTERN.sub("_", pipeline_name)
    return f"CONFIRM_{sanitized_name}"


def _protection_string(
    *, values: dict[str, object], key: str, default: str, file_path: Path
) -> str:
    value: object = values.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise PipelineDiscoveryError(
            f"Pipeline config '{file_path}' must define protection.{key} as a non-empty string"
        )
    return value


def _load_pipeline_transforms(
    *,
    pipeline_root: Path,
    model_contents_by_path: Mapping[Path, str] | None = None,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
) -> tuple[TransformStep | ViewStep, ...]:
    model_file_paths: list[Path] = sorted(pipeline_root.rglob("*.sql"))
    if not model_file_paths:
        raise PipelineDiscoveryError(
            f"Pipeline root '{pipeline_root}' must contain at least one SQL model file"
        )
    transforms: list[TransformStep | ViewStep] = []
    model_paths_by_name: dict[str, Path] = {}
    model_file_path: Path
    for model_file_path in model_file_paths:
        existing_path: Path | None = model_paths_by_name.get(model_file_path.stem)
        if existing_path is not None:
            raise PipelineDiscoveryError(
                f"Pipeline root '{pipeline_root}' defines duplicate model filename stem "
                f"'{model_file_path.stem}' in both '{existing_path}' and '{model_file_path}'"
            )
        model_paths_by_name[model_file_path.stem] = model_file_path
        transforms.append(
            load_transform_from_sql_file(
                file_path=model_file_path,
                contents=(
                    None
                    if model_contents_by_path is None
                    else model_contents_by_path[model_file_path]
                ),
                macro_registry=macro_registry,
                macro_context=macro_context,
            )
        )
    return tuple(transforms)
