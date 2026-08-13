"""Validate and normalize the authored access-policy object schema."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Never, cast

from streambuild.compiler.access.constants import (
    GRANT_KEYS,
    PIPELINE_PERMISSIONS,
    PIPELINES_KEY,
    PROJECT_PERMISSIONS,
    PROTECTED_ROLE_NAMES,
    ROLE_KEYS,
    SCOPE_KEY,
    SYSTEM_ONLY_PERMISSIONS,
    TARGET_PERMISSIONS,
    TOP_LEVEL_KEYS,
)
from streambuild.compiler.access.exceptions import AccessPolicyError
from streambuild.compiler.access.models import (
    CompiledAccessGrant,
    CompiledAccessRole,
)
from streambuild.compiler.access.types import GrantScope, Permission
from streambuild.diagnostics.models import SourceLocation


def build_compiled_roles(
    *, document: object, pipeline_names: frozenset[str], source_path: Path
) -> tuple[CompiledAccessRole, ...]:
    """Validate one loaded document and return normalized roles."""

    root: Mapping[str, object] = _string_mapping(
        value=document, context="access policy", source_path=source_path
    )
    _reject_unknown_keys(
        values=root, allowed=TOP_LEVEL_KEYS, context="access policy", source_path=source_path
    )
    roles_value: object = root.get("roles")
    roles: Mapping[str, object] = _string_mapping(
        value=roles_value, context="roles", source_path=source_path
    )
    return tuple(
        _build_role(
            role_name=role_name,
            value=roles[role_name],
            pipeline_names=pipeline_names,
            source_path=source_path,
        )
        for role_name in sorted(roles)
    )


def _build_role(
    *, role_name: str, value: object, pipeline_names: frozenset[str], source_path: Path
) -> CompiledAccessRole:
    if not role_name.strip() or role_name != role_name.strip():
        _fail(
            message="role names must be non-empty and must not contain surrounding whitespace",
            source_path=source_path,
        )
    if role_name in PROTECTED_ROLE_NAMES:
        _fail(
            message=f"role '{role_name}' is protected and cannot be declared in access.yml",
            source_path=source_path,
        )
    role: Mapping[str, object] = _string_mapping(
        value=value, context=f"role '{role_name}'", source_path=source_path
    )
    _reject_unknown_keys(
        values=role,
        allowed=ROLE_KEYS,
        context=f"role '{role_name}'",
        source_path=source_path,
    )
    description: str | None = _optional_string(
        value=role.get("description"),
        context=f"role '{role_name}' description",
        source_path=source_path,
    )
    grants: Sequence[object] = _sequence(
        value=role.get("grants"), context=f"role '{role_name}' grants", source_path=source_path
    )
    if not grants:
        _fail(
            message=f"role '{role_name}' must contain at least one grant",
            source_path=source_path,
        )
    compiled_grants: tuple[CompiledAccessGrant, ...] = tuple(
        _build_grant(
            role_name=role_name,
            grant_index=index,
            value=grant,
            pipeline_names=pipeline_names,
            source_path=source_path,
        )
        for index, grant in enumerate(grants)
    )
    return CompiledAccessRole(
        name=role_name,
        description=description,
        grants=tuple(sorted(compiled_grants, key=_grant_sort_key)),
    )


def _build_grant(
    *,
    role_name: str,
    grant_index: int,
    value: object,
    pipeline_names: frozenset[str],
    source_path: Path,
) -> CompiledAccessGrant:
    context: str = f"role '{role_name}' grant {grant_index + 1}"
    grant: Mapping[str, object] = _string_mapping(
        value=value, context=context, source_path=source_path
    )
    _reject_unknown_keys(values=grant, allowed=GRANT_KEYS, context=context, source_path=source_path)
    has_pipelines: bool = PIPELINES_KEY in grant
    has_scope: bool = SCOPE_KEY in grant
    if has_pipelines == has_scope:
        _fail(
            message=f"{context} must contain exactly one of 'pipelines' or 'scope'",
            source_path=source_path,
        )
    permissions: tuple[Permission, ...] = _permissions(
        value=grant.get("permissions"), context=context, source_path=source_path
    )
    if has_pipelines:
        pipelines: tuple[str, ...] = _unique_strings(
            value=grant[PIPELINES_KEY], context=f"{context} pipelines", source_path=source_path
        )
        unknown: tuple[str, ...] = tuple(sorted(set(pipelines) - pipeline_names))
        if unknown:
            _fail(
                message=f"{context} references unknown pipelines: {', '.join(unknown)}",
                source_path=source_path,
            )
        invalid: tuple[Permission, ...] = tuple(
            permission for permission in permissions if permission not in PIPELINE_PERMISSIONS
        )
        if invalid:
            _fail(
                message=(
                    f"{context} cannot grant pipeline permission(s): {_permission_list(invalid)}"
                ),
                source_path=source_path,
            )
        return CompiledAccessGrant(permissions=permissions, pipelines=tuple(sorted(pipelines)))
    scope: GrantScope = _scope(value=grant[SCOPE_KEY], context=context, source_path=source_path)
    allowed: frozenset[Permission] = (
        PROJECT_PERMISSIONS if scope == GrantScope.PROJECT else TARGET_PERMISSIONS
    )
    invalid = tuple(permission for permission in permissions if permission not in allowed)
    if invalid:
        _fail(
            message=f"{context} cannot grant {_permission_list(invalid)} at {scope.value} scope",
            source_path=source_path,
        )
    return CompiledAccessGrant(permissions=permissions, scope=scope)


def _permissions(*, value: object, context: str, source_path: Path) -> tuple[Permission, ...]:
    names: tuple[str, ...] = _unique_strings(
        value=value, context=f"{context} permissions", source_path=source_path
    )
    permissions: list[Permission] = []
    for name in names:
        try:
            permission: Permission = Permission(name)
        except ValueError:
            _fail(
                message=f"{context} contains unknown permission '{name}'",
                source_path=source_path,
            )
        if permission in SYSTEM_ONLY_PERMISSIONS:
            _fail(
                message=f"{context} cannot grant system-only permission '{permission.value}'",
                source_path=source_path,
            )
        permissions.append(permission)
    return tuple(sorted(permissions, key=lambda item: item.value))


def _scope(*, value: object, context: str, source_path: Path) -> GrantScope:
    if not isinstance(value, str):
        _fail(message=f"{context} scope must be 'project' or 'target'", source_path=source_path)
    try:
        return GrantScope(value)
    except ValueError:
        _fail(
            message=f"{context} scope must be 'project' or 'target', received '{value}'",
            source_path=source_path,
        )


def _unique_strings(*, value: object, context: str, source_path: Path) -> tuple[str, ...]:
    values: Sequence[object] = _sequence(value=value, context=context, source_path=source_path)
    strings: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            _fail(message=f"{context} must contain non-empty strings", source_path=source_path)
        strings.append(item)
    if len(strings) != len(set(strings)):
        _fail(message=f"{context} contains duplicate values", source_path=source_path)
    if not strings:
        _fail(message=f"{context} must not be empty", source_path=source_path)
    return tuple(strings)


def _string_mapping(*, value: object, context: str, source_path: Path) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _fail(message=f"{context} must be a string-keyed mapping", source_path=source_path)
    return cast(Mapping[str, object], value)


def _sequence(*, value: object, context: str, source_path: Path) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        _fail(message=f"{context} must be a sequence", source_path=source_path)
    return value


def _optional_string(*, value: object, context: str, source_path: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        _fail(message=f"{context} must be a non-empty string", source_path=source_path)
    return value


def _reject_unknown_keys(
    *, values: Mapping[str, object], allowed: frozenset[str], context: str, source_path: Path
) -> None:
    unknown: tuple[str, ...] = tuple(sorted(set(values) - allowed))
    if unknown:
        _fail(
            message=f"{context} contains unknown key(s): {', '.join(unknown)}",
            source_path=source_path,
        )


def _grant_sort_key(grant: CompiledAccessGrant) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    return (
        "pipelines" if grant.scope is None else grant.scope.value,
        grant.pipelines,
        tuple(permission.value for permission in grant.permissions),
    )


def _permission_list(permissions: tuple[Permission, ...]) -> str:
    return ", ".join(permission.value for permission in permissions)


def _fail(*, message: str, source_path: Path) -> Never:
    raise AccessPolicyError(
        message,
        location=SourceLocation(path=source_path, line=1, column=1),
    )
