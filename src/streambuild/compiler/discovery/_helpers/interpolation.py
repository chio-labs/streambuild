"""Invocation-local project variable and environment interpolation."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import cast

from streambuild.compiler.discovery.constants import INTERPOLATION_NAMESPACE_SEPARATOR
from streambuild.compiler.discovery.exceptions import ProjectConfigError

_TOKEN_PATTERN: re.Pattern[str] = re.compile(r"\$\{([^{}]+)\}")
_WHOLE_TOKEN_PATTERN: re.Pattern[str] = re.compile(r"^\$\{([^{}]+)\}$")


def resolve_variable_values(
    *,
    values: Mapping[str, object],
    environment: Mapping[str, str],
    field_path_prefix: str,
    defer_missing_environment: bool = False,
) -> dict[str, object]:
    """Resolve all effective variable values with cycle detection."""

    resolved: dict[str, object] = {}
    name: str
    for name in sorted(values):
        resolved[name] = _resolve_variable(
            name=name,
            values=values,
            environment=environment,
            resolved=resolved,
            stack=(),
            field_path_prefix=field_path_prefix,
            defer_missing_environment=defer_missing_environment,
        )
    return resolved


def interpolate_config_value(
    *,
    value: object,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    field_path: str,
) -> object:
    """Interpolate one effective non-connection configuration value."""

    lazy_variables: dict[str, object] = _LazyVariableMapping(
        values=variables,
        environment=environment,
        resolved={},
        stack=(),
        field_path_prefix=field_path,
        defer_missing_environment=False,
    )
    return _interpolate_value(
        value=value,
        variables=lazy_variables,
        environment=environment,
        field_path=field_path,
        defer_missing_environment=False,
    )


def _resolve_variable(
    *,
    name: str,
    values: Mapping[str, object],
    environment: Mapping[str, str],
    resolved: dict[str, object],
    stack: tuple[str, ...],
    field_path_prefix: str,
    defer_missing_environment: bool,
) -> object:
    if name in resolved:
        return resolved[name]
    if name in stack:
        cycle: str = " -> ".join((*stack, name))
        raise ProjectConfigError(f"{field_path_prefix} variable interpolation cycle: {cycle}")
    if name not in values:
        raise ProjectConfigError(f"{field_path_prefix} unknown project variable '{name}'")
    raw_value: object = values[name]
    nested_stack: tuple[str, ...] = (*stack, name)
    variable_resolver: dict[str, object] = _LazyVariableMapping(
        values=values,
        environment=environment,
        resolved=resolved,
        stack=nested_stack,
        field_path_prefix=field_path_prefix,
        defer_missing_environment=defer_missing_environment,
    )
    value: object = _interpolate_value(
        value=raw_value,
        variables=variable_resolver,
        environment=environment,
        field_path=f"{field_path_prefix} vars.{name}",
        defer_missing_environment=defer_missing_environment,
    )
    resolved[name] = value
    return value


class _LazyVariableMapping(dict[str, object]):
    def __init__(
        self,
        *,
        values: Mapping[str, object],
        environment: Mapping[str, str],
        resolved: dict[str, object],
        stack: tuple[str, ...],
        field_path_prefix: str,
        defer_missing_environment: bool,
    ) -> None:
        super().__init__()
        self._values: Mapping[str, object] = values
        self._environment: Mapping[str, str] = environment
        self._resolved: dict[str, object] = resolved
        self._stack: tuple[str, ...] = stack
        self._field_path_prefix: str = field_path_prefix
        self._defer_missing_environment: bool = defer_missing_environment

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._values

    def __getitem__(self, name: str) -> object:
        return _resolve_variable(
            name=name,
            values=self._values,
            environment=self._environment,
            resolved=self._resolved,
            stack=self._stack,
            field_path_prefix=self._field_path_prefix,
            defer_missing_environment=self._defer_missing_environment,
        )


def _interpolate_value(
    *,
    value: object,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    field_path: str,
    defer_missing_environment: bool,
) -> object:
    if isinstance(value, str):
        return _interpolate_string(
            value=value,
            variables=variables,
            environment=environment,
            field_path=field_path,
            defer_missing_environment=defer_missing_environment,
        )
    if isinstance(value, (list, tuple)):
        return tuple(
            _interpolate_value(
                value=item,
                variables=variables,
                environment=environment,
                field_path=f"{field_path}[{index}]",
                defer_missing_environment=defer_missing_environment,
            )
            for index, item in enumerate(value)
        )
    if isinstance(value, Mapping):
        mapping: Mapping[str, object] = cast(Mapping[str, object], value)
        return {
            key: _interpolate_value(
                value=item,
                variables=variables,
                environment=environment,
                field_path=f"{field_path}.{key}",
                defer_missing_environment=defer_missing_environment,
            )
            for key, item in sorted(mapping.items())
        }
    return value


def _interpolate_string(
    *,
    value: str,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    field_path: str,
    defer_missing_environment: bool,
) -> object:
    whole_match: re.Match[str] | None = _WHOLE_TOKEN_PATTERN.fullmatch(value)
    if whole_match is not None:
        return _token_value(
            token=whole_match.group(1),
            variables=variables,
            environment=environment,
            field_path=field_path,
            defer_missing_environment=defer_missing_environment,
        )
    rendered: str = value
    token_match: re.Match[str]
    for token_match in tuple(_TOKEN_PATTERN.finditer(value)):
        token_value: object = _token_value(
            token=token_match.group(1),
            variables=variables,
            environment=environment,
            field_path=field_path,
            defer_missing_environment=defer_missing_environment,
        )
        if isinstance(token_value, (tuple, list, Mapping)):
            raise ProjectConfigError(
                f"{field_path} cannot interpolate an object or array into text; "
                "consume the value through a macro"
            )
        rendered = rendered.replace(token_match.group(0), _scalar_text(token_value))
    return rendered


def _token_value(
    *,
    token: str,
    variables: Mapping[str, object],
    environment: Mapping[str, str],
    field_path: str,
    defer_missing_environment: bool,
) -> object:
    if token.startswith("ENV:"):
        environment_name: str = token.removeprefix("ENV:")
        if not environment_name or environment_name not in environment:
            if defer_missing_environment and environment_name:
                return f"${{ENV:{environment_name}}}"
            raise ProjectConfigError(
                f"{field_path} references missing environment variable '{environment_name}'"
            )
        return environment[environment_name]
    if INTERPOLATION_NAMESPACE_SEPARATOR in token:
        namespace: str = token.split(INTERPOLATION_NAMESPACE_SEPARATOR, 1)[0]
        raise ProjectConfigError(
            f"{field_path} uses unsupported interpolation namespace '{namespace}'"
        )
    if token not in variables:
        raise ProjectConfigError(f"{field_path} references unknown project variable '{token}'")
    return variables[token]


def _scalar_text(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
