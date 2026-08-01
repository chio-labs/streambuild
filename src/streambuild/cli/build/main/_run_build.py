"""CLI command for mode-aware builds."""

import sys

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.cli.build._helpers.direct_command import execute_direct_build_command
from streambuild.cli.build._helpers.virtual_command import execute_virtual_build_command
from streambuild.cli.build.models import BuildCommandOptions
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.executor.direct.exceptions import DirectBuildError


def run_build(
    *,
    options: BuildCommandOptions,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Plan and execute one build through the effective project mode."""

    try:
        if options.json_output and not options.auto_approve:
            print("--json requires --auto-approve for build", file=sys.stderr)
            return 1
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=options.pipelines_root,
            loaded_project=loaded_project,
            adapter_profile=adapter_profile,
        )
        if analysis.compile_inputs.virtual_environments:
            return execute_virtual_build_command(analysis=analysis, options=options, client=client)
        return execute_direct_build_command(
            analysis=analysis,
            options=options,
            client=client,
            adapter_profile=adapter_profile,
        )
    except (
        TransformSqlContractError,
        CliUserError,
        DirectPlanError,
        DirectBuildError,
        AdapterError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1
