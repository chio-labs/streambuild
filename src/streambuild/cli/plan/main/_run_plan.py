"""CLI command for mode-aware execution planning."""

import sys
from pathlib import Path

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.entry.main._resolve_default_database import resolve_default_database
from streambuild.cli.plan._helpers.plan_command import execute_plan_command, validate_plan_flags
from streambuild.cli.plan.models import PlanCommandOptions
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.exceptions import DirectPlanError


def run_plan(
    *,
    pipelines_root: Path,
    database: str | None,
    selectors: tuple[str, ...],
    full_refresh: bool,
    start_time: str | None,
    json_output: bool,
    verbose: bool,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Plan the effective mode's execution against live warehouse state."""

    try:
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=pipelines_root,
            loaded_project=loaded_project,
            adapter_profile=adapter_profile,
        )
        options: PlanCommandOptions = PlanCommandOptions(
            database=resolve_default_database(
                loaded_pipelines=list(analysis.compile_inputs.pipelines), override=database
            ),
            selectors=selectors,
            full_refresh=full_refresh,
            start_time=start_time,
            json_output=json_output,
            verbose=verbose,
        )
        validate_plan_flags(options=options)
        print(execute_plan_command(analysis=analysis, options=options, client=client))
    except (TransformSqlContractError, CliUserError, DirectPlanError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0
