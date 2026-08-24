"""Enforce compiled-policy authorization for dev-server operations."""

from pathlib import Path

from fastapi import HTTPException, Request

from streambuild.auth.classes.control_store import ControlStore
from streambuild.auth.constants import ADMIN_ROLE
from streambuild.auth.main.read_authenticated_request import read_authenticated_request
from streambuild.auth.models import AuthenticatedRequest
from streambuild.authorization.main.authorize_operation import authorize_operation
from streambuild.authorization.main.effective_capabilities import effective_capabilities
from streambuild.authorization.models import (
    AuthorizationDecision,
    AuthorizationRequest,
    CapabilityRequest,
    EffectiveCapabilities,
)
from streambuild.cli.build.models import (
    DirectWorkflowPreparation,
    MixedWorkflowPreparation,
    VirtualWorkflowPreparation,
)
from streambuild.compiler.access.models import CompiledAccessGrant, CompiledAccessRole
from streambuild.compiler.access.types import GrantScope, Permission
from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.compile.models import LogicalResourceKey
from streambuild.compiler.compile.types import LogicalResourceType
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.testing.models import SqlTestCase
from streambuild.dev_server.constants import CHECK_KIND_TEST
from streambuild.dev_server.models import OperationAuthorizationContext
from streambuild.executor.destruction.types import DestructionOperation

_HTTP_FORBIDDEN: int = 403
_MODEL_IDENTITY_PREFIX: str = f"{LogicalResourceType.MODEL}:"


def require_operation_authorization(
    *,
    analysis: CompileAnalysis | None,
    request: Request,
    store: ControlStore,
    project_dir: Path,
    selected_target: str | None,
    permission: Permission,
    grant_scope: GrantScope | None,
    affected_pipelines: tuple[str, ...],
    denial_message: str,
) -> AuthorizationDecision:
    """Return an allow decision or raise a structured forbidden response."""

    authenticated: AuthenticatedRequest = read_authenticated_request(request=request)
    project_name: str = (
        project_dir.resolve().as_posix()
        if analysis is None or analysis.compiled_project.project_name is None
        else analysis.compiled_project.project_name
    )
    target_name: str | None = (
        selected_target
        if analysis is None or analysis.compiled_project.target_name is None
        else analysis.compiled_project.target_name
    )
    decision: AuthorizationDecision = authorize_operation(
        store=store,
        request=AuthorizationRequest(
            authenticated=authenticated,
            permission=permission,
            project_name=project_name,
            target_name=target_name,
            grant_scope=grant_scope,
            affected_pipelines=affected_pipelines,
            policy=None if analysis is None else analysis.access_policy,
        ),
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=_HTTP_FORBIDDEN,
            detail={
                "message": denial_message,
                "permission": decision.permission.value,
                "reason": decision.reason.value,
                "project": decision.project_name,
                "target": decision.target_name,
                "missingPipelines": list(decision.missing_pipelines),
            },
        )
    return decision


def build_access_policy_payload(*, analysis: CompileAnalysis | None) -> dict[str, object]:
    """Serialize the compiled read-only project role policy."""

    if analysis is None or analysis.access_policy is None:
        return {"present": False, "fingerprint": None, "roles": []}
    return {
        "present": True,
        "fingerprint": analysis.access_policy.fingerprint,
        "roles": [_role_payload(role=role) for role in analysis.access_policy.roles],
    }


def _role_payload(*, role: CompiledAccessRole) -> dict[str, object]:
    return {
        "name": role.name,
        "description": role.description,
        "grants": [_grant_payload(grant=grant) for grant in role.grants],
    }


def _grant_payload(*, grant: CompiledAccessGrant) -> dict[str, object]:
    return {
        "scope": None if grant.scope is None else grant.scope.value,
        "pipelines": list(grant.pipelines),
        "permissions": [permission.value for permission in grant.permissions],
    }


def require_check_authorization(
    *,
    analysis: CompileAnalysis,
    request: Request,
    store: ControlStore,
    project_dir: Path,
    selected_target: str | None,
    kind: str,
    name: str,
) -> AuthorizationDecision | None:
    """Authorize one named check; unknown names defer to runner validation."""

    permission: Permission = (
        Permission.QUALITY_TEST_RUN if kind == CHECK_KIND_TEST else Permission.QUALITY_AUDIT_RUN
    )
    scope: tuple[str, ...] | None = _check_pipelines(analysis=analysis, kind=kind, name=name)
    if scope is None:
        return None
    return require_operation_authorization(
        analysis=analysis,
        request=request,
        store=store,
        project_dir=project_dir,
        selected_target=selected_target,
        permission=permission,
        grant_scope=GrantScope.PROJECT if not scope else None,
        affected_pipelines=scope,
        denial_message=f"Running this {kind} is not permitted",
    )


