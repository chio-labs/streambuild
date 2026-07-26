"""Runtime inspection models for ClickHouse deployed state."""

from dataclasses import dataclass

from streambuild.compiler.compile.models import ObjectKey


@dataclass(frozen=True)
class InspectedActiveTableBinding:
    """A stable logical view pointing at an active physical table."""

    database: str
    logical_name: str
    physical_name: str


@dataclass(frozen=True)
class InspectedPhysicalTableCandidate:
    """A deployment-suffixed physical table candidate for a logical root."""

    database: str
    logical_name: str
    physical_name: str


@dataclass(frozen=True)
class InspectedManagedTableState:
    """Inspected managed table state for active-deployment resolution."""

    active_bindings: tuple[InspectedActiveTableBinding, ...]
    physical_candidates: tuple[InspectedPhysicalTableCandidate, ...]


@dataclass(frozen=True)
class RootDeploymentInspection:
    """Inspection result for one managed root logical table."""

    root_key: ObjectKey
    state_kind: str
    active_deployment_id: str | None


@dataclass(frozen=True)
class ActiveBindingSystemRow:
    """Row shape for stable view bindings read from ClickHouse system tables."""

    name: str
    as_select: str


@dataclass(frozen=True)
class PhysicalCandidateSystemRow:
    """Row shape for deployment-suffixed physical table candidates."""

    name: str
