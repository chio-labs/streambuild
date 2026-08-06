"""`stb dev` command handler."""

from __future__ import annotations

from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.dev.classes.dev_terminal_reporter import DevTerminalReporter
from streambuild.cli.dev.models import DevCommandOptions
from streambuild.cli.presentation.main._cli_style import cli_style
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server.main.run_dev_server import run_dev_server
from streambuild.dev_server.models import DevExecutionContext


def run_dev(
    *,
    options: DevCommandOptions,
    client: AdapterConnection | None,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Serve the dev UI and API over this project until interrupted."""

    project_dir: Path = options.pipelines_root.parent
    execution_context: DevExecutionContext = DevExecutionContext(
        database=options.database,
        selected_target=options.selected_target,
        cli_variables=options.cli_variables,
        environment=options.environment,
        connection_host=options.connection_host,
        connection_port=options.connection_port,
        connection_username=options.connection_username,
        connection_password=options.connection_password,
    )

    def run_compile() -> CompileAnalysis:
        reloaded: LoadedProject | None = (
            load_project_input_for_path(
                path=project_dir,
                selected_target=execution_context.selected_target,
                cli_variables=dict(execution_context.cli_variables),
                environment=execution_context.environment,
            )
            if loaded_project is not None
            else None
        )
        return analyze_project(
            pipelines_root=options.pipelines_root,
            loaded_project=reloaded,
            adapter_profile=adapter_profile,
        )

    return run_dev_server(
        run_compile=run_compile,
        connection=client,
        database=options.database,
        project_dir=project_dir,
        host=options.host,
        port=options.port,
        reporter=DevTerminalReporter(style=cli_style()),
        execution_context=execution_context,
    )
