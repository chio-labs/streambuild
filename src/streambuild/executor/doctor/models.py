"""Doctor runtime models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DoctorRequest:
    """Input required to inspect active-view health."""

    default_database: str


@dataclass(frozen=True)
class ActiveViewStatus:
    """Diagnosis for one logical managed table."""

    table_name: str
    state_kind: str
    active_deployment_id: str | None
    candidate_deployment_ids: tuple[str, ...]


@dataclass(frozen=True)
class DoctorResult:
    """Read-only diagnosis of active-view health."""

    active_views: tuple[ActiveViewStatus, ...]
