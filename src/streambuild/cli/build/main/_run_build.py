"""CLI command for mode-aware builds."""

import sys

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.cli.build._helpers.direct_command import execute_direct_build_command
from streambuild.cli.build._helpers.virtual_command import execute_virtual_build_command
from streambuild.cli.build.main._prepare_build_workflow import prepare_build_workflow
from streambuild.cli.build.models import (
    BuildCommandOptions,
    DirectWorkflowPreparation,
    VirtualWorkflowPreparation,
    WorkflowPreparationOptions,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.executor.backfill.exceptions import BackfillExecutionError
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
        preparation_options: WorkflowPreparationOptions = WorkflowPreparationOptions(
            database=options.database,
            metadata_database=options.metadata_database,
            selectors=options.selectors,
            deployment_id=options.deployment_id,
            full_refresh=options.full_refresh,
            start_time=options.start_time,
            verbose=options.verbose,
        )
        preparation: DirectWorkflowPreparation | VirtualWorkflowPreparation = (
            prepare_build_workflow(
                analysis=analysis,
                options=preparation_options,
                client=client,
                adapter_profile=adapter_profile,
            )
        )
        if isinstance(preparation, VirtualWorkflowPreparation):
            return execute_virtual_build_command(
                preparation=preparation,
                options=options,
                client=client,
            )
        return execute_direct_build_command(
            preparation=preparation,
            options=options,
            client=client,
        )
    except (
        TransformSqlContractError,
        CliUserError,
        DirectPlanError,
        DirectBuildError,
        BackfillExecutionError,
        AdapterError,
        ValueError,
    ) as error:
        print(str(error), file=sys.stderr)
        return 1
