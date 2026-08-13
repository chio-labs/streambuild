"""Evaluate current project-role assignments against one compiled policy."""

from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.constants import ADMIN_ROLE
from streambuild.auth.models import ProjectRoleAssignment
from streambuild.authorization.models import (
    AuthorizationDecision,
    AuthorizationRequest,
    CapabilityRequest,
    EffectiveCapabilities,
)
from streambuild.authorization.types import AuthorizationReason
from streambuild.compiler.access.constants import (
    PIPELINE_PERMISSIONS,
    PROJECT_PERMISSIONS,
    TARGET_PERMISSIONS,
)
from streambuild.compiler.access.models import CompiledAccessGrant, CompiledAccessRole
from streambuild.compiler.access.types import GrantScope, Permission


class ProjectAuthorizer:
    """Resolve project authorization from fresh control-plane membership."""

    def __init__(self, *, store: ControlStore) -> None:
        self._store = store

    def decide(self, *, request: AuthorizationRequest) -> AuthorizationDecision:
        """Return a complete, side-effect-free authorization decision."""

        affected_pipelines: tuple[str, ...] = tuple(sorted(set(request.affected_pipelines)))
        if ADMIN_ROLE in request.authenticated.roles:
            return self._decision(
                request=request,
                affected_pipelines=affected_pipelines,
                allowed=True,
                reason=AuthorizationReason.SYSTEM_ADMIN,
                matched_roles=(ADMIN_ROLE,),
            )
        if request.policy is None:
            return self._decision(
                request=request,
                affected_pipelines=affected_pipelines,
                allowed=False,
                reason=AuthorizationReason.POLICY_ABSENT,
            )
        assignments: tuple[ProjectRoleAssignment, ...] = tuple(
            assignment
            for assignment in self._store.list_project_role_assignments(
                user_id=request.authenticated.principal.user_id,
                project_name=request.project_name,
            )
            if assignment.target_name is None or assignment.target_name == request.target_name
        )
        if not assignments:
            return self._decision(
                request=request,
                affected_pipelines=affected_pipelines,
                allowed=False,
                reason=AuthorizationReason.NO_MATCHING_ASSIGNMENT,
                missing_pipelines=affected_pipelines,
            )
        role_by_name: dict[str, CompiledAccessRole] = {
            role.name: role for role in request.policy.roles
        }
        assigned_roles: tuple[CompiledAccessRole, ...] = tuple(
            role_by_name[assignment.role_name]
            for assignment in assignments
            if assignment.role_name in role_by_name
        )
        if not assigned_roles:
            return self._decision(
                request=request,
                affected_pipelines=affected_pipelines,
                allowed=False,
                reason=AuthorizationReason.STALE_ASSIGNMENT,
                missing_pipelines=affected_pipelines,
            )
        if request.grant_scope is not None:
            matching_role_names: set[str] = set()
            for role in assigned_roles:
                for grant in role.grants:
                    if _is_matching_scoped_grant(grant=grant, request=request):
                        matching_role_names.add(role.name)
                        break
            matching_roles: tuple[str, ...] = tuple(sorted(matching_role_names))
            return self._decision(
                request=request,
                affected_pipelines=affected_pipelines,
                allowed=bool(matching_roles),
                reason=(
                    AuthorizationReason.GRANTED
                    if matching_roles
                    else AuthorizationReason.MISSING_PERMISSION
                ),
                matched_roles=matching_roles,
            )
        if not affected_pipelines:
            return self._decision(
                request=request,
                affected_pipelines=affected_pipelines,
                allowed=False,
                reason=AuthorizationReason.EMPTY_PIPELINE_SCOPE,
            )
        covered_by_role: dict[str, set[str]] = {}
        for role in assigned_roles:
            covered: set[str] = set()
            for grant in role.grants:
                if _is_matching_pipeline_grant(grant=grant, request=request):
                    covered.update(set(grant.pipelines).intersection(affected_pipelines))
                if _is_matching_project_grant(grant=grant, request=request):
                    covered.update(affected_pipelines)
            if covered:
                covered_by_role[role.name] = covered
        covered_pipelines: set[str] = (
            set().union(*covered_by_role.values()) if covered_by_role else set()
        )
        missing_pipelines: tuple[str, ...] = tuple(
            sorted(set(affected_pipelines) - covered_pipelines)
        )
        return self._decision(
            request=request,
            affected_pipelines=affected_pipelines,
            allowed=not missing_pipelines,
            reason=(
                AuthorizationReason.GRANTED
                if not missing_pipelines
                else AuthorizationReason.MISSING_PIPELINES
            ),
            matched_roles=tuple(sorted(covered_by_role)),
            missing_pipelines=missing_pipelines,
        )

    def capabilities(self, *, request: CapabilityRequest) -> EffectiveCapabilities:
        """Summarize the caller's effective operational permissions."""

        if ADMIN_ROLE in request.authenticated.roles:
            return EffectiveCapabilities(
                system_admin=True,
                project_name=request.project_name,
                target_name=request.target_name,
                permissions=_sorted_permissions(PROJECT_PERMISSIONS | TARGET_PERMISSIONS),
                pipeline_permissions=tuple(
                    (permission, tuple(sorted(request.pipeline_names)))
                    for permission in _sorted_permissions(PIPELINE_PERMISSIONS)
                ),
            )
        assignments: tuple[ProjectRoleAssignment, ...] = tuple(
            assignment
            for assignment in self._store.list_project_role_assignments(
                user_id=request.authenticated.principal.user_id,
                project_name=request.project_name,
            )
            if assignment.target_name is None or assignment.target_name == request.target_name
        )
        role_by_name: dict[str, CompiledAccessRole] = (
            {} if request.policy is None else {role.name: role for role in request.policy.roles}
        )
        assigned_names: set[str] = {assignment.role_name for assignment in assignments}
        assigned_roles: tuple[CompiledAccessRole, ...] = tuple(
            role_by_name[name] for name in sorted(assigned_names) if name in role_by_name
        )
        collected_grants: list[CompiledAccessGrant] = []
        for role in assigned_roles:
            collected_grants.extend(role.grants)
        grants: tuple[CompiledAccessGrant, ...] = tuple(collected_grants)
        scoped: list[Permission] = []
        for permission in _sorted_permissions(PROJECT_PERMISSIONS | TARGET_PERMISSIONS):
            if _scoped_permission_granted(grants=grants, permission=permission):
                scoped.append(permission)
        pipeline_permissions: list[tuple[Permission, tuple[str, ...]]] = []
        for permission in _sorted_permissions(PIPELINE_PERMISSIONS):
            covered: tuple[str, ...] = _covered_pipelines(
                grants=grants,
                permission=permission,
                pipeline_names=request.pipeline_names,
            )
            if covered:
                pipeline_permissions.append((permission, covered))
        return EffectiveCapabilities(
            system_admin=False,
            project_name=request.project_name,
            target_name=request.target_name,
            permissions=tuple(scoped),
            pipeline_permissions=tuple(pipeline_permissions),
            stale_roles=tuple(sorted(assigned_names - set(role_by_name))),
        )

    def _decision(
        self,
        *,
        request: AuthorizationRequest,
        affected_pipelines: tuple[str, ...],
        allowed: bool,
        reason: AuthorizationReason,
        matched_roles: tuple[str, ...] = (),
        missing_pipelines: tuple[str, ...] = (),
    ) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=allowed,
            reason=reason,
            permission=request.permission,
            project_name=request.project_name,
            target_name=request.target_name,
            affected_pipelines=affected_pipelines,
            matched_roles=matched_roles,
            missing_pipelines=missing_pipelines,
        )


