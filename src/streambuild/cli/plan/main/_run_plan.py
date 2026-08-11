"""CLI command for mode-aware execution planning."""

import sys

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterError
from streambuild.cli.build.main.prepare_build_workflow import prepare_build_workflow
from streambuild.cli.build.models import (
    DirectWorkflowPreparation,
    MixedWorkflowPreparation,
    VirtualWorkflowPreparation,
    WorkflowPreparationOptions,
)
from streambuild.cli.entry.exceptions import CliUserError
from streambuild.cli.plan.models import PlanCommandOptions
from streambuild.cli.workflow_artifacts.main._publish_plan_workflow import publish_plan_workflow
from streambuild.compiler.compile.exceptions import TransformSqlContractError
from streambuild.compiler.compile.models import CompilerAdapterProfile
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.exceptions import DirectPlanError
from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.executor.direct.exceptions import DirectBuildError


def run_plan(
    *,
    options: PlanCommandOptions,
    client: AdapterConnection,
    loaded_project: LoadedProject | None,
    adapter_profile: CompilerAdapterProfile,
) -> int:
    """Plan the effective mode's execution against live warehouse state."""

    try:
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=options.pipelines_root,
            loaded_project=loaded_project,
            adapter_profile=adapter_profile,
        )
        preparation_options: WorkflowPreparationOptions = WorkflowPreparationOptions(
            database=options.database,
            metadata_database=None,
            selectors=options.selectors,
            deployment_id=options.deployment_id,
            full_refresh=options.full_refresh,
            start_time=options.start_time,
            verbose=options.verbose,
        )
        preparation: (
            DirectWorkflowPreparation | MixedWorkflowPreparation | VirtualWorkflowPreparation
        ) = prepare_build_workflow(
            analysis=analysis,
            options=preparation_options,
            client=client,
            adapter_profile=adapter_profile,
        )
        if not isinstance(preparation, MixedWorkflowPreparation):
            publish_plan_workflow(
                target_dir=options.pipelines_root.parent / "target",
                workflow=(
                    preparation.workflow.template
                    if isinstance(preparation, DirectWorkflowPreparation)
                    else preparation.workflow
                ),
                is_template=isinstance(preparation, DirectWorkflowPreparation),
            )
        if options.json_output:
            rendered_output: str = (
                preparation.plan_json
                if isinstance(preparation, MixedWorkflowPreparation)
                else preparation.workflow.plan_json
            )
        else:
            rendered_output = preparation.plan_text + "\n"
        print(rendered_output, end="")
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
    return 0
