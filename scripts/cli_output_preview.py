"""Preview representative CLI output shapes without running the stack."""

from __future__ import annotations

import argparse

from streambuild.cli.commands.main.audit_backfill.helpers.rendering import (
    render_audit_backfill_result,
)
from streambuild.cli.commands.main.backfill.helpers.rendering import render_backfill_result
from streambuild.cli.commands.main.publish.helpers.rendering import render_publish_result
from streambuild.cli.commands.main.shared.helpers.deployment_candidates import (
    render_ambiguous_deployment_message,
)
from streambuild.cli.commands.main.shared.helpers.plan_rendering import render_plan_result

from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.models import (
    DeploymentPlan,
    DeploymentStep,
    PlannedObjectChange,
    PlannedSqlDiff,
    PlannerWarning,
    PreparedShadowObject,
    RebuildSubtree,
)
from streambuild.compiler.shared.models import (
    Column,
    DesiredMaterializedView,
    DesiredTable,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.executor.audit_backfill.models import (
    AuditBackfillResult,
    AuditDeploymentCandidate,
    RootAuditResult,
)
from streambuild.executor.backfill.models import (
    BackfillBootstrapResult,
    BackfillExecutionResult,
    RootBackfillReport,
)
from streambuild.executor.publish.models import PublishedView, PublishResult
from streambuild.spec.models import SchemaChangeBackfillPolicy, SchemaChangeBackfillRule


def main() -> int:
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Preview representative CLI output",
    )
    parser.add_argument(
        "scenario",
        choices=(
            "plan",
            "plan-type-change",
            "plan-multi",
            "backfill",
            "audit",
            "audit-caution",
            "publish",
            "audit-ambiguous",
            "all",
        ),
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args: argparse.Namespace = parser.parse_args()

    scenario_names: tuple[str, ...] = (
        (
            "plan",
            "plan-type-change",
            "plan-multi",
            "backfill",
            "audit",
            "audit-caution",
            "publish",
            "audit-ambiguous",
        )
        if args.scenario == "all"
        else (args.scenario,)
    )
    scenario_name: str
    for index, scenario_name in enumerate(scenario_names):
        if index > 0:
            print("\n---\n")
        print(
            render_scenario(
                scenario_name=scenario_name, json_output=args.json, verbose=args.verbose
            )
        )

    return 0


def render_scenario(*, scenario_name: str, json_output: bool, verbose: bool) -> str:
    if scenario_name == "plan":
        return render_plan_result(
            plan=_build_plan_preview(),
            desired_state=_build_plan_preview_desired_state(),
            database="analytics",
            json_output=json_output,
            verbose=verbose,
        )
    if scenario_name == "plan-multi":
        return render_plan_result(
            plan=_build_multi_target_plan_preview(),
            desired_state=_build_multi_target_plan_preview_desired_state(),
            database="analytics",
            json_output=json_output,
            verbose=verbose,
        )
    if scenario_name == "plan-type-change":
        return render_plan_result(
            plan=_build_type_change_plan_preview(),
            desired_state=_build_type_change_plan_preview_desired_state(),
            database="analytics",
            json_output=json_output,
            verbose=verbose,
        )
    if scenario_name == "backfill":
        return render_backfill_result(
            result=_build_backfill_preview(),
            database="analytics",
            json_output=json_output,
        )
    if scenario_name == "audit":
        return render_audit_backfill_result(
            result=_build_audit_preview(),
            database="analytics",
            json_output=json_output,
        )
    if scenario_name == "audit-caution":
        return render_audit_backfill_result(
            result=_build_audit_caution_preview(),
            database="analytics",
            json_output=json_output,
        )
    if scenario_name == "publish":
        return render_publish_result(
            result=_build_publish_preview(),
            database="analytics",
            json_output=json_output,
        )
    return render_ambiguous_deployment_message(
        command_name="audit backfill",
        database="analytics",
        root_names=("tbl__orders_enriched",),
        candidates=_build_ambiguity_candidates(),
    )


def _build_plan_preview() -> DeploymentPlan:
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


def _build_multi_target_plan_preview() -> DeploymentPlan:
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
                strategy="bounded_replay",
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


def _build_type_change_plan_preview() -> DeploymentPlan:
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


def _build_plan_preview_desired_state() -> DesiredState:
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
                schema_change_backfill=SchemaChangeBackfillPolicy(
                    breaking=SchemaChangeBackfillRule(mode="full"),
                    non_breaking=SchemaChangeBackfillRule(
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


def _build_multi_target_plan_preview_desired_state() -> DesiredState:
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


def _build_type_change_plan_preview_desired_state() -> DesiredState:
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
                schema_change_backfill=SchemaChangeBackfillPolicy(
                    breaking=SchemaChangeBackfillRule(
                        mode="bounded",
                        lookback_seconds=7 * 24 * 60 * 60,
                    ),
                    non_breaking=SchemaChangeBackfillRule(
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


def _build_backfill_preview() -> BackfillExecutionResult:
    return BackfillExecutionResult(
        bootstrap=BackfillBootstrapResult(
            deployment_id="20260410T120000Z_ab12cd",
            created_at="2026-04-10 12:00:00.000",
            deployment_plan=_build_plan_preview(),
            root_reports=(
                RootBackfillReport(
                    root_key=ObjectKey(None, "table", "tbl__orders_enriched"),
                    state_kind="greenfield",
                    replay_strategy="create_from_scratch",
                    active_deployment_id=None,
                ),
            ),
        ),
        boundary_time="2026-04-10 12:00:00.000",
    )


def _build_audit_preview() -> AuditBackfillResult:
    return AuditBackfillResult(
        deployment_id="20260410T120000Z_ab12cd",
        deployment_status="backfilling",
        assessment="ready",
        replay_lineage_mode="offsets",
        warning_codes=(),
        root_results=(
            RootAuditResult(
                root_key=ObjectKey(None, "table", "tbl__orders_enriched"),
                staged_physical_name="tbl__orders_enriched_20260410T120000Z_ab12cd",
                staged_exists=True,
                active_exists=False,
                active_row_count=None,
                staged_row_count=1203,
                assessment="ready",
                replay_lineage_mode="offsets",
                offset_catchup_summary=None,
                scalar_catchup_summary=None,
            ),
        ),
    )


def _build_publish_preview() -> PublishResult:
    return PublishResult(
        deployment_id="20260410T120000Z_ab12cd",
        published_views=(
            PublishedView(
                view_name="tbl__orders_enriched",
                target_table_name="tbl__orders_enriched_20260410T120000Z_ab12cd",
            ),
        ),
    )


def _build_audit_caution_preview() -> AuditBackfillResult:
    return AuditBackfillResult(
        deployment_id="20260410T120500Z_cd34ef",
        deployment_status="backfilling",
        assessment="caution",
        replay_lineage_mode="offsets",
        warning_codes=("missing_staged_active_partition",),
        root_results=(
            RootAuditResult(
                root_key=ObjectKey(None, "table", "tbl__orders_enriched"),
                staged_physical_name="tbl__orders_enriched_20260410T120500Z_cd34ef",
                staged_exists=True,
                active_exists=True,
                active_row_count=1350,
                staged_row_count=1324,
                assessment="caution",
                replay_lineage_mode="offsets",
                offset_catchup_summary=None,
                scalar_catchup_summary=None,
            ),
        ),
    )


def _build_ambiguity_candidates() -> tuple[AuditDeploymentCandidate, ...]:
    return (
        AuditDeploymentCandidate(
            deployment_id="20260410T120500Z_cd34ef",
            created_at="2026-04-10 12:05:00.000",
            deployment_status="backfilling",
            root_names=("tbl__orders_enriched",),
        ),
        AuditDeploymentCandidate(
            deployment_id="20260410T120000Z_ab12cd",
            created_at="2026-04-10 12:00:00.000",
            deployment_status="backfilling",
            root_names=("tbl__orders_enriched",),
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
