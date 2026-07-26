from dataclasses import dataclass

from streambuild.compiler.planner.types import RebuildExecutionMode
from streambuild.spec.types import BoundedReplayFallback


@dataclass(frozen=True)
class FilterRootBackfillReportsForDeploymentTestCase:
    description: str
    expected_root_names: tuple[str, ...]


@dataclass(frozen=True)
class RenderOffsetReplayStatementTestCase:
    description: str
    source_table_name: str
    target_table_name: str
    shadow_target_name: str
    anchor_table_name: str
    query: str
    replay_table_name_by_logical_name: dict[str, str]
    expected_statement: str


@dataclass(frozen=True)
class ResolveUnsupportedBoundedReplayBehaviorTestCase:
    description: str
    bounded_replay_fallback: BoundedReplayFallback | str
    expected_execution_mode: RebuildExecutionMode
    expected_requested_start_time: str | None


@dataclass(frozen=True)
class CreateShadowObjectsOrderingTestCase:
    description: str
    expected_preceding_fragment: str
    expected_following_fragment: str
