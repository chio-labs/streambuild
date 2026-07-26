from dataclasses import replace

import pytest

from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner._helpers.rebuild import emit_rebuild_subtrees_from_changes
from streambuild.compiler.planner.constants import (
    PLANNED_CHANGE_TYPE_REBUILD,
    REBUILD_EXECUTION_MODE_FULL,
    REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
    REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
)
from streambuild.compiler.planner.models import PlannedObjectChange, RebuildSubtree
from tests.unit.src.streambuild.compiler.planner._test_types import PlannerExecutionModeTestCase
from tests.unit.src.streambuild.compiler.planner.helpers import (
    build_example_desired_state,
    build_key,
    with_schema_change_backfill_policy,
)

TEST_CASES: list[PlannerExecutionModeTestCase] = [
    PlannerExecutionModeTestCase(
        description="defaults non-breaking seedable table changes to seeded bounded rebuild",
        schema_change_kind="non_breaking",
        seed_compatibility="seedable",
        expected_execution_mode=REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
    ),
    PlannerExecutionModeTestCase(
        description="defaults breaking seedable table changes to full rebuild",
        schema_change_kind="breaking",
        seed_compatibility="seedable",
        expected_execution_mode=REBUILD_EXECUTION_MODE_FULL,
    ),
    PlannerExecutionModeTestCase(
        description="defaults non-seedable table changes to full rebuild",
        schema_change_kind="breaking",
        seed_compatibility="non_seedable",
        expected_execution_mode=REBUILD_EXECUTION_MODE_FULL,
    ),
    PlannerExecutionModeTestCase(
        description="defaults unclassified changes to full rebuild",
        schema_change_kind=None,
        seed_compatibility=None,
        expected_execution_mode=REBUILD_EXECUTION_MODE_FULL,
    ),
    PlannerExecutionModeTestCase(
        description="uses configured full policy for non-breaking changes",
        schema_change_kind="non_breaking",
        seed_compatibility="seedable",
        expected_execution_mode=REBUILD_EXECUTION_MODE_FULL,
        configured_backfill_mode="full",
    ),
    PlannerExecutionModeTestCase(
        description=(
            "uses configured bounded policy with seeded execution for seedable breaking changes"
        ),
        schema_change_kind="breaking",
        seed_compatibility="seedable",
        expected_execution_mode=REBUILD_EXECUTION_MODE_SEEDED_BOUNDED,
        configured_backfill_mode="bounded",
        configured_lookback_seconds=1800,
    ),
    PlannerExecutionModeTestCase(
        description=(
            "uses configured bounded policy with unseeded execution for non-seedable "
            "breaking changes"
        ),
        schema_change_kind="breaking",
        seed_compatibility="non_seedable",
        expected_execution_mode=REBUILD_EXECUTION_MODE_UNSEEDED_BOUNDED,
        configured_backfill_mode="bounded",
        configured_lookback_seconds=1800,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=lambda case: case.description,
)
def test_given_planned_change_metadata_when_building_subtrees_then_it_sets_expected_execution_mode(
    test_case: PlannerExecutionModeTestCase,
) -> None:
    desired_state: DesiredState = build_example_desired_state()
    if test_case.configured_backfill_mode is not None:
        desired_state = replace(
            desired_state,
            objects=tuple(
                with_schema_change_backfill_policy(
                    object_=object_,
                    mode=test_case.configured_backfill_mode,
                    lookback_seconds=test_case.configured_lookback_seconds,
                    apply_to_non_breaking=test_case.schema_change_kind == "non_breaking",
                )
                for object_ in desired_state.objects
            ),
        )
    rebuild_subtrees: tuple[RebuildSubtree, ...] = emit_rebuild_subtrees_from_changes(
        desired_state,
        (
            PlannedObjectChange(
                key=build_key(None, "table", "tbl__orders_enriched"),
                change_type=PLANNED_CHANGE_TYPE_REBUILD,
                schema_change_kind=test_case.schema_change_kind,
                seed_compatibility=test_case.seed_compatibility,
            ),
        ),
    )

    assert rebuild_subtrees[0].execution_mode == test_case.expected_execution_mode
    assert rebuild_subtrees[0].configured_backfill_mode == test_case.configured_backfill_mode
    assert rebuild_subtrees[0].execution_lookback_seconds == test_case.configured_lookback_seconds