def _is_matching_pipeline_grant(
    *, grant: CompiledAccessGrant, request: AuthorizationRequest
) -> bool:
    return grant.scope is None and request.permission in grant.permissions


def _is_matching_project_grant(
    *, grant: CompiledAccessGrant, request: AuthorizationRequest
) -> bool:
    return grant.scope == GrantScope.PROJECT and request.permission in grant.permissions


def _is_matching_scoped_grant(*, grant: CompiledAccessGrant, request: AuthorizationRequest) -> bool:
    """Match the exact scope; broader project grants satisfy target requests."""

    if request.permission not in grant.permissions:
        return False
    if grant.scope == request.grant_scope:
        return True
    return request.grant_scope == GrantScope.TARGET and grant.scope == GrantScope.PROJECT


def _sorted_permissions(permissions: frozenset[Permission]) -> tuple[Permission, ...]:
    return tuple(sorted(permissions, key=lambda permission: permission.value))


def _scoped_permission_granted(
    *, grants: tuple[CompiledAccessGrant, ...], permission: Permission
) -> bool:
    return any(grant.scope is not None and permission in grant.permissions for grant in grants)


def _covered_pipelines(
    *,
    grants: tuple[CompiledAccessGrant, ...],
    permission: Permission,
    pipeline_names: tuple[str, ...],
) -> tuple[str, ...]:
    covered: set[str] = set()
    for grant in grants:
        if permission not in grant.permissions:
            continue
        if grant.scope == GrantScope.PROJECT:
            covered.update(pipeline_names)
        if grant.scope is None:
            covered.update(grant.pipelines)
    return tuple(sorted(covered))
