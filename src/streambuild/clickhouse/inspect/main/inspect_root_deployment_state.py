"""Helpers for resolving active deployment state from inspected objects."""

from streambuild.clickhouse.inspect.models import (
    InspectedManagedTableState,
    RootDeploymentInspection,
)
from streambuild.clickhouse.inspect.types import RootDeploymentStateKind
from streambuild.compiler.compile.models import ObjectKey
from streambuild.compiler.planner.main.deployment_id_from_physical_name import (
    deployment_id_from_physical_name,
)
from streambuild.compiler.planner.main.is_deployment_physical_name import (
    is_deployment_physical_name,
)


def inspect_root_deployment_state(
    *,
    inspected_state: InspectedManagedTableState,
    root_key: ObjectKey,
) -> RootDeploymentInspection:
    """Classify one managed root as active, greenfield, or damaged."""

    active_binding_physical_names: tuple[str, ...] = tuple(
        binding.physical_name
        for binding in inspected_state.active_bindings
        if binding.logical_name == root_key.name
        and binding.database == (root_key.database or binding.database)
    )
    physical_candidate_names: tuple[str, ...] = tuple(
        candidate.physical_name
        for candidate in inspected_state.physical_candidates
        if candidate.logical_name == root_key.name
        and candidate.database == (root_key.database or candidate.database)
    )
    if len(active_binding_physical_names) == 1:
        if not is_deployment_physical_name(active_binding_physical_names[0]):
            return RootDeploymentInspection(
                root_key=root_key,
                state_kind=RootDeploymentStateKind.INVALID_ACTIVE_VIEW,
                active_deployment_id=None,
            )
        return RootDeploymentInspection(
            root_key=root_key,
            state_kind=RootDeploymentStateKind.ACTIVE_VIEW_PRESENT,
            active_deployment_id=deployment_id_from_physical_name(active_binding_physical_names[0]),
        )
    if not physical_candidate_names:
        return RootDeploymentInspection(
            root_key=root_key,
            state_kind=RootDeploymentStateKind.GREENFIELD,
            active_deployment_id=None,
        )
    return RootDeploymentInspection(
        root_key=root_key,
        state_kind=RootDeploymentStateKind.LOGICAL_VIEW_MISSING,
        active_deployment_id=None,
    )
