"""Resolve connection ownership for one CLI invocation."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterConnectionConfig
from streambuild.cli.entry._helpers.entrypoint import resolve_adapter_connection_config
from streambuild.cli.entry.constants import COMMANDS_WITHOUT_ADAPTER_CONNECTION
from streambuild.cli.entry.models import (
    ResolvedCliInvocation,
    ResolvedInvocationConnection,
)


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
    config: AdapterConnectionConfig = resolve_adapter_connection_config(
        host=invocation.connection.host,
        port=invocation.connection.port,
        username=invocation.connection.username,
        password=invocation.connection.password,
        project_connection=invocation.connection.project_connection,
    )
    return ResolvedInvocationConnection(
        connection=invocation.adapter.connect(config),
        close_after_command=True,
    )
