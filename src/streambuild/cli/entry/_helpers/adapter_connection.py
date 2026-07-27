"""Resolve connection ownership for one CLI invocation."""

from collections.abc import Mapping

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterConfigurationError
from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.cli.entry._helpers.entrypoint import resolve_adapter_connection_config
from streambuild.cli.entry.constants import COMMANDS_WITHOUT_ADAPTER_CONNECTION
from streambuild.cli.entry.models import (
    ResolvedCliInvocation,
    ResolvedInvocationConnection,
)
from streambuild.compiler.discovery.main.interpolate_configuration_value import (
    interpolate_configuration_value,
)
from streambuild.compiler.discovery.models import LoadedProject


def resolve_invocation_connection(
    *,
    invocation: ResolvedCliInvocation,
    provided_connection: AdapterConnection | None,
) -> ResolvedInvocationConnection:
    """Resolve a borrowed or CLI-owned connection for one invocation."""

    if invocation.args.command in COMMANDS_WITHOUT_ADAPTER_CONNECTION:
        return ResolvedInvocationConnection(connection=None, close_after_command=False)
    if provided_connection is not None:
        return ResolvedInvocationConnection(
            connection=provided_connection,
            close_after_command=False,
        )
    config: AdapterConnectionConfig = _resolve_connection_config(invocation)
    return ResolvedInvocationConnection(
        connection=invocation.adapter.connect(config),
        close_after_command=True,
    )


def _resolve_connection_config(invocation: ResolvedCliInvocation) -> AdapterConnectionConfig:
    if invocation.connection.raw_project_connection is None:
        return resolve_adapter_connection_config(
            host=invocation.connection.host,
            port=invocation.connection.port,
            username=invocation.connection.username,
            password=invocation.connection.password,
            project_connection=invocation.connection.project_connection,
        )
    raw_values: dict[str, object] = dict(invocation.connection.raw_project_connection.values)
    cli_values: dict[str, object | None] = {
        "host": invocation.connection.host,
        "port": invocation.connection.port,
        "username": invocation.connection.username,
        "password": invocation.connection.password,
    }
    key: str
    value: object | None
    for key, value in cli_values.items():
        if value is not None:
            raw_values[key] = value
    environment: Mapping[str, str] = invocation.connection.environment or {}
    variables: dict[str, object] = dict(invocation.connection.variables)
    expanded_values: dict[str, object] = {
        name: interpolate_configuration_value(
            value=raw_value,
            variables=variables,
            environment=environment,
            field_path=f"connection.{name}",
        )
        for name, raw_value in raw_values.items()
    }
    try:
        return invocation.adapter.build_connection_config(
            values=expanded_values,
            database=invocation.database,
        )
    except AdapterConfigurationError as error:
        loaded_project: LoadedProject | None = invocation.loaded_project
        if loaded_project is None or loaded_project.configuration is None:
            raise
        project_sources: list[str] = [str(loaded_project.configuration.project_source.file_path)]
        if loaded_project.configuration.local_source is not None:
            project_sources.append(str(loaded_project.configuration.local_source.file_path))
        raise AdapterConfigurationError(
            f"Effective connection from {', '.join(project_sources)} is invalid: {error}"
        ) from error
