import pytest

from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner._helpers.rebuild import emit_rebuild_subtrees_from_changes
from streambuild.compiler.planner.constants import (
    PLANNED_CHANGE_TYPE_CREATE,
    PLANNED_CHANGE_TYPE_REBUILD,
)
from streambuild.compiler.planner.models import PlannedObjectChange, RebuildSubtree
from tests.unit.src.streambuild.compiler.planner._test_types import (
    PlannerCollapseSubtreesTestCase,
)
from tests.unit.src.streambuild.compiler.planner.helpers import (
    build_example_desired_state,
    build_key,
    key_parts,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlannerCollapseSubtreesTestCase(
            description="collapses descendant rebuild roots under an upstream changed table",
            changed_keys=(
                (None, "table", "raw__orders"),
                (None, "table", "tbl__orders_enriched"),
            ),
            change_types=(PLANNED_CHANGE_TYPE_REBUILD, PLANNED_CHANGE_TYPE_REBUILD),
            expected_root_keys=((None, "table", "tbl__orders_enriched"),),
        ),
        PlannerCollapseSubtreesTestCase(
            description="ignores kafka table roots because kafka sources are live not shadowed",
            changed_keys=(
                (None, "kafka_table", "kafka__orders"),
                (None, "table", "raw__orders"),
            ),
            change_types=(PLANNED_CHANGE_TYPE_CREATE, PLANNED_CHANGE_TYPE_REBUILD),
            expected_root_keys=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_overlapping_changed_keys_when_building_subtrees_then_it_collapses_descendants(
    test_case: PlannerCollapseSubtreesTestCase,
) -> None:
    desired_state: DesiredState = build_example_desired_state()
    object_changes: tuple[PlannedObjectChange, ...] = tuple(
        PlannedObjectChange(
            key=build_key(*changed_key),
            change_type=change_type,
        )
        for changed_key, change_type in zip(
            test_case.changed_keys,
            test_case.change_types,
            strict=True,
        )
    )

    rebuild_subtrees: tuple[RebuildSubtree, ...] = emit_rebuild_subtrees_from_changes(
        desired_state=desired_state,
        object_changes=object_changes,
    )

    assert (
        tuple(key_parts(subtree.root_key) for subtree in rebuild_subtrees)
        == test_case.expected_root_keys
    )
