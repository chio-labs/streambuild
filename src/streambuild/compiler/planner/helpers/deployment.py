"""Deployment-plan step emission helpers."""

from __future__ import annotations

from streambuild.compiler.actual_state.models import ActualState
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.constants import (
    DEPLOYMENT_ACTION_AUDIT_SUBTREE,
    DEPLOYMENT_ACTION_BACKFILL_SUBTREE,
    DEPLOYMENT_ACTION_PLAN_SHADOW_MATERIALIZED_VIEW,
    DEPLOYMENT_ACTION_PLAN_SHADOW_TABLE,
    DEPLOYMENT_ACTION_PUBLISH_SUBTREE,
    DEPLOYMENT_PHASE_AUDIT,
    DEPLOYMENT_PHASE_BACKFILL,
    DEPLOYMENT_PHASE_PLAN,
    DEPLOYMENT_PHASE_PUBLISH,
)
from streambuild.compiler.planner.helpers.diff import classify_object_changes
from streambuild.compiler.planner.helpers.rebuild import emit_rebuild_subtrees_from_changes
from streambuild.compiler.planner.helpers.sql_diffs import build_planned_sql_diffs
from streambuild.compiler.planner.models import (
    DeploymentPlan,
    DeploymentStep,
    PlannedObjectChange,
    PlannedSqlDiff,
    PlannerWarning,
    PreparedShadowObject,
    RebuildSubtree,
)
from streambuild.compiler.planner.types import DeploymentAction
from streambuild.compiler.shared.constants import DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW
from streambuild.compiler.shared.helpers.deployment_names import build_deployment_physical_name
from streambuild.compiler.shared.models import ObjectKey


def build_deployment_plan(
    desired_state: DesiredState,
    actual_state: ActualState,
    default_database: str,
    deployment_id: str | None = None,
    full_refresh_keys: frozenset[ObjectKey] = frozenset(),
    start_time_keys: frozenset[ObjectKey] = frozenset(),
    start_time: str | None = None,
) -> DeploymentPlan:
    """Build a conservative staged deployment plan from desired and actual state."""

    object_changes: tuple[PlannedObjectChange, ...] = classify_object_changes(
        desired_state=desired_state,
        actual_state=actual_state,
        full_refresh_keys=full_refresh_keys,
        start_time_keys=start_time_keys,
        start_time=start_time,
    )
    rebuild_subtrees: tuple[RebuildSubtree, ...] = emit_rebuild_subtrees_from_changes(
        desired_state=desired_state,
        object_changes=object_changes,
    )
    prepared_shadow_objects: tuple[PreparedShadowObject, ...] = build_prepared_shadow_objects(
        rebuild_subtrees,
        deployment_id,
    )
    steps: tuple[DeploymentStep, ...] = emit_deployment_steps(
        rebuild_subtrees,
        build_physical_name_by_key(prepared_shadow_objects),
    )
    warnings: tuple[PlannerWarning, ...] = emit_planner_warnings(desired_state, rebuild_subtrees)
    sql_diffs: tuple[PlannedSqlDiff, ...] = build_planned_sql_diffs(
        desired_state=desired_state,
        actual_state=actual_state,
        object_changes=object_changes,
        default_database=default_database,
    )
    return DeploymentPlan(
        deployment_id=deployment_id,
        object_changes=object_changes,
        rebuild_subtrees=rebuild_subtrees,
        steps=steps,
        prepared_shadow_objects=prepared_shadow_objects,
        warnings=warnings,
        sql_diffs=sql_diffs,
    )


