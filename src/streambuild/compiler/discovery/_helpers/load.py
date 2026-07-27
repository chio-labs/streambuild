"""Pipeline loading helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml

from streambuild.compiler.compile.main._extract_refs import extract_refs
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
    FULL_REPLAY_POLICY_VALUE,
    PIPELINE_FILE_NAME,
    PIPELINE_KEYS,
    PIPELINE_NAME_KEY,
    PYTHON_PACKAGE_INITIALIZER_FILE_NAME,
    SCHEMA_CHANGE_RULE_KEYS,
    SECONDS_BY_DURATION_UNIT,
)
from streambuild.compiler.discovery.exceptions import PipelineDiscoveryError
from streambuild.compiler.discovery.models import (
    DiscoveredProjectFile,
    EffectiveProjectConfiguration,
    ExternalTableSourceStep,
    KafkaLandingStep,
    LoadedPipeline,
    Pipeline,
    Project,
    ReplayOnChangePolicy,
    ReplayOnChangeRule,
    TransformStep,
)
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    ReplayOnChangeMode,
    SqlRelationType,
)
from streambuild.compiler.macros.main._build_macro_context import build_macro_context
from streambuild.compiler.macros.main._load_macro_registry import load_macro_registry
from streambuild.compiler.macros.models import MacroContext, MacroRegistry


def load_pipeline_file(file_path: Path) -> LoadedPipeline:
    """Load one pipeline through the TOML project and standalone source registry."""

    project_dir: Path | None = find_project_configuration_dir(file_path)
    if project_dir is None:
        raise PipelineDiscoveryError(
            f"Pipeline file '{file_path}' is not inside a streambuild_project.toml project"
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
            )
        )
    )
    macro_registry: MacroRegistry = load_macro_registry(
        macro_files=_discovered_macro_files(project_dir)
    )
    macro_context: MacroContext = build_macro_context(
        adapter_name=effective.adapter,
        dialect="clickhouse",
        target_name=effective.target_name,
        database=effective.database,
        schema=None,
        virtual_environments=effective.settings.virtual_environments,
        variables=dict(effective.variables),
    )
    pipeline: Pipeline = load_pipeline_yaml(
        file_path=file_path,
        sources_by_name=sources_by_name,
        macro_registry=macro_registry,
        macro_context=macro_context,
    )
    loaded_pipeline: LoadedPipeline = LoadedPipeline(
        pipeline=pipeline,
        file_path=file_path,
        project=Project(
            replay_on_change=effective.defaults.replay_on_change,
            bounded_replay_fallback=effective.defaults.bounded_replay_fallback,
            default_database=effective.database,
            adapter=effective.adapter,
        ),
    )
    validate_replay_policies_for_mode(
        virtual_environments=effective.settings.virtual_environments,
        project=loaded_pipeline.project,
        project_file_path=project_dir / "streambuild_project.toml",
        loaded_pipelines=(loaded_pipeline,),
    )
    return loaded_pipeline


def load_pipeline_yaml(
    *,
    file_path: Path,
    contents: str | None = None,
    model_contents_by_path: Mapping[Path, str] | None = None,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
    sources_by_name: Mapping[str, KafkaLandingStep | ExternalTableSourceStep] | None = None,
) -> Pipeline:
    """Load one authored pipeline folder rooted at `pipeline.yml`."""

    if file_path.name != PIPELINE_FILE_NAME:
        raise PipelineDiscoveryError(f"Pipeline file '{file_path}' must be named 'pipeline.yml'")
    source_contents: str = file_path.read_text(encoding="utf-8") if contents is None else contents
    pipeline_values: object = yaml.safe_load(source_contents)
    if not isinstance(pipeline_values, dict) or not all(
        isinstance(key, str) for key in pipeline_values
    ):
        raise PipelineDiscoveryError(f"Pipeline file '{file_path}' must define a top-level mapping")
    typed_pipeline_values: dict[str, Any] = pipeline_values
    unknown_keys: list[str] = [key for key in typed_pipeline_values if key not in PIPELINE_KEYS]
    if unknown_keys:
        raise PipelineDiscoveryError(
            f"Pipeline file '{file_path}' contains unsupported keys: "
            f"{', '.join(sorted(unknown_keys))}"
        )

    pipeline_root: Path = file_path.parent
    if PIPELINE_NAME_KEY in typed_pipeline_values:
        raise PipelineDiscoveryError(
            f"Pipeline file '{file_path}' must not define 'name'; pipeline name is inferred "
            f"from folder '{pipeline_root.name}'"
        )
    nested_pipeline_files: list[Path] = sorted(
        nested_file
        for nested_file in pipeline_root.rglob(PIPELINE_FILE_NAME)
        if nested_file != file_path
    )
    if nested_pipeline_files:
        nested_file_list: str = ", ".join(str(path) for path in nested_pipeline_files)
        raise PipelineDiscoveryError(
            f"Pipeline root '{pipeline_root}' must not contain nested pipeline.yml files: "
            f"{nested_file_list}"
        )

    source: KafkaLandingStep | ExternalTableSourceStep = _resolve_pipeline_source(
        pipeline_values=typed_pipeline_values,
        file_path=file_path,
        sources_by_name=sources_by_name,
    )
    transforms: list[TransformStep] = _load_pipeline_transforms(
        pipeline_root=pipeline_root,
        model_contents_by_path=model_contents_by_path,
        macro_registry=macro_registry,
        macro_context=macro_context,
    )
    _validate_source_references(
        source_name=source.name,
        transforms=transforms,
        file_path=file_path,
    )
    return Pipeline(
        name=pipeline_root.name,
        source=source,
        transforms=transforms,
        replay_on_change=_load_replay_on_change(
            value=typed_pipeline_values.get("replay_on_change"),
            file_path=file_path,
        ),
        bounded_replay_fallback=_load_bounded_replay_fallback(
            value=typed_pipeline_values.get("bounded_replay_fallback"),
            file_path=file_path,
        ),
    )


def _resolve_pipeline_source(
    *,
    pipeline_values: dict[str, Any],
    file_path: Path,
    sources_by_name: Mapping[str, KafkaLandingStep | ExternalTableSourceStep] | None,
) -> KafkaLandingStep | ExternalTableSourceStep:
    source_name: object = pipeline_values.get("source")
    if not isinstance(source_name, str) or not source_name:
        raise PipelineDiscoveryError(
            f"Pipeline file '{file_path}' must define source as one non-empty registry name"
        )
    if sources_by_name is None:
        raise PipelineDiscoveryError(
            f"Pipeline file '{file_path}' requires a project sources/*.yml registry"
        )
    source: KafkaLandingStep | ExternalTableSourceStep | None = sources_by_name.get(source_name)
    if source is None:
        raise PipelineDiscoveryError(
            f"Pipeline file '{file_path}' references unknown source '{source_name}'"
        )
    return source


def _load_replay_on_change(*, value: object, file_path: Path) -> ReplayOnChangePolicy | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise PipelineDiscoveryError(
            f"Pipeline file '{file_path}' must define replay_on_change as a mapping"
        )
    typed_value: dict[str, object] = cast(dict[str, object], value)
    unknown_keys: list[str] = [key for key in typed_value if key not in SCHEMA_CHANGE_RULE_KEYS]
    if unknown_keys:
        raise PipelineDiscoveryError(
            f"Pipeline file '{file_path}' contains unsupported replay_on_change keys: "
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
            f"Pipeline file '{file_path}' must define replay_on_change.{key} as a string"
        )
    if value == FULL_REPLAY_POLICY_VALUE:
        return ReplayOnChangeRule(mode=ReplayOnChangeMode.FULL)
    bounded_match: re.Match[str] | None = re.fullmatch(r"bounded-(\d+)([dhms])", value)
    if bounded_match is None:
        raise PipelineDiscoveryError(
            f"Pipeline file '{file_path}' must define replay_on_change.{key} as 'full' "
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
            f"Pipeline file '{file_path}' has unsupported bounded_replay_fallback '{value}'; "
            "expected 'full' or 'bounded_without_history'"
        ) from error


def _load_pipeline_transforms(
    *,
    pipeline_root: Path,
    model_contents_by_path: Mapping[Path, str] | None = None,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
) -> list[TransformStep]:
    model_file_paths: list[Path] = sorted(pipeline_root.rglob("*.sql"))
    if not model_file_paths:
        raise PipelineDiscoveryError(
            f"Pipeline root '{pipeline_root}' must contain at least one SQL model file"
        )
    transforms: list[TransformStep] = []
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
    return transforms


def _discovered_macro_files(project_dir: Path) -> tuple[DiscoveredProjectFile, ...]:
    macro_files: list[DiscoveredProjectFile] = []
    macro_path: Path
    for macro_path in sorted((project_dir / "macros").rglob("*.py")):
        relative_path: Path = macro_path.relative_to(project_dir)
        if macro_path.name == PYTHON_PACKAGE_INITIALIZER_FILE_NAME or any(
            part.startswith("_") for part in relative_path.parts
        ):
            continue
        macro_files.append(
            DiscoveredProjectFile(
                file_path=macro_path,
                relative_path=relative_path,
                contents=macro_path.read_text(encoding="utf-8"),
            )
        )
    return tuple(macro_files)


def _validate_source_references(
    *, source_name: str, transforms: list[TransformStep], file_path: Path
) -> None:
    transform: TransformStep
    for transform in transforms:
        referenced_source_names: set[str] = {
            parsed_ref.name
            for parsed_ref in extract_refs(
                sql=transform.query or "",
                source_path=transform.source_file_path or file_path,
                source_line=transform.source_line,
                source_column=transform.source_column,
            )
            if parsed_ref.relation_type == SqlRelationType.SOURCE
        }
        if referenced_source_names and referenced_source_names != {source_name}:
            raise PipelineDiscoveryError(
                f"Pipeline file '{file_path}' selects source '{source_name}', but model "
                f"'{transform.name}' references driving source "
                f"'{', '.join(sorted(referenced_source_names))}'"
            )


def updated_unique_logical_names(
    *,
    loaded_pipeline: LoadedPipeline,
    logical_node_names: dict[str, Path],
) -> dict[str, Path]:
    """Return the logical-name registry after validating one loaded pipeline."""

    for logical_name in [transform.name for transform in loaded_pipeline.pipeline.transforms]:
        existing_path: Path | None = logical_node_names.get(logical_name)
        if existing_path is not None:
            raise PipelineDiscoveryError(
                "Logical node name "
                f"'{logical_name}' is defined in both "
                f"'{existing_path}' and '{loaded_pipeline.file_path}'"
            )
        logical_node_names[logical_name] = loaded_pipeline.file_path
    return logical_node_names
