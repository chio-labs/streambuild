import json
from dataclasses import replace
from pathlib import Path

from streambuild.adapter.models import AdapterQueryResult
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.build._helpers.virtual_preview import build_virtual_build_preview
from streambuild.cli.build.main._run_build import run_build
from streambuild.cli.build.models import (
    BuildCommandOptions,
    VirtualBuildPreviewContext,
    WorkflowPreparationOptions,
)
from streambuild.cli.entry._helpers.compiler_profile import build_compiler_adapter_profile
from streambuild.cli.plan.main.render_plan_result import render_plan_result
from streambuild.cli.workflow_artifacts.main._publish_build_workflow import publish_build_workflow
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.models import DirectWarehouseSnapshot
from streambuild.executor.backfill.main.assemble_virtual_build_workflow import (
    assemble_virtual_build_workflow,
)
from streambuild.executor.backfill.models import BackfillBootstrapRequest
from streambuild.executor.workflow.models import BuildWorkflow, PublishedBuildWorkflow
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.compiler.planner.helpers import build_settled_direct_snapshot


class _VirtualArtifactConnection(RecordingAdapterConnection):
    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        rows: tuple[tuple[str, ...], ...] = {
            False: (),
            True: (("2026-08-01 12:00:01.000",),),
        }[statement.startswith("SELECT any(cutoff_value) AS boundary_time ")]
        return AdapterQueryResult(rows=rows)


def run_scope_project_build(*, project_root: Path, json_output: bool, auto_approve: bool) -> int:
    """Run `stb build` against the scope project with a settled fake warehouse."""

    return run_scope_project_build_with_connection(
        project_root=project_root,
        json_output=json_output,
        auto_approve=auto_approve,
        connection=build_scope_project_connection(),
    )


def build_scope_project_connection() -> RecordingAdapterConnection:
    """Build the settled recording connection shared by direct command tests."""

    snapshot: DirectWarehouseSnapshot = build_settled_direct_snapshot()
    snapshot = replace(
        snapshot,
        catalog=replace(
            snapshot.catalog,
            relations=snapshot.catalog.relations[3:],
        ),
    )
    return RecordingAdapterConnection(
        relations=snapshot.catalog.relations,
        ownership_records=snapshot.ownership_records,
    )


def run_scope_project_build_with_connection(
    *,
    project_root: Path,
    json_output: bool,
    auto_approve: bool,
    connection: RecordingAdapterConnection,
) -> int:
    """Run a direct build with an observable recording connection."""

    return run_build(
        options=BuildCommandOptions(
            pipelines_root=project_root / "pipelines",
            database=None,
            metadata_database=None,
            selectors=(),
            json_output=json_output,
            verbose=False,
            auto_approve=auto_approve,
        ),
        client=connection,
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )


def publish_scope_project_virtual_workflow(
    *, project_root: Path, deployment_id: str
) -> PublishedBuildWorkflow:
    """Publish the approved virtual workflow without executing its warehouse statements."""

    connection: RecordingAdapterConnection = RecordingAdapterConnection()
    analysis: CompileAnalysis = analyze_project(
        pipelines_root=project_root / "pipelines",
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )
    options: WorkflowPreparationOptions = WorkflowPreparationOptions(
        database=None,
        metadata_database=None,
        selectors=(),
        deployment_id=deployment_id,
        full_refresh=False,
        start_time=None,
        verbose=False,
    )
    preview: VirtualBuildPreviewContext = build_virtual_build_preview(
        options=options,
        start_time_utc=None,
        client=connection,
        analysis=analysis,
    )
    plan_payload: dict[str, object] = json.loads(
        render_plan_result(
            plan=preview.plan,
            desired_state=preview.desired_state,
            database=preview.database,
            adapter_name=connection.adapter_identity.name,
            json_output=True,
            verbose=False,
        )
    )
    plan_payload["deployment_created_at"] = preview.created_at
    request: BackfillBootstrapRequest = BackfillBootstrapRequest(
        desired_state=preview.desired_state,
        default_database=preview.database,
        metadata_database=preview.metadata_database,
        replay_lineage_mode=preview.replay_lineage_mode,
        confirmed_plan=preview.plan,
        deployment_id=preview.deployment_id,
        created_at=preview.created_at,
        confirmed_target_catalog=preview.target_catalog,
        confirmed_metadata_catalog=preview.metadata_catalog,
    )
    workflow: BuildWorkflow = assemble_virtual_build_workflow(
        request=request,
        client=connection,
        plan_json=json.dumps(plan_payload, indent=2),
    )
    return publish_build_workflow(target_dir=project_root / "target", workflow=workflow)


def run_scope_project_virtual_build(*, project_root: Path, deployment_id: str) -> int:
    """Run the production virtual command against a deterministic recording connection."""

    return run_build(
        options=BuildCommandOptions(
            pipelines_root=project_root / "pipelines",
            database=None,
            metadata_database=None,
            selectors=(),
            deployment_id=deployment_id,
            json_output=True,
            verbose=False,
            auto_approve=True,
        ),
        client=_VirtualArtifactConnection(),
        loaded_project=load_project_input_for_path(path=project_root),
        adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
    )
