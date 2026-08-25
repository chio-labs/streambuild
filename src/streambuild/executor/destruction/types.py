"""Destruction operation and owned-relation types."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from streambuild.adapter.models import (
    AdapterDeploymentInventory,
    AdapterQueryResult,
    CatalogSnapshot,
)

if TYPE_CHECKING:
    from streambuild.executor.destruction.models import DestructionPlan


class DestructionOperation(StrEnum):
    DESTROY_PIPELINES = "destroy_pipelines"
    RESET_TARGET = "reset_target"


class DestructionRelationKind(StrEnum):
    VIEW = "view"
    MATERIALIZED_VIEW = "materialized_view"
    TABLE = "table"
    MANAGED_SOURCE = "managed_source"


class DestructionOwnership(StrEnum):
    CURRENT_MANIFEST = "current_manifest"
    VIRTUAL_PHYSICAL_MAPPING = "virtual_physical_mapping"
    PUBLISHED_STABLE_BINDING = "published_stable_binding"
    OWNERSHIP_LEDGER = "ownership_ledger"


class DestructionPlanningConnection(Protocol):
    """The complete, read-only adapter surface available to planning."""

    def load_catalog(self, database: str) -> CatalogSnapshot: ...

    def load_deployment_inventory(self, database: str) -> AdapterDeploymentInventory: ...

    def load_external_dependants(
        self, *, database: str, relation_names: tuple[str, ...]
    ) -> tuple[str, ...]: ...

    def query(self, statement: str) -> AdapterQueryResult: ...


class DestructionPlanStore(Protocol):
    """Actor-bound storage gate for reviewed, single-use destruction plans."""

    def save(self, *, plan: DestructionPlan, actor: str) -> None: ...

    def get(self, *, plan_id: str, actor: str) -> DestructionPlan: ...

    def mark_reviewed(self, *, plan_id: str, actor: str) -> datetime: ...

    def reviewed_at(self, *, plan_id: str, actor: str) -> datetime: ...

    def consume(
        self,
        *,
        plan_id: str,
        challenge_responses: tuple[str, ...],
        actor: str,
    ) -> DestructionPlan: ...


type DestructionClock = Callable[[], datetime]
