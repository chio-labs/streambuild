from dataclasses import dataclass

from streambuild.adapter.types import AdapterReplayLowerBoundMode, AdapterReplaySeedMode
from streambuild.compiler.discovery.types import BoundedReplayFallback, ReplayLineageMode
from streambuild.compiler.planner.types import RebuildExecutionMode


@dataclass(frozen=True)
class FilterRootBackfillReportsForDeploymentTestCase:
    description: str
    expected_root_names: tuple[str, ...]


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


@dataclass(frozen=True)
class ManagedSourceCapabilityTestCase:
    description: str
    expected_error_message: str
    expected_warehouse_interaction_count: int


@dataclass(frozen=True)
class ReplayRequestConstructionTestCase:
    description: str
    source_ownership: str
    replay_mode: ReplayLineageMode
    boundary_key: str
    cutoff_value: str
    expected_partition_value: str | None
    expected_anchor_name: str
    expected_partition_column: str
    expected_offset_column: str
    expected_timestamp_column: str
    expected_cursor_column: str
    expected_cutoff_inclusive: bool
    expected_lower_bound_inclusive: bool
    execution_mode: RebuildExecutionMode
    expected_seed_mode: AdapterReplaySeedMode
    expected_lower_bound_mode: AdapterReplayLowerBoundMode


@dataclass(frozen=True)
class ReplayBoundaryCapabilityTestCase:
    description: str
    expected_error_message: str
    expected_warehouse_interaction_count: int


@dataclass(frozen=True)
class HistoryPrefixCapabilityTestCase:
    description: str
    expected_error_message: str
    expected_write_count: int
