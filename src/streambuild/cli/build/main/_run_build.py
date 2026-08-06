"""CLI command for mode-aware builds."""

import sys

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.adapter.models import AdapterInvocationRecord
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
from streambuild.executor.observability.main.build_invocation_record import (
    build_invocation_record,
)
from streambuild.executor.observability.main.persist_terminal_observations import (
    persist_terminal_observations,
)
from streambuild.executor.observability.main.start_invocation import start_invocation
from streambuild.executor.observability.models import TerminalInvocation


def run_build(
    *,
    options: BuildCommandOptions,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Plan and execute one build through the effective project mode."""

    started: tuple[str, str, int] = start_invocation()
    try:
        if options.json_output and not options.auto_approve:
            print("--json requires --auto-approve for build", file=sys.stderr)
            _persist_failed_build(
                started=started,
                options=options,
                client=client,
                error_message="--json requires --auto-approve for build",
            )
            return 1
        if options.events_output and not options.auto_approve:
            print("--events requires --auto-approve for build", file=sys.stderr)
            _persist_failed_build(
                started=started,
                options=options,
                client=client,
                error_message="--events requires --auto-approve for build",
            )
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
                started=started,
            )
        return execute_direct_build_command(
            preparation=preparation,
            options=options,
            client=client,
            started=started,
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
        _persist_failed_build(
            started=started,
            options=options,
            client=client,
            error_message=str(error),
        )
        return 1


def _persist_failed_build(
    *,
    started: tuple[str, str, int],
    options: BuildCommandOptions,
    client: AdapterConnection,
    error_message: str,
) -> None:
    database: str = options.metadata_database or options.database or ""
    invocation: AdapterInvocationRecord = build_invocation_record(
        started=started,
        terminal=TerminalInvocation(
            project_dir=options.pipelines_root.parent,
            target_identity=options.database or "",
            command="build",
            mode=None,
            outcome="failed",
            exit_code=1,
            materialized_outcome=None,
            deployment_id=options.deployment_id,
            workflow_id=None,
            selected_node_count=0,
            error_message=error_message,
            summary={},
        ),
    )
    persist_terminal_observations(
        client=client,
        database=database,
        invocation=invocation,
        node_results=(),
    )
