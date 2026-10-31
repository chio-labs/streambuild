"""Entry exposing preserved managed-source planning to build orchestration."""

from __future__ import annotations

from sqltide.adapter.models import CatalogSnapshot
from sqltide.compiler.pipeline.models import RealizedProject
from sqltide.compiler.planner.models import DirectPlan
from sqltide.executor.direct._helpers.sources import (
    plan_preserved_managed_sources as _plan_preserved_managed_sources,
)
from sqltide.executor.population.models import (
    PopulationRealization,
    PopulationSourcePreparation,
)


def plan_preserved_managed_sources(
    *,
    plan: DirectPlan,
    realized_project: RealizedProject,
    catalog: CatalogSnapshot,
    database: str,
) -> tuple[PopulationSourcePreparation, tuple[PopulationRealization, ...]]:
    """Validate preserved sources and plan absent resources without mutation."""

    return _plan_preserved_managed_sources(
        plan=plan,
        realized_project=realized_project,
        catalog=catalog,
        database=database,
    )
