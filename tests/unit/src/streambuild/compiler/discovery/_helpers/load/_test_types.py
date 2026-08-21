from dataclasses import dataclass

from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    PipelineMode,
    ReplayOnChangeMode,
)


@dataclass(frozen=True)
class LoadRegistryPipelineTestCase:
    description: str
    expected_pipeline_name: str
    expected_source_name: str
    expected_transform_names: tuple[str, ...]


@dataclass(frozen=True)
class LoadReplayPoliciesTestCase:
    description: str
    expected_pipeline_breaking_mode: ReplayOnChangeMode
    expected_pipeline_breaking_seconds: int
    expected_pipeline_non_breaking_mode: ReplayOnChangeMode
    expected_pipeline_fallback: BoundedReplayFallback
    expected_model_breaking_seconds: int
    expected_model_fallback: BoundedReplayFallback


@dataclass(frozen=True)
class PipelineProtectionTestCase:
    description: str
    pipeline_name: str
    pipeline_config_contents: str
    expected_warning: str
    expected_confirmation: str


@dataclass(frozen=True)
class InvalidPipelineProtectionTestCase:
    description: str
    confirmation: str
    expected_error_fragment: str


@dataclass(frozen=True)
class RemovedPipelineSurfaceTestCase:
    description: str
    pipeline_config_contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class MismatchedSourceTestCase:
    description: str
    model_source_name: str
    expected_error_fragment: str


@dataclass(frozen=True)
class StandaloneMacroOwnershipTestCase:
    description: str
    macro_contents: str
    expected_query: str


@dataclass(frozen=True)
class PipelineModeTestCase:
    description: str
    configured_mode: str
    expected_mode: PipelineMode


@dataclass(frozen=True)
class InvalidPipelineModeTestCase:
    description: str
    configured_mode: str
    expected_error_fragment: str


@dataclass(frozen=True)
class PipelineExecutionSettingsTestCase:
    description: str
    pipeline_config_contents: str
    expected_replay_settings: dict[str, str]