def is_system_admin(*, request: Request) -> bool:
    """Return whether the authenticated caller holds the system admin role."""

    authenticated: AuthenticatedRequest = read_authenticated_request(request=request)
    return ADMIN_ROLE in authenticated.roles


def build_capabilities_payload(
    *,
    analysis: CompileAnalysis | None,
    request: Request,
    context: OperationAuthorizationContext,
) -> dict[str, object]:
    """Serialize the caller's effective project/target capabilities."""

    authenticated: AuthenticatedRequest = read_authenticated_request(request=request)
    project_name: str = (
        context.project_dir.resolve().as_posix()
        if analysis is None or analysis.compiled_project.project_name is None
        else analysis.compiled_project.project_name
    )
    target_name: str | None = (
        context.selected_target
        if analysis is None or analysis.compiled_project.target_name is None
        else analysis.compiled_project.target_name
    )
    pipeline_names: tuple[str, ...] = (
        ()
        if analysis is None
        else tuple(sorted(item.pipeline.name for item in analysis.compiled_project.pipelines))
    )
    capabilities: EffectiveCapabilities = effective_capabilities(
        store=context.store,
        request=CapabilityRequest(
            authenticated=authenticated,
            project_name=project_name,
            target_name=target_name,
            pipeline_names=pipeline_names,
            policy=None if analysis is None else analysis.access_policy,
        ),
    )
    return {
        "systemAdmin": capabilities.system_admin,
        "project": capabilities.project_name,
        "target": capabilities.target_name,
        "permissions": [permission.value for permission in capabilities.permissions],
        "pipelinePermissions": {
            permission.value: list(pipelines)
            for permission, pipelines in capabilities.pipeline_permissions
        },
        "staleRoles": list(capabilities.stale_roles),
    }


def require_prepared_build_authorization(
    *,
    analysis: CompileAnalysis,
    request: Request,
    context: OperationAuthorizationContext,
    preparation: DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation,
) -> None:
    """Require complete pipeline coverage for the resolved build workflow."""

    direct_pipelines: tuple[str, ...] = _direct_pipelines(
        analysis=analysis, preparation=preparation
    )
    virtual_pipelines: tuple[str, ...] = _virtual_pipelines(
        analysis=analysis, preparation=preparation
    )

    def require_scoped(
        *, permission: Permission, pipelines: tuple[str, ...], message: str
    ) -> AuthorizationDecision:
        return require_operation_authorization(
            analysis=analysis,
            request=request,
            store=context.store,
            project_dir=context.project_dir,
            selected_target=context.selected_target,
            permission=permission,
            grant_scope=None,
            affected_pipelines=pipelines,
            denial_message=message,
        )

    if not direct_pipelines and not virtual_pipelines:
        _ = require_scoped(
            permission=Permission.BUILD_DIRECT_RUN,
            pipelines=(),
            message="Build authorization requires a resolvable pipeline scope",
        )
        return
    if direct_pipelines:
        _ = require_scoped(
            permission=Permission.BUILD_DIRECT_RUN,
            pipelines=direct_pipelines,
            message="Direct build writes are not permitted",
        )
    if virtual_pipelines:
        _ = require_scoped(
            permission=Permission.DEPLOYMENT_CREATE,
            pipelines=virtual_pipelines,
            message="Creating staged deployments is not permitted",
        )


def require_run_cancel_authorization(
    *,
    analysis: CompileAnalysis,
    request: Request,
    context: OperationAuthorizationContext,
    invocation_id: str,
    active_runs: list[dict[str, object]],
) -> None:
    """Require BUILD_CANCEL over every pipeline recorded on the run."""

    run: dict[str, object] | None = next(
        (item for item in active_runs if item.get("invocationId") == invocation_id),
        None,
    )
    pipelines: tuple[str, ...] | None = (
        None
        if run is None
        else _pipelines_from_logical_ids(
            analysis=analysis, logical_ids=run.get("executedLogicalIds")
        )
    )
    if pipelines is None:
        raise HTTPException(
            status_code=_HTTP_FORBIDDEN,
            detail={
                "message": f"Cannot resolve pipeline scope for run '{invocation_id}'",
                "reason": "unresolved_scope",
            },
        )
    _ = require_operation_authorization(
        analysis=analysis,
        request=request,
        store=context.store,
        project_dir=context.project_dir,
        selected_target=context.selected_target,
        permission=Permission.BUILD_CANCEL,
        grant_scope=None,
        affected_pipelines=pipelines,
        denial_message="Cancelling this run is not permitted",
    )


