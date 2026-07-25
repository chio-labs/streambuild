import pytest

from streambuild.compiler.planner.constants import (
    REBUILD_EXECUTION_MODE_FULL,
    REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
    REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
    REBUILD_STRATEGY_SHADOW,
)
from streambuild.compiler.planner.models import RebuildSubtree
from streambuild.compiler.shared.models import ObjectKey
from streambuild.executor.backfill._helpers.behavior import (
    resolve_subtree_behavior_from_support,
)
from tests.unit.src.streambuild.executor.backfill._helpers._test_types import (
    ResolveUnsupportedBoundedReplayBehaviorTestCase,
)

RESOLVE_UNSUPPORTED_BOUNDED_REPLAY_BEHAVIOR_TEST_CASES: list[
    ResolveUnsupportedBoundedReplayBehaviorTestCase
] = [
    ResolveUnsupportedBoundedReplayBehaviorTestCase(
        description="policy full resolves unsupported bounded replay to full rebuild",
        bounded_replay_fallback="full_refresh",
        expected_execution_mode=REBUILD_EXECUTION_MODE_FULL,
        expected_requested_start_time="2026-04-09 15:00:00.000",
    ),
    ResolveUnsupportedBoundedReplayBehaviorTestCase(
        description="policy window only resolves unsupported bounded replay to unseeded bounded",
        bounded_replay_fallback="bounded_without_history",
        expected_execution_mode=REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
        expected_requested_start_time=None,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    RESOLVE_UNSUPPORTED_BOUNDED_REPLAY_BEHAVIOR_TEST_CASES,
    ids=[case.description for case in RESOLVE_UNSUPPORTED_BOUNDED_REPLAY_BEHAVIOR_TEST_CASES],
)
def test_given_missing_active_lineage_when_resolving_then_it_applies_policy(
    test_case: ResolveUnsupportedBoundedReplayBehaviorTestCase,
) -> None:
    root_key: ObjectKey = ObjectKey(None, "table", "tbl__hourly_order_volume")
    subtree: RebuildSubtree = resolve_subtree_behavior_from_support(
        subtree=RebuildSubtree(
            root_key=root_key,
            affected_keys=(root_key,),
            upstream_boundary_key=ObjectKey(None, "table", "tbl__orders"),
            strategy=REBUILD_STRATEGY_SHADOW,
            execution_mode=REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
            forced_start_time="2026-04-09 15:00:00.000",
        ),
        bounded_replay_fallback=test_case.bounded_replay_fallback,
        history_preserving_bounded_supported=False,
    )

    assert subtree.execution_mode == test_case.expected_execution_mode
    assert subtree.requested_start_time == test_case.expected_requested_start_time
    assert not subtree.history_preserving_bounded_supported
    assert subtree.resolved_bounded_replay_fallback == test_case.bounded_replay_fallback
