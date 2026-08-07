import json

import pytest

from streambuild.adapter.models import AdapterReplayColumns
from streambuild.cli.plan._helpers.direct_rendering import render_direct_plan_json
from streambuild.compiler.compile.models import LogicalResourceKey, ObjectKey
from streambuild.compiler.planner.models import (
    DirectPlan,
    DirectPlanEntry,
    DirectPrerequisite,
    DirectRelationOperation,
    DirectReplayRoot,
    PlannerWarning,
)
from tests.unit.src.streambuild.cli.plan.main._test_types import (
    CliDirectPlanSerializationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CliDirectPlanSerializationTestCase(
            description="serializes every direct plan and nested identity field",
            expected_payload={
                "mode": "direct",
                "adapter": "clickhouse",
                "database": "analytics",
                "start_time": None,
                "user_scope": [{"resource_type": "model", "name": "orders_enriched"}],
                "execution_scope": [{"resource_type": "model", "name": "orders_enriched"}],
                "prerequisite_scope": [
                    {
                        "key": {"resource_type": "source", "name": "orders"},
                        "relation_names": ["raw__orders"],
                        "present": True,
                        "framework_managed": True,
                    }
                ],
                "entries": [
                    {
                        "model_key": {
                            "resource_type": "model",
                            "name": "orders_enriched",
                        },
                        "reason": "selected",
                        "relation_names": ["tbl__orders_enriched", "mv__orders_enriched"],
                        "resource_kinds": ["table", "materialized_view"],
                        "driving_input_key": {"resource_type": "source", "name": "orders"},
                        "is_replay_root": True,
                        "sql_change": None,
                    }
                ],
                "replay_roots": [
                    {
                        "model_key": {
                            "resource_type": "model",
                            "name": "orders_enriched",
                        },
                        "driving_input_key": {
                            "resource_type": "source",
                            "name": "orders",
                        },
                        "driving_input_relation_name": "raw__orders",
                        "driving_input_replay_columns": {
                            "partition": "event_partition",
                            "offset": "event_offset",
                            "timestamp": "event_timestamp",
                            "landed_at": "landed_at",
                            "cursor": "event_cursor",
                        },
                        "replay_boundary_mode": "offsets",
                        "propagated_model_keys": [
                            {"resource_type": "model", "name": "orders_enriched"}
                        ],
                        "has_aggregate_semantics": False,
                    }
                ],
                "teardown": [
                    {
                        "relation_name": "mv__orders_enriched",
                        "action": "drop",
                        "model_key": {
                            "resource_type": "model",
                            "name": "orders_enriched",
                        },
                        "resource_kind": "materialized_view",
                    }
                ],
                "creation": [
                    {
                        "relation_name": "tbl__orders_enriched",
                        "action": "create",
                        "model_key": {
                            "resource_type": "model",
                            "name": "orders_enriched",
                        },
                        "resource_kind": "table",
                    }
                ],
                "warnings": [
                    {
                        "warning_code": "replay_overlap",
                        "message": "Replay intentionally overlaps live propagation",
                        "root_key": {
                            "database": "analytics",
                            "object_type": "table",
                            "name": "raw__orders",
                        },
                        "target_key": {
                            "database": "analytics",
                            "object_type": "table",
                            "name": "tbl__orders_enriched",
                        },
                    }
                ],
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_plan_when_serializing_then_preserves_complete_nested_identity(
    test_case: CliDirectPlanSerializationTestCase,
) -> None:
    source_key: LogicalResourceKey = LogicalResourceKey("source", "orders")
    model_key: LogicalResourceKey = LogicalResourceKey("model", "orders_enriched")
    plan: DirectPlan = DirectPlan(
        database="analytics",
        user_scope=(model_key,),
        execution_scope=(model_key,),
        prerequisite_scope=(
            DirectPrerequisite(
                key=source_key,
                relation_names=("raw__orders",),
                present=True,
                framework_managed=True,
            ),
        ),
        entries=(
            DirectPlanEntry(
                model_key=model_key,
                reason="selected",
                relation_names=("tbl__orders_enriched", "mv__orders_enriched"),
                resource_kinds=("table", "materialized_view"),
                driving_input_key=source_key,
                is_replay_root=True,
            ),
        ),
        replay_roots=(
            DirectReplayRoot(
                model_key=model_key,
                driving_input_key=source_key,
                driving_input_relation_name="raw__orders",
                driving_input_replay_columns=AdapterReplayColumns(
                    partition="event_partition",
                    offset="event_offset",
                    timestamp="event_timestamp",
                    landed_at="landed_at",
                    cursor="event_cursor",
                ),
                replay_boundary_mode="offsets",
                propagated_model_keys=(model_key,),
            ),
        ),
        teardown_operations=(
            DirectRelationOperation(
                relation_name="mv__orders_enriched",
                action="drop",
                model_key=model_key,
                resource_kind="materialized_view",
            ),
        ),
        creation_operations=(
            DirectRelationOperation(
                relation_name="tbl__orders_enriched",
                action="create",
                model_key=model_key,
                resource_kind="table",
            ),
        ),
        warnings=(
            PlannerWarning(
                warning_code="replay_overlap",
                message="Replay intentionally overlaps live propagation",
                root_key=ObjectKey("analytics", "table", "raw__orders"),
                target_key=ObjectKey("analytics", "table", "tbl__orders_enriched"),
            ),
        ),
    )

    assert json.loads(render_direct_plan_json(plan=plan, adapter_name="clickhouse")) == (
        test_case.expected_payload
    )