def require_kill_authorization(
    *,
    analysis: CompileAnalysis | None,
    request: Request,
    context: OperationAuthorizationContext,
) -> None:
    """Require the target-scoped force-kill recovery permission."""

    _ = require_operation_authorization(
        analysis=analysis,
        request=request,
        store=context.store,
        project_dir=context.project_dir,
        selected_target=context.selected_target,
        permission=Permission.BUILD_KILL,
        grant_scope=GrantScope.TARGET,
        affected_pipelines=(),
        denial_message="Force-killing builds is not permitted",
    )


def require_promotion_authorization(
    *,
    analysis: CompileAnalysis,
    request: Request,
    context: OperationAuthorizationContext,
    deployment_id: str,
    logical_ids: tuple[str, ...],
) -> None:
    """Require DEPLOYMENT_PROMOTE over every pipeline changed by promotion."""

    pipelines: tuple[str, ...] | None = _pipelines_from_logical_ids(
        analysis=analysis, logical_ids=list(logical_ids)
    )
    if pipelines is None or not pipelines:
        raise HTTPException(
            status_code=_HTTP_FORBIDDEN,
            detail={
                "message": (
                    f"Cannot resolve pipeline scope for deployment '{deployment_id}' promotion"
                ),
                "reason": "unresolved_scope",
            },
        )
    _ = require_operation_authorization(
        analysis=analysis,
        request=request,
        store=context.store,
        project_dir=context.project_dir,
        selected_target=context.selected_target,
        permission=Permission.DEPLOYMENT_PROMOTE,
        grant_scope=None,
        affected_pipelines=pipelines,
        denial_message="Promoting this deployment is not permitted",
    )


def require_message_read_authorization(
    *,
    analysis: CompileAnalysis,
    request: Request,
    context: OperationAuthorizationContext,
) -> None:
    """Require the project- or target-scoped raw source-message permission."""

    _ = require_operation_authorization(
        analysis=analysis,
        request=request,
        store=context.store,
        project_dir=context.project_dir,
        selected_target=context.selected_target,
        permission=Permission.SOURCE_MESSAGES_READ,
        grant_scope=GrantScope.TARGET,
        affected_pipelines=(),
        denial_message="Reading raw source messages is not permitted",
    )


def require_cleanup_authorization(
    *,
    analysis: CompileAnalysis | None,
    request: Request,
    context: OperationAuthorizationContext,
) -> None:
    """Require the target-scoped deployment cleanup permission."""

    _ = require_operation_authorization(
        analysis=analysis,
        request=request,
        store=context.store,
        project_dir=context.project_dir,
        selected_target=context.selected_target,
        permission=Permission.DEPLOYMENT_CLEANUP,
        grant_scope=GrantScope.TARGET,
        affected_pipelines=(),
        denial_message="Deployment cleanup is not permitted",
    )


def require_destruction_authorization(
    *,
    analysis: CompileAnalysis,
    request: Request,
    context: OperationAuthorizationContext,
    operation: DestructionOperation | str,
    affected_pipelines: tuple[str, ...],
) -> None:
    """Require the dedicated permission for an exact destructive-operation scope."""

    reset_target: bool = DestructionOperation(operation) == DestructionOperation.RESET_TARGET
    _ = require_operation_authorization(
        analysis=analysis,
        request=request,
        store=context.store,
        project_dir=context.project_dir,
        selected_target=context.selected_target,
        permission=Permission.TARGET_RESET if reset_target else Permission.PIPELINE_DESTROY,
        grant_scope=GrantScope.TARGET if reset_target else None,
        affected_pipelines=() if reset_target else affected_pipelines,
        denial_message=(
            "Resetting this target is not permitted"
            if reset_target
            else "Destroying these pipelines is not permitted"
        ),
    )


def require_automation_authorization(
    *,
    analysis: CompileAnalysis | None,
    request: Request,
    context: OperationAuthorizationContext,
) -> None:
    """Require the target-scoped sensor automation management permission."""

    _ = require_operation_authorization(
        analysis=analysis,
        request=request,
        store=context.store,
        project_dir=context.project_dir,
        selected_target=context.selected_target,
        permission=Permission.AUTOMATION_MANAGE,
        grant_scope=GrantScope.TARGET,
        affected_pipelines=(),
        denial_message="Sensor automation management is not permitted",
    )


