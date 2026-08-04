from pathlib import Path

from streambuild.adapter.models import AdapterMutationResult, AdapterQueryResult
from streambuild.adapters.clickhouse._helpers.metadata import (
    render_clickhouse_metadata_migration_workflow,
)
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.models import DirectPlan, DirectWarehouseSnapshot
from streambuild.executor.direct.models import DirectBuildRequest
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.compiler.planner.helpers import (
    analyze_direct_scope_project,
    build_direct_snapshot,
    plan_direct_scope,
    write_direct_scope_project,
)


class RecordingDirectBuildConnection(RecordingAdapterConnection):
    def __init__(self) -> None:
        snapshot: DirectWarehouseSnapshot = _direct_prerequisite_snapshot()
        super().__init__(relations=snapshot.catalog.relations)
        self.workflow_mutation_statements: list[str] = []

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return AdapterQueryResult(rows=())

    def execute_workflow_sql(self, statement: str) -> AdapterMutationResult:
        self.workflow_mutation_statements.append(statement)
        return AdapterMutationResult(written_rows=7)

    def render_migrate_metadata_state(self, database: str) -> tuple[str, ...]:
        return render_clickhouse_metadata_migration_workflow(database)


def build_direct_execution_request(
    *, project_root: Path, selected_model_names: tuple[str, ...]
) -> DirectBuildRequest:
    write_direct_scope_project(project_root=project_root)
    analysis: CompileAnalysis = analyze_direct_scope_project(project_root=project_root)
    plan: DirectPlan = plan_direct_scope(
        analysis=analysis,
        snapshot=_direct_prerequisite_snapshot(),
        selected_model_names=selected_model_names,
    )
    return DirectBuildRequest(
        plan=plan,
        realized_project=analysis.realized_project,
        database="analytics",
        metadata_database="analytics",
        tool_version="test",
        stabilization_seconds=0,
    )


def _direct_prerequisite_snapshot() -> DirectWarehouseSnapshot:
    return build_direct_snapshot(
        relation_names=("tbl__alpha", "mv__alpha"),
    )
