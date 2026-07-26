"""One preview renderer per scenario, keyed by scenario name."""

from collections.abc import Callable, Mapping

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
from scripts.cli_output_preview_support.constants import PREVIEW_DATABASE
from streambuild.cli.audit_backfill.main.render_audit_backfill_result import (
    render_audit_backfill_result,
)
from streambuild.cli.backfill.main.render_backfill_result import render_backfill_result
from streambuild.cli.publish.main.render_publish_result import render_publish_result
from streambuild.cli.shared.main.render_ambiguous_deployment_message import (
    render_ambiguous_deployment_message,
)
from streambuild.cli.shared.main.render_plan_result import render_plan_result

type PreviewRenderer = Callable[[bool, bool], str]


def _render_plan_preview(json_output: bool, verbose: bool) -> str:
    return render_plan_result(
        plan=build_plan_preview(),
        desired_state=build_plan_preview_desired_state(),
        database=PREVIEW_DATABASE,
        json_output=json_output,
        verbose=verbose,
    )


def _render_multi_target_plan_preview(json_output: bool, verbose: bool) -> str:
    return render_plan_result(
        plan=build_multi_target_plan_preview(),
        desired_state=build_multi_target_plan_preview_desired_state(),
        database=PREVIEW_DATABASE,
        json_output=json_output,
        verbose=verbose,
    )


def _render_type_change_plan_preview(json_output: bool, verbose: bool) -> str:
    return render_plan_result(
        plan=build_type_change_plan_preview(),
        desired_state=build_type_change_plan_preview_desired_state(),
        database=PREVIEW_DATABASE,
        json_output=json_output,
        verbose=verbose,
    )


def _render_backfill_preview(json_output: bool, verbose: bool) -> str:
    return render_backfill_result(
        result=build_backfill_preview(),
        database=PREVIEW_DATABASE,
        json_output=json_output,
    )


def _render_audit_preview(json_output: bool, verbose: bool) -> str:
    return render_audit_backfill_result(
        result=build_audit_preview(),
        database=PREVIEW_DATABASE,
        json_output=json_output,
    )


def _render_audit_caution_preview(json_output: bool, verbose: bool) -> str:
    return render_audit_backfill_result(
        result=build_audit_caution_preview(),
        database=PREVIEW_DATABASE,
        json_output=json_output,
    )


def _render_publish_preview(json_output: bool, verbose: bool) -> str:
    return render_publish_result(
        result=build_publish_preview(),
        database=PREVIEW_DATABASE,
        json_output=json_output,
    )


def _render_audit_ambiguous_preview(json_output: bool, verbose: bool) -> str:
    return render_ambiguous_deployment_message(
        command_name="audit backfill",
        database=PREVIEW_DATABASE,
        root_names=("tbl__orders_enriched",),
        candidates=build_ambiguity_candidates(),
    )


PREVIEW_RENDERER_BY_SCENARIO: Mapping[str, PreviewRenderer] = {
    "plan": _render_plan_preview,
    "plan-multi": _render_multi_target_plan_preview,
    "plan-type-change": _render_type_change_plan_preview,
    "backfill": _render_backfill_preview,
    "audit": _render_audit_preview,
    "audit-caution": _render_audit_caution_preview,
    "publish": _render_publish_preview,
    "audit-ambiguous": _render_audit_ambiguous_preview,
}
