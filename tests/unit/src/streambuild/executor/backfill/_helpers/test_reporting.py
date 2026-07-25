import pytest

from streambuild.compiler.planner.constants import REBUILD_STRATEGY_SHADOW
from streambuild.compiler.planner.models import DeploymentPlan, RebuildSubtree
from streambuild.compiler.shared.models import ObjectKey
from streambuild.executor.backfill._helpers.reporting import (
    filter_root_backfill_reports_for_deployment,
)
from streambuild.executor.backfill.models import RootBackfillReport
from tests.unit.src.streambuild.executor.backfill._helpers._test_types import (
    FilterRootBackfillReportsForDeploymentTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FilterRootBackfillReportsForDeploymentTestCase(
            description="keeps only deployment target reports for subset selections",
            expected_root_names=("tbl__daily_revenue",),
        )
    ],
    ids=["keeps only deployment target reports for subset selections"],
)
def test_given_root_reports_outside_selected_deployment_when_filtering_then_it_keeps_targets(
    test_case: FilterRootBackfillReportsForDeploymentTestCase,
) -> None:
    orders_key: ObjectKey = ObjectKey(None, "table", "tbl__orders")
    daily_revenue_key: ObjectKey = ObjectKey(None, "table", "tbl__daily_revenue")
    hourly_volume_key: ObjectKey = ObjectKey(None, "table", "tbl__hourly_order_volume")

    filtered_reports: tuple[RootBackfillReport, ...] = filter_root_backfill_reports_for_deployment(
        (
            RootBackfillReport(
                root_key=orders_key,
                state_kind="active_view_present",
                replay_strategy="bounded_replay",
                active_deployment_id="dep_active",
            ),
            RootBackfillReport(
                root_key=daily_revenue_key,
                state_kind="active_view_present",
                replay_strategy="bounded_replay",
                active_deployment_id="dep_active",
            ),
            RootBackfillReport(
                root_key=hourly_volume_key,
                state_kind="active_view_present",
                replay_strategy="bounded_replay",
                active_deployment_id="dep_active",
            ),
        ),
        DeploymentPlan(
            deployment_id="dep_new",
            object_changes=(),
            rebuild_subtrees=(
                RebuildSubtree(
                    root_key=daily_revenue_key,
                    affected_keys=(daily_revenue_key,),
                    upstream_boundary_key=ObjectKey(None, "table", "raw__orders"),
                    strategy=REBUILD_STRATEGY_SHADOW,
                ),
            ),
            steps=(),
            prepared_shadow_objects=(),
            warnings=(),
            sql_diffs=(),
        ),
    )

    assert (
        tuple(report.root_key.name for report in filtered_reports) == test_case.expected_root_names
    )
