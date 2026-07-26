from __future__ import annotations

from dataclasses import replace
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterRelationNotFoundError
from streambuild.adapter.models import CatalogSnapshot
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.models import DeploymentPlan, PlannerWarning, RebuildSubtree


def add_empty_replay_source_warnings(
    *,
    client: AdapterConnection,
    catalog: CatalogSnapshot,
    database: str,
    desired_state: DesiredState,
    plan: DeploymentPlan,
) -> DeploymentPlan:
    del desired_state
    warning_by_root_name: dict[str, PlannerWarning] = {
        warning.root_key.name: warning for warning in plan.warnings
    }
    subtree: RebuildSubtree
    for subtree in plan.rebuild_subtrees:
        replay_source_row_count: int | None = _safe_point_in_time_row_count(
            client=client,
            catalog=catalog,
            database=database,
            table_name=subtree.upstream_boundary_key.name,
        )
        if replay_source_row_count != 0:
            continue
        active_row_count: int | None = _safe_point_in_time_row_count(
            client=client,
            catalog=catalog,
            database=database,
            table_name=subtree.root_key.name,
        )
        message: str = (
            f"replay source {subtree.upstream_boundary_key.name} is empty; staged outputs for this "
            "subtree may also be empty"
        )
        if active_row_count is not None and active_row_count > 0:
            message += (
                f" (active target {subtree.root_key.name} currently has {active_row_count} rows)"
            )
        warning_by_root_name[subtree.root_key.name] = PlannerWarning(
            warning_code="empty_replay_source",
            message=message,
            root_key=subtree.root_key,
        )

    return replace(
        plan,
        warnings=tuple(
            sorted(
                warning_by_root_name.values(),
                key=lambda warning: (
                    warning.root_key.database or "",
                    warning.root_key.object_type,
                    warning.root_key.name,
                    warning.warning_code,
                ),
            )
        ),
    )


def _safe_point_in_time_row_count(
    *,
    client: AdapterConnection,
    catalog: CatalogSnapshot,
    database: str,
    table_name: str,
) -> int | None:
    """Return a dynamic point-in-time count outside the immutable catalog snapshot."""

    if catalog.relation(table_name) is None:
        return None
    try:
        rows: tuple[tuple[object, ...], ...] = client.query(
            f"SELECT count() FROM {database}.{table_name}"
        ).rows
    except AdapterRelationNotFoundError:
        return None
    if not rows:
        return None
    return int(cast(int, rows[0][0]))
