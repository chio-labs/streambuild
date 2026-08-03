"""Selector expansion and DirectPlan serialization for /api/plan."""

from __future__ import annotations

from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.models import (
    DirectPlan,
    DirectPlanEntry,
    DirectPrerequisite,
    DirectRelationOperation,
    DirectReplayRoot,
)
from streambuild.dev_server.exceptions import DevServerError

_PIPELINE_SELECTOR_PREFIX: str = "pipeline:"


def expand_selectors(
    *,
    analysis: CompileAnalysis,
    selectors: tuple[str, ...],
) -> frozenset[LogicalResourceKey]:
    """Expand bare model names and pipeline:<name> selectors into model keys."""

    model_names: frozenset[str] = frozenset(
        model.key.name for model in analysis.compiled_project.models
    )
    pipelines_by_name: dict[str, tuple[str, ...]] = {}
    for pipeline in analysis.compiled_project.pipelines:
        pipelines_by_name[pipeline.pipeline.name] = tuple(
            model.key.name for model in pipeline.models
        )
    selected: set[str] = set()
    selector: str
    for selector in selectors:
        selected.update(
            _expand_one_selector(
                selector=selector,
                model_names=model_names,
                pipelines_by_name=pipelines_by_name,
            )
        )
    return frozenset(
        LogicalResourceKey(resource_type=LogicalResourceType.MODEL, name=name) for name in selected
    )


def _expand_one_selector(
    *,
    selector: str,
    model_names: frozenset[str],
    pipelines_by_name: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    if selector.startswith(_PIPELINE_SELECTOR_PREFIX):
        pipeline_name: str = selector[len(_PIPELINE_SELECTOR_PREFIX) :]
        members: tuple[str, ...] | None = pipelines_by_name.get(pipeline_name)
        if members is None:
            raise DevServerError(f"Unknown pipeline selector '{selector}'")
        return members
    if selector not in model_names:
        raise DevServerError(f"Unknown selector '{selector}'; use a model name or pipeline:<name>")
    return (selector,)


def build_plan_payload(
    *,
    plan: DirectPlan,
    analysis: CompileAnalysis,
    selectors: tuple[str, ...],
    start_time: str | None,
    planned_at: str,
) -> dict[str, object]:
    """Serialize one DirectPlan into the UI plan shape."""

    pipeline_by_model: dict[str, str] = {
        model.key.name: model.pipeline_name for model in analysis.compiled_project.models
    }
    return {
        "database": plan.database,
        "userScope": list(selectors),
        "entries": [
            _entry_payload(entry=entry, pipeline_by_model=pipeline_by_model)
            for entry in plan.entries
        ],
        "prerequisites": [_prerequisite_payload(item) for item in plan.prerequisite_scope],
        "teardown": [_operation_payload(item) for item in plan.teardown_operations],
        "creation": [_operation_payload(item) for item in plan.creation_operations],
        "replayRoots": [_replay_root_payload(item) for item in plan.replay_roots],
        "warnings": [
            {"code": item.warning_code, "message": item.message} for item in plan.warnings
        ],
        "replayWindow": (
            {"mode": "full"} if start_time is None else {"mode": "from", "startTime": start_time}
        ),
        "plannedAt": planned_at,
        "command": _command_string(selectors=selectors, start_time=start_time),
    }


def _command_string(*, selectors: tuple[str, ...], start_time: str | None) -> str:
    parts: list[str] = ["stb build"]
    selector: str
    for selector in selectors:
        parts.append(f"--select {selector}")
    if start_time is not None:
        parts.append(f"--start-time {start_time}")
    return " ".join(parts)


def _entry_payload(
    *,
    entry: DirectPlanEntry,
    pipeline_by_model: dict[str, str],
) -> dict[str, object]:
    return {
        "modelName": entry.model_key.name,
        "pipeline": pipeline_by_model.get(entry.model_key.name),
        "reason": str(entry.reason),
        "relationNames": list(entry.relation_names),
        "resourceKinds": [str(kind) for kind in entry.resource_kinds],
        "ownership": [
            {"relation": item.relation_name, "ownership": str(item.ownership)}
            for item in entry.ownership
        ],
        "drivingInput": None if entry.driving_input_key is None else entry.driving_input_key.name,
        "isReplayRoot": entry.is_replay_root,
    }


def _prerequisite_payload(item: DirectPrerequisite) -> dict[str, object]:
    return {
        "name": item.key.name,
        "type": str(item.key.resource_type),
        "relationNames": list(item.relation_names),
        "present": item.present,
        "frameworkManaged": item.framework_managed,
    }


def _operation_payload(item: DirectRelationOperation) -> dict[str, object]:
    return {
        "relationName": item.relation_name,
        "action": str(item.action),
        "modelName": item.model_key.name,
        "resourceKind": str(item.resource_kind),
    }


def _replay_root_payload(item: DirectReplayRoot) -> dict[str, object]:
    return {
        "modelName": item.model_key.name,
        "drivingInputName": item.driving_input_key.name,
        "drivingInputRelationName": item.driving_input_relation_name,
        "boundaryMode": str(item.replay_boundary_mode),
        "propagatedModelNames": [key.name for key in item.propagated_model_keys],
        "hasAggregateSemantics": item.has_aggregate_semantics,
    }
