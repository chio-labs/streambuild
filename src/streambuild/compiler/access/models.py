"""Immutable normalized access-policy models."""

from dataclasses import dataclass

from streambuild.compiler.access.types import GrantScope, Permission


@dataclass(frozen=True)
class CompiledAccessGrant:
    """One normalized project, target, or exact-pipeline grant."""

    permissions: tuple[Permission, ...]
    pipelines: tuple[str, ...] = ()
    scope: GrantScope | None = None


@dataclass(frozen=True)
class CompiledAccessRole:
    """One project-authored operational role."""

    name: str
    description: str | None
    grants: tuple[CompiledAccessGrant, ...]


@dataclass(frozen=True)
class CompiledAccessPolicy:
    """Complete normalized policy compiled with one project analysis."""

    roles: tuple[CompiledAccessRole, ...]
    fingerprint: str
