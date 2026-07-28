"""Deployment plan fixtures for preview rendering."""

from __future__ import annotations

from streambuild.compiler.compile.models import (
    Column,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    LogicalResourceKey,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.discovery.models import (
    ReplayOnChangePolicy,
    ReplayOnChangeRule,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.compiler.planner.models import (
    DeploymentPlan,
    DeploymentStep,
    PlannedObjectChange,
    PlannedSqlDiff,
    PlannerWarning,
    PreparedShadowObject,
    RebuildSubtree,
    StandardPlan,
    StandardPlanEntry,
    StandardPopulationSegment,
    StandardPrerequisite,
    StandardRelationOperation,
    StandardReplayRoot,
    TargetOwnershipClassification,
)
from streambuild.compiler.planner.types import (
    StandardPlanReason,
    StandardRelationAction,
    TargetOwnership,
)


def build_plan_preview() -> DeploymentPlan:
    mv_orders_enriched_key: ObjectKey = ObjectKey(None, "materialized_view", "mv__orders_enriched")
    tbl_orders_enriched_key: ObjectKey = ObjectKey(None, "table", "tbl__orders_enriched")
    return DeploymentPlan(
        deployment_id=None,
        object_changes=(
            PlannedObjectChange(
                key=mv_orders_enriched_key,
                change_type="replace",
            ),
            PlannedObjectChange(
                key=tbl_orders_enriched_key,
                change_type="replace",
                schema_change_kind="non_breaking",
                seed_compatibility="seedable",
            ),
        ),
        rebuild_subtrees=(
            RebuildSubtree(
                root_key=ObjectKey(None, "table", "raw__orders"),
                affected_keys=(
                    ObjectKey(None, "table", "raw__orders"),
                    ObjectKey(None, "materialized_view", "mv__orders"),
                    ObjectKey(None, "table", "tbl__orders_enriched"),
                    ObjectKey(None, "materialized_view", "mv__orders_enriched"),
                ),
                upstream_boundary_key=ObjectKey(None, "table", "raw__orders"),
                strategy="shadow_rebuild",
                execution_mode="seeded_bounded_rebuild",
                configured_backfill_mode="bounded",
                execution_lookback_seconds=7 * 24 * 60 * 60,
            ),
        ),
        steps=(
            DeploymentStep(
                step_id="step-1",
                phase="plan",
                action="plan_shadow_table",
                root_key=ObjectKey(None, "table", "raw__orders"),
                target_key=ObjectKey(None, "table", "raw__orders"),
            ),
            DeploymentStep(
                step_id="step-2",
                phase="plan",
                action="plan_shadow_materialized_view",
                root_key=ObjectKey(None, "table", "raw__orders"),
                target_key=ObjectKey(None, "materialized_view", "mv__orders"),
            ),
            DeploymentStep(
                step_id="step-3",
                phase="plan",
                action="plan_shadow_table",
                root_key=ObjectKey(None, "table", "raw__orders"),
                target_key=ObjectKey(None, "table", "tbl__orders_enriched"),
            ),
            DeploymentStep(
                step_id="step-4",
                phase="plan",
                action="plan_shadow_materialized_view",
                root_key=ObjectKey(None, "table", "raw__orders"),
                target_key=ObjectKey(None, "materialized_view", "mv__orders_enriched"),
            ),
            DeploymentStep(
                step_id="step-5",
                phase="backfill",
                action="backfill_subtree",
                root_key=ObjectKey(None, "table", "raw__orders"),
            ),
            DeploymentStep(
                step_id="step-6",
                phase="audit",
                action="audit_subtree",
                root_key=ObjectKey(None, "table", "raw__orders"),
            ),
            DeploymentStep(
                step_id="step-7",
                phase="publish",
                action="publish_subtree",
                root_key=ObjectKey(None, "table", "raw__orders"),
            ),
        ),
        prepared_shadow_objects=(
            PreparedShadowObject(
                logical_key=ObjectKey(None, "table", "raw__orders"),
                physical_name="raw__orders_20260410T120000Z_ab12cd",
            ),
            PreparedShadowObject(
                logical_key=ObjectKey(None, "materialized_view", "mv__orders"),
                physical_name="mv__orders_20260410T120000Z_ab12cd",
            ),
            PreparedShadowObject(
                logical_key=ObjectKey(None, "table", "tbl__orders_enriched"),
                physical_name="tbl__orders_enriched_20260410T120000Z_ab12cd",
            ),
            PreparedShadowObject(
                logical_key=ObjectKey(None, "materialized_view", "mv__orders_enriched"),
                physical_name="mv__orders_enriched_20260410T120000Z_ab12cd",
            ),
        ),
        warnings=(),
        sql_diffs=(
            PlannedSqlDiff(
                key=mv_orders_enriched_key,
                object_type="transform",
                name="mv__orders_enriched",
                diff_lines=(
                    "--- current",
                    "+++ desired",
                    "@@ -1,5 +1,6 @@",
                    " SELECT",
                    "   order_id,",
                    "   customer_id,",
                    "-  CAST(amount AS Decimal(18, 2)) AS order_total",
                    "+  amount::Decimal(18, 2) AS order_total,",
                    "+  region",
                    " FROM raw__orders",
                ),
            ),
            PlannedSqlDiff(
                key=tbl_orders_enriched_key,
                object_type="table",
                name="tbl__orders_enriched",
                diff_lines=(
                    "--- current",
                    "+++ desired",
                    "@@ -1,7 +1,8 @@",
                    " CREATE TABLE tbl__orders_enriched (",
                    "   order_id UInt64,",
                    "   customer_id UInt64,",
                    "-  order_total Decimal(18, 2)",
                    "+  order_total Decimal(18, 2),",
                    "+  region LowCardinality(String)",
                    " )",
                    " ENGINE = ReplacingMergeTree",
                    " ORDER BY (order_id)",
                ),
            ),
        ),
    )


def build_multi_target_plan_preview() -> DeploymentPlan:
    return DeploymentPlan(
        deployment_id=None,
        object_changes=(),
        rebuild_subtrees=(
            RebuildSubtree(
                root_key=ObjectKey(None, "table", "raw__orders"),
                affected_keys=(
                    ObjectKey(None, "table", "tbl__orders_enriched"),
                    ObjectKey(None, "table", "tbl__orders_rollup"),
                ),
                upstream_boundary_key=ObjectKey(None, "table", "raw__orders"),
                strategy="shadow_rebuild",
            ),
        ),
        steps=(),
        prepared_shadow_objects=(),
        warnings=(
            PlannerWarning(
                warning_code="mutable_ref_replay_not_guaranteed",
                message="Mutable side refs may weaken exact replay equivalence.",
                root_key=ObjectKey(None, "table", "raw__orders"),
            ),
        ),
    )


def build_type_change_plan_preview() -> DeploymentPlan:
    mv_orders_enriched_key: ObjectKey = ObjectKey(None, "materialized_view", "mv__orders_enriched")
    tbl_orders_enriched_key: ObjectKey = ObjectKey(None, "table", "tbl__orders_enriched")
    return DeploymentPlan(
        deployment_id=None,
        object_changes=(
            PlannedObjectChange(
                key=mv_orders_enriched_key,
                change_type="replace",
            ),
            PlannedObjectChange(
                key=tbl_orders_enriched_key,
                change_type="replace",
                schema_change_kind="breaking",
                seed_compatibility="non_seedable",
            ),
        ),
        rebuild_subtrees=(
            RebuildSubtree(
                root_key=ObjectKey(None, "table", "raw__orders"),
                affected_keys=(
                    ObjectKey(None, "table", "raw__orders"),
                    tbl_orders_enriched_key,
                    mv_orders_enriched_key,
                ),
                upstream_boundary_key=ObjectKey(None, "table", "raw__orders"),
                strategy="shadow_rebuild",
                execution_mode="unseeded_bounded_rebuild",
                configured_backfill_mode="bounded",
                execution_lookback_seconds=7 * 24 * 60 * 60,
            ),
        ),
        steps=(),
        prepared_shadow_objects=(),
        warnings=(),
        sql_diffs=(
            PlannedSqlDiff(
                key=mv_orders_enriched_key,
                object_type="transform",
                name="mv__orders_enriched",
                diff_lines=(
                    "--- current",
                    "+++ desired",
                    "@@ -1,3 +1,3 @@",
                    "-SELECT order_id, kafka_topic FROM raw__orders",
                    "+SELECT order_id, CAST(kafka_topic AS UInt64) AS kafka_topic FROM raw__orders",
                ),
            ),
            PlannedSqlDiff(
                key=tbl_orders_enriched_key,
                object_type="table",
                name="tbl__orders_enriched",
                diff_lines=(
                    "--- current",
                    "+++ desired",
                    "@@ -1,5 +1,5 @@",
                    " CREATE TABLE tbl__orders_enriched (",
                    "   order_id UInt64,",
                    "-  kafka_topic String",
                    "+  kafka_topic UInt64",
                    " )",
                ),
            ),
        ),
    )


def build_plan_preview_desired_state() -> DesiredState:
    raw_orders_key: ObjectKey = ObjectKey(None, "table", "raw__orders")
    mv_orders_key: ObjectKey = ObjectKey(None, "materialized_view", "mv__orders")
    tbl_orders_enriched_key: ObjectKey = ObjectKey(None, "table", "tbl__orders_enriched")
    mv_orders_enriched_key: ObjectKey = ObjectKey(
        None,
        "materialized_view",
        "mv__orders_enriched",
    )
    return DesiredState(
        objects=(
            DesiredTable(
                key=raw_orders_key,
                deps=(),
                spec=TableSpec(
                    columns=(
                        Column("order_id", "UInt64"),
                        Column("customer_id", "UInt64"),
                        Column("kafka_landed_at", "DateTime64(3)"),
                    ),
                    storage=TableStorage(
                        engine="MergeTree",
                        order_by=("order_id",),
                    ),
                ),
            ),
            DesiredMaterializedView(
                key=mv_orders_key,
                deps=(raw_orders_key,),
                spec=MaterializedViewSpec(
                    source_table_name="raw__orders",
                    target_table_name="raw__orders",
                    query=("SELECT order_id, customer_id, kafka_landed_at\nFROM raw__orders"),
                ),
            ),
            DesiredTable(
                key=tbl_orders_enriched_key,
                deps=(raw_orders_key,),
                spec=TableSpec(
                    columns=(
                        Column("order_id", "UInt64"),
                        Column("customer_id", "UInt64"),
                        Column("order_total", "Decimal(18, 2)"),
                    ),
                    storage=TableStorage(
                        engine="ReplacingMergeTree",
                        order_by=("order_id",),
                    ),
                ),
                replay_on_change=ReplayOnChangePolicy(
                    breaking=ReplayOnChangeRule(mode="full"),
                    non_breaking=ReplayOnChangeRule(
                        mode="bounded",
                        lookback_seconds=7 * 24 * 60 * 60,
                    ),
                ),
            ),
            DesiredMaterializedView(
                key=mv_orders_enriched_key,
                deps=(raw_orders_key,),
                spec=MaterializedViewSpec(
                    source_table_name="raw__orders",
                    target_table_name="tbl__orders_enriched",
                    query=(
                        "SELECT\n"
                        "  order_id,\n"
                        "  customer_id,\n"
                        "  amount::Decimal(18, 2) AS order_total\n"
                        "FROM raw__orders"
                    ),
                ),
            ),
        ),
        replay_anchor_keys=frozenset({raw_orders_key}),
        mutable_ref_warning_keys=frozenset(),
    )


def build_multi_target_plan_preview_desired_state() -> DesiredState:
    raw_orders_key: ObjectKey = ObjectKey(None, "table", "raw__orders")
    tbl_orders_enriched_key: ObjectKey = ObjectKey(None, "table", "tbl__orders_enriched")
    tbl_orders_rollup_key: ObjectKey = ObjectKey(None, "table", "tbl__orders_rollup")
    return DesiredState(
        objects=(
            DesiredTable(
                key=raw_orders_key,
                deps=(),
                spec=TableSpec(
                    columns=(
                        Column("order_id", "UInt64"),
                        Column("customer_id", "UInt64"),
                    ),
                    storage=TableStorage(
                        engine="MergeTree",
                        order_by=("order_id",),
                    ),
                ),
            ),
            DesiredTable(
                key=tbl_orders_enriched_key,
                deps=(raw_orders_key,),
                spec=TableSpec(
                    columns=(
                        Column("order_id", "UInt64"),
                        Column("customer_id", "UInt64"),
                        Column("order_total", "Decimal(18, 2)"),
                    ),
                    storage=TableStorage(
                        engine="ReplacingMergeTree",
                        order_by=("order_id",),
                    ),
                ),
            ),
            DesiredTable(
                key=tbl_orders_rollup_key,
                deps=(raw_orders_key,),
                spec=TableSpec(
                    columns=(
                        Column("customer_id", "UInt64"),
                        Column("order_count", "UInt64"),
                    ),
                    storage=TableStorage(
                        engine="SummingMergeTree",
                        order_by=("customer_id",),
                    ),
                ),
            ),
        ),
        replay_anchor_keys=frozenset({raw_orders_key}),
        mutable_ref_warning_keys=frozenset({tbl_orders_enriched_key}),
    )


def build_type_change_plan_preview_desired_state() -> DesiredState:
    raw_orders_key: ObjectKey = ObjectKey(None, "table", "raw__orders")
    tbl_orders_enriched_key: ObjectKey = ObjectKey(None, "table", "tbl__orders_enriched")
    mv_orders_enriched_key: ObjectKey = ObjectKey(None, "materialized_view", "mv__orders_enriched")
    return DesiredState(
        objects=(
            DesiredTable(
                key=raw_orders_key,
                deps=(),
                spec=TableSpec(
                    columns=(
                        Column("order_id", "UInt64"),
                        Column("kafka_topic", "String"),
                        Column("kafka_landed_at", "DateTime64(3)"),
                    ),
                    storage=TableStorage(
                        engine="MergeTree",
                        order_by=("order_id",),
                    ),
                ),
            ),
            DesiredTable(
                key=tbl_orders_enriched_key,
                deps=(raw_orders_key,),
                spec=TableSpec(
                    columns=(
                        Column("order_id", "UInt64"),
                        Column("kafka_topic", "UInt64"),
                    ),
                    storage=TableStorage(
                        engine="ReplacingMergeTree",
                        order_by=("order_id",),
                    ),
                ),
                replay_on_change=ReplayOnChangePolicy(
                    breaking=ReplayOnChangeRule(
                        mode="bounded",
                        lookback_seconds=7 * 24 * 60 * 60,
                    ),
                    non_breaking=ReplayOnChangeRule(
                        mode="bounded",
                        lookback_seconds=7 * 24 * 60 * 60,
                    ),
                ),
            ),
            DesiredMaterializedView(
                key=mv_orders_enriched_key,
                deps=(raw_orders_key,),
                spec=MaterializedViewSpec(
                    source_table_name="raw__orders",
                    target_table_name="tbl__orders_enriched",
                    query=(
                        "SELECT\n"
                        "  order_id,\n"
                        "  CAST(kafka_topic AS UInt64) AS kafka_topic\n"
                        "FROM raw__orders"
                    ),
                ),
            ),
        ),
        replay_anchor_keys=frozenset({raw_orders_key}),
        mutable_ref_warning_keys=frozenset(),
    )


def build_standard_plan_preview() -> StandardPlan:
    """Build one representative standard plan for output preview."""

    orders_key: LogicalResourceKey = LogicalResourceKey(
        resource_type=LogicalResourceType.SOURCE, name="orders"
    )
    enriched_key: LogicalResourceKey = LogicalResourceKey(
        resource_type=LogicalResourceType.MODEL, name="orders_enriched"
    )
    return StandardPlan(
        database="analytics",
        user_scope=(enriched_key,),
        execution_scope=(enriched_key,),
        prerequisite_scope=(
            StandardPrerequisite(
                key=orders_key,
                relation_names=("raw__orders",),
                present=True,
            ),
        ),
        entries=(
            StandardPlanEntry(
                model_key=enriched_key,
                reason=StandardPlanReason.SELECTED,
                relation_names=("tbl__orders_enriched", "mv__orders_enriched"),
                ownership=(
                    TargetOwnershipClassification(
                        relation_name="tbl__orders_enriched",
                        ownership=TargetOwnership.STANDARD,
                    ),
                    TargetOwnershipClassification(
                        relation_name="mv__orders_enriched",
                        ownership=TargetOwnership.STANDARD,
                    ),
                ),
                driving_input_key=orders_key,
                is_replay_root=True,
            ),
        ),
        replay_roots=(
            StandardReplayRoot(
                model_key=enriched_key,
                driving_input_key=orders_key,
                driving_input_relation_name="raw__orders",
                replay_boundary_mode=ReplayLineageMode.OFFSETS,
                propagated_model_keys=(enriched_key,),
            ),
        ),
        population_segments=(
            StandardPopulationSegment(
                model_key=enriched_key,
                driving_input_key=orders_key,
                driving_input_relation_name="raw__orders",
                replay_boundary_mode=ReplayLineageMode.OFFSETS,
            ),
        ),
        teardown_operations=(
            StandardRelationOperation(
                relation_name="mv__orders_enriched",
                action=StandardRelationAction.DROP,
                model_key=enriched_key,
            ),
            StandardRelationOperation(
                relation_name="tbl__orders_enriched",
                action=StandardRelationAction.DROP,
                model_key=enriched_key,
            ),
        ),
        creation_operations=(
            StandardRelationOperation(
                relation_name="tbl__orders_enriched",
                action=StandardRelationAction.CREATE,
                model_key=enriched_key,
            ),
            StandardRelationOperation(
                relation_name="mv__orders_enriched",
                action=StandardRelationAction.CREATE,
                model_key=enriched_key,
            ),
        ),
    )