def emit_deployment_steps(
    rebuild_subtrees: tuple[RebuildSubtree, ...],
    physical_name_by_key: dict[ObjectKey, str],
) -> tuple[DeploymentStep, ...]:
    """Emit deterministic staged deployment steps for rebuild subtrees."""

    steps: list[DeploymentStep] = []
    subtree_index: int
    subtree: RebuildSubtree
    for subtree_index, subtree in enumerate(rebuild_subtrees, start=1):
        target_key: ObjectKey
        for target_key in subtree.affected_keys:
            steps.append(
                DeploymentStep(
                    step_id=f"plan-{subtree_index}-{target_key.object_type}-{target_key.name}",
                    phase=DEPLOYMENT_PHASE_PLAN,
                    action=plan_action_for_key(target_key),
                    root_key=subtree.root_key,
                    target_key=target_key,
                    physical_name=physical_name_by_key.get(target_key),
                )
            )

        root_key: ObjectKey = subtree.root_key
        steps.extend(
            (
                DeploymentStep(
                    step_id=f"backfill-{subtree_index}-{root_key.name}",
                    phase=DEPLOYMENT_PHASE_BACKFILL,
                    action=DEPLOYMENT_ACTION_BACKFILL_SUBTREE,
                    root_key=root_key,
                    physical_name=physical_name_by_key.get(root_key),
                ),
                DeploymentStep(
                    step_id=f"audit-{subtree_index}-{root_key.name}",
                    phase=DEPLOYMENT_PHASE_AUDIT,
                    action=DEPLOYMENT_ACTION_AUDIT_SUBTREE,
                    root_key=root_key,
                    physical_name=physical_name_by_key.get(root_key),
                ),
                DeploymentStep(
                    step_id=f"publish-{subtree_index}-{root_key.name}",
                    phase=DEPLOYMENT_PHASE_PUBLISH,
                    action=DEPLOYMENT_ACTION_PUBLISH_SUBTREE,
                    root_key=root_key,
                    physical_name=physical_name_by_key.get(root_key),
                ),
            )
        )

    return tuple(steps)


def build_prepared_shadow_objects(
    rebuild_subtrees: tuple[RebuildSubtree, ...],
    deployment_id: str | None,
) -> tuple[PreparedShadowObject, ...]:
    """Build deterministic physical shadow identities for a deployment plan."""

    if deployment_id is None:
        return ()

    prepared_shadow_objects: list[PreparedShadowObject] = []
    seen_keys: set[ObjectKey] = set()
    subtree: RebuildSubtree
    for subtree in rebuild_subtrees:
        target_key: ObjectKey
        for target_key in subtree.affected_keys:
            if target_key in seen_keys:
                continue
            seen_keys.add(target_key)
            prepared_shadow_objects.append(
                PreparedShadowObject(
                    logical_key=target_key,
                    physical_name=build_shadow_physical_name(target_key.name, deployment_id),
                )
            )

    return tuple(prepared_shadow_objects)


def build_physical_name_by_key(
    prepared_shadow_objects: tuple[PreparedShadowObject, ...],
) -> dict[ObjectKey, str]:
    """Build a key-to-physical-name lookup for prepared shadow objects."""

    return {
        prepared_shadow_object.logical_key: prepared_shadow_object.physical_name
        for prepared_shadow_object in prepared_shadow_objects
    }


def build_shadow_physical_name(logical_name: str, deployment_id: str) -> str:
    """Build a deterministic physical shadow object name."""

    return build_deployment_physical_name(logical_name, deployment_id)


def plan_action_for_key(key: ObjectKey) -> DeploymentAction:
    """Return the plan-phase action for an affected desired object key."""

    if key.object_type == DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW:
        return DEPLOYMENT_ACTION_PLAN_SHADOW_MATERIALIZED_VIEW
    return DEPLOYMENT_ACTION_PLAN_SHADOW_TABLE


def emit_planner_warnings(
    desired_state: DesiredState,
    rebuild_subtrees: tuple[RebuildSubtree, ...],
) -> tuple[PlannerWarning, ...]:
    """Emit planner-visible warnings for staged deployment semantics."""

    warnings: list[PlannerWarning] = []
    subtree: RebuildSubtree
    for subtree in rebuild_subtrees:
        target_key: ObjectKey
        for target_key in subtree.affected_keys:
            if target_key not in desired_state.mutable_ref_warning_keys:
                continue
            warnings.append(
                PlannerWarning(
                    warning_code="mutable_ref_replay_not_guaranteed",
                    message=(
                        "Transform uses mutable side refs; exact historical replay equivalence "
                        "cannot be guaranteed because side-table state may differ from the "
                        "original processing time."
                    ),
                    root_key=subtree.root_key,
                    target_key=target_key,
                )
            )

    return tuple(warnings)
