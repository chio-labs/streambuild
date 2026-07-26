"""Render one representative CLI output scenario from static fixtures."""

from scripts.cli_output_preview_support._helpers.plan_fixtures import (
    build_multi_target_plan_preview,
    build_multi_target_plan_preview_desired_state,
    build_plan_preview,
    build_plan_preview_desired_state,
    build_type_change_plan_preview,
    build_type_change_plan_preview_desired_state,
)
from scripts.cli_output_preview_support._helpers.result_fixtures import (
    build_ambiguity_candidates,
    build_audit_caution_preview,
    build_audit_preview,
    build_backfill_preview,
    build_publish_preview,
)
from streambuild.cli.audit_backfill.main.render_audit_backfill_result import (
    render_audit_backfill_result,
)
from streambuild.cli.backfill.main.render_backfill_result import render_backfill_result
from streambuild.cli.publish.main.render_publish_result import render_publish_result
from streambuild.cli.shared.main.render_ambiguous_deployment_message import (
    render_ambiguous_deployment_message,
)
from streambuild.cli.shared.main.render_plan_result import render_plan_result


def render_cli_output_preview(*, scenario_name: str, json_output: bool, verbose: bool) -> str:
    if scenario_name == "plan":
        return render_plan_result(
            plan=build_plan_preview(),
            desired_state=build_plan_preview_desired_state(),
            database="analytics",
            json_output=json_output,
            verbose=verbose,
        )
    if scenario_name == "plan-multi":
        return render_plan_result(
            plan=build_multi_target_plan_preview(),
            desired_state=build_multi_target_plan_preview_desired_state(),
            database="analytics",
            json_output=json_output,
            verbose=verbose,
        )
    if scenario_name == "plan-type-change":
        return render_plan_result(
            plan=build_type_change_plan_preview(),
            desired_state=build_type_change_plan_preview_desired_state(),
            database="analytics",
            json_output=json_output,
            verbose=verbose,
        )
    if scenario_name == "backfill":
        return render_backfill_result(
            result=build_backfill_preview(),
            database="analytics",
            json_output=json_output,
        )
    if scenario_name == "audit":
        return render_audit_backfill_result(
            result=build_audit_preview(),
            database="analytics",
            json_output=json_output,
        )
    if scenario_name == "audit-caution":
        return render_audit_backfill_result(
            result=build_audit_caution_preview(),
            database="analytics",
            json_output=json_output,
        )
    if scenario_name == "publish":
        return render_publish_result(
            result=build_publish_preview(),
            database="analytics",
            json_output=json_output,
        )
    return render_ambiguous_deployment_message(
        command_name="audit backfill",
        database="analytics",
        root_names=("tbl__orders_enriched",),
        candidates=build_ambiguity_candidates(),
    )
