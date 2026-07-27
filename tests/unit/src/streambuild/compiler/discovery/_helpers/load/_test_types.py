from dataclasses import dataclass

from streambuild.compiler.discovery.types import BoundedReplayFallback, ReplayOnChangeMode


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
class RemovedPipelineSurfaceTestCase:
    description: str
    pipeline_contents: str
    expected_error_fragment: str


@dataclass(frozen=True)
class MismatchedSourceTestCase:
    description: str
    model_source_name: str
    expected_error_fragment: str