def _check_pipelines(*, analysis: CompileAnalysis, kind: str, name: str) -> tuple[str, ...] | None:
    """Return authoritative pipeline scope, or no scope for unknown names."""

    if kind == CHECK_KIND_TEST:
        test_case: SqlTestCase | None = _test_by_name(analysis=analysis, name=name)
        if test_case is None:
            return None
        model_names: tuple[str, ...] = tuple(
            step.target_model_name for step in test_case.target_cases
        )
        return _required_pipelines_for_models(analysis=analysis, model_names=model_names, name=name)
    audit: LoadedSqlAudit | None = _audit_by_name(analysis=analysis, name=name)
    if audit is None:
        return None
    return _required_pipelines_for_models(
        analysis=analysis, model_names=audit.referenced_model_names, name=name
    )


def _required_pipelines_for_models(
    *, analysis: CompileAnalysis, model_names: tuple[str, ...], name: str
) -> tuple[str, ...]:
    pipelines: tuple[str, ...] | None = _pipelines_for_model_names(
        analysis=analysis, model_names=model_names
    )
    if pipelines is None:
        raise HTTPException(
            status_code=_HTTP_FORBIDDEN,
            detail={
                "message": f"Cannot resolve pipeline ownership for check '{name}'",
                "reason": "unresolved_scope",
            },
        )
    return pipelines


def _audit_by_name(*, analysis: CompileAnalysis, name: str) -> LoadedSqlAudit | None:
    for audit in analysis.compiled_project.audits:
        if (audit.name or audit.file_path.stem) == name:
            return audit
    return None


def _test_by_name(*, analysis: CompileAnalysis, name: str) -> SqlTestCase | None:
    for test_case in analysis.compiled_project.test_cases:
        if (test_case.name or test_case.file_path.stem) == name:
            return test_case
    return None


def _direct_pipelines(
    *,
    analysis: CompileAnalysis,
    preparation: DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation,
) -> tuple[str, ...]:
    direct: DirectWorkflowPreparation | None = (
        preparation
        if isinstance(preparation, DirectWorkflowPreparation)
        else preparation.direct
        if isinstance(preparation, MixedWorkflowPreparation)
        else None
    )
    if direct is None:
        return ()
    return _pipelines_for_keys(analysis=analysis, keys=direct.preview.plan.execution_scope)


def _virtual_pipelines(
    *,
    analysis: CompileAnalysis,
    preparation: DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation,
) -> tuple[str, ...]:
    virtual: VirtualWorkflowPreparation | None = (
        preparation
        if isinstance(preparation, VirtualWorkflowPreparation)
        else preparation.virtual
        if isinstance(preparation, MixedWorkflowPreparation)
        else None
    )
    if virtual is None:
        return ()
    return _pipelines_for_keys(analysis=analysis, keys=virtual.preview.run_execution_scope)


def _pipelines_for_keys(
    *, analysis: CompileAnalysis, keys: tuple[LogicalResourceKey, ...]
) -> tuple[str, ...]:
    model_names: tuple[str, ...] = tuple(
        key.name for key in keys if key.resource_type == LogicalResourceType.MODEL
    )
    pipelines: tuple[str, ...] | None = _pipelines_for_model_names(
        analysis=analysis, model_names=model_names
    )
    if pipelines is None:
        raise HTTPException(
            status_code=_HTTP_FORBIDDEN,
            detail={
                "message": "Cannot resolve pipeline ownership for the resolved build scope",
                "reason": "unresolved_scope",
            },
        )
    return pipelines


def _pipelines_from_logical_ids(
    *, analysis: CompileAnalysis, logical_ids: object
) -> tuple[str, ...] | None:
    if not isinstance(logical_ids, list):
        return None
    model_names: list[str] = []
    for item in logical_ids:
        if not isinstance(item, str):
            return None
        if item.startswith(_MODEL_IDENTITY_PREFIX):
            model_names.append(item.removeprefix(_MODEL_IDENTITY_PREFIX))
    return _pipelines_for_model_names(analysis=analysis, model_names=tuple(model_names))


def _pipelines_for_model_names(
    *, analysis: CompileAnalysis, model_names: tuple[str, ...]
) -> tuple[str, ...] | None:
    pipeline_by_model: dict[str, str] = {
        model.key.name: model.pipeline_name for model in analysis.compiled_project.models
    }
    if any(model_name not in pipeline_by_model for model_name in model_names):
        return None
    return tuple(sorted({pipeline_by_model[model_name] for model_name in model_names}))
