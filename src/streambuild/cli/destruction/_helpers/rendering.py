"""Human-readable rendering and mandatory review for destruction plans."""

import sys

from streambuild.cli.entry.constants import AFFIRMATIVE_RESPONSES
from streambuild.executor.destruction.models import (
    DestructionExecutionResult,
    DestructionPlan,
)


def render_destruction_plan(plan: DestructionPlan) -> str:
    """Render every frozen impact-plan field before asking for review."""

    lines: list[str] = [
        "Destruction Plan",
        f"Plan ID: {plan.plan_id}",
        f"Operation: {plan.operation.value}",
        f"Target: {plan.target}",
        f"Database: {plan.database}",
        f"Metadata database: {plan.metadata_database}",
        f"Created at: {plan.created_at.isoformat()}",
        f"Expires at: {plan.expires_at.isoformat()}",
        f"Manifest fingerprint: {plan.manifest_fingerprint}",
        f"Plan fingerprint: {plan.plan_fingerprint}",
        f"Requested pipelines: {_values(plan.requested_pipeline_names)}",
        f"Included dependent pipelines: {_values(plan.included_dependent_pipeline_names)}",
        f"Affected pipelines: {_values(plan.affected_pipeline_names)}",
        f"Affected models: {_values(plan.affected_model_names)}",
        f"Affected sources: {_values(plan.affected_source_names)}",
        f"Includes historical orphans: {_yes_no(plan.include_orphans)}",
        f"Preserves managed sources: {_yes_no(plan.preserves_sources)}",
        f"Preserves replay data: {_yes_no(plan.preserves_replay_data)}",
        f"Estimated active-part bytes: {plan.estimated_bytes}",
        (
            "Effective relation DROP limit: "
            f"{_drop_limit(plan=plan, value=plan.relation_drop_size_limit)}"
        ),
        (
            "ClickHouse server default DROP limit: "
            f"{_drop_limit(plan=plan, value=plan.relation_drop_size_server_limit)}"
        ),
        (
            "StreamBuild destruction DROP override: "
            f"{_drop_limit(plan=plan, value=plan.relation_drop_size_override)}"
        ),
        "Irreversible: yes; dropped data cannot be restored by StreamBuild",
        (
            "Recreation: authored definitions remain and a later build can recreate "
            "defined resources without restoring their dropped data"
        ),
        "",
        "Relations:",
    ]
    if not plan.relations:
        lines.append("- none")
    for relation in plan.relations:
        lines.extend(
            (
                f"- {relation.database}.{relation.name}",
                f"  Kind: {relation.kind}",
                f"  Exists: {_yes_no(relation.exists)}",
                f"  Active-part bytes: {_optional_number(relation.total_bytes)}",
                f"  Active parts: {_optional_number(relation.active_parts)}",
                f"  Catalog fingerprint: {relation.catalog_fingerprint or '<none>'}",
                f"  Logical names: {_values(relation.logical_names)}",
                f"  Pipelines: {_values(relation.pipeline_names)}",
                f"  Ownership: {_values(tuple(item.value for item in relation.ownership))}",
                f"  Dependencies: {_values(relation.dependency_relation_names)}",
            )
        )
    lines.extend(("", "Required typed challenges:"))
    lines.extend(f"- {challenge}" for challenge in plan.challenges)
    return "\n".join(lines)


def confirm_destruction_review() -> bool:
    """Apply a review gate separate from the exact typed challenges."""

    return input("Have you reviewed the complete destruction plan? [y/N] ").strip().lower() in (
        AFFIRMATIVE_RESPONSES
    )


def read_destruction_challenges(plan: DestructionPlan) -> tuple[str, ...]:
    """Read exact challenge values without stripping or otherwise normalizing them."""

    return tuple(
        input(f"Type {challenge} to confirm destruction: ") for challenge in plan.challenges
    )


def print_destruction_result(result: DestructionExecutionResult) -> None:
    """Render one terminal destructive-operation result."""

    print(f"Destruction {result.outcome}.")
    print(f"Invocation ID: {result.invocation_id}")
    if result.error_message is not None:
        print(result.error_message, file=sys.stderr)


def _values(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


def _drop_limit(*, plan: DestructionPlan, value: int | None) -> str:
    if not plan.relation_drop_size_policy_observed:
        return "unknown; create a fresh plan"
    return "unlimited" if value is None else f"{value} bytes"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _optional_number(value: int | None) -> str:
    return "unknown" if value is None else str(value)
