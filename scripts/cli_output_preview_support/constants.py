"""Preview scenario names and the renderer registry."""

from collections.abc import Mapping

from scripts.cli_output_preview_support._helpers.renderers import (
    render_audit_ambiguous_preview,
    render_audit_caution_preview,
    render_audit_preview,
    render_backfill_preview,
    render_multi_target_plan_preview,
    render_plan_preview,
    render_publish_preview,
    render_standard_plan_preview,
    render_type_change_plan_preview,
)
from scripts.cli_output_preview_support.types import PreviewRenderer

PREVIEW_DATABASE: str = "analytics"
ALL_SCENARIOS_CHOICE: str = "all"

PREVIEW_RENDERER_BY_SCENARIO: Mapping[str, PreviewRenderer] = {
    "plan": render_plan_preview,
    "plan-multi": render_multi_target_plan_preview,
    "plan-type-change": render_type_change_plan_preview,
    "plan-standard": render_standard_plan_preview,
    "backfill": render_backfill_preview,
    "audit": render_audit_preview,
    "audit-caution": render_audit_caution_preview,
    "publish": render_publish_preview,
    "audit-ambiguous": render_audit_ambiguous_preview,
}
PREVIEW_SCENARIO_NAMES: tuple[str, ...] = tuple(PREVIEW_RENDERER_BY_SCENARIO)
