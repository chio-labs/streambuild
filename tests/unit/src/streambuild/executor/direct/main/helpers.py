from collections.abc import Iterator
from pathlib import Path

from streambuild.adapter.models import (
    AdapterManagedSource,
    AdapterMaterializedView,
    AdapterOwnershipRecord,
    AdapterQueryResult,
    AdapterReplayRequest,
    AdapterStableView,
    AdapterTable,
)
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.compiler.planner.models import DirectPlan
from streambuild.executor.direct.models import DirectBuildRequest
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection
from tests.unit.src.streambuild.compiler.planner.helpers import (
    analyze_direct_scope_project,
    build_settled_direct_snapshot,
    plan_direct_scope,
    write_direct_scope_project,
)


class RecordingDirectBuildConnection(RecordingAdapterConnection):
    def __init__(self) -> None:
        super().__init__()
        self.adapter_actions: list[str] = []
        self.realized_resource_names: list[str] = []
        self.replay_requests: list[AdapterReplayRequest] = []
        self._query_results: Iterator[AdapterQueryResult] = iter(
            (
                AdapterQueryResult(rows=()),
                AdapterQueryResult(rows=()),
                AdapterQueryResult(
                    rows=((0, 5),), column_names=("_replay_partition", "cutoff_offset")
                ),
                AdapterQueryResult(
                    rows=((0, 5),), column_names=("_replay_partition", "cutoff_offset")
                ),
                AdapterQueryResult(rows=((0, 1, 5),)),
                AdapterQueryResult(rows=((0, 1, 5),)),
            )
        )

    def record_target_ownership(
        self, *, database: str, records: tuple[AdapterOwnershipRecord, ...]
    ) -> None:
        self.adapter_actions.append("record_ownership")
        super().record_target_ownership(database=database, records=records)

    def command(self, statement: str) -> None:
        self.adapter_actions.append(statement)
        super().command(statement)

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return next(self._query_results)

    def realize_resource(
        self,
        *,
        resource: AdapterManagedSource | AdapterTable | AdapterMaterializedView | AdapterStableView,
        database: str,
        if_not_exists: bool = False,
    ) -> None:
        self.realized_resource_names.append(resource.name)
        super().realize_resource(resource=resource, database=database, if_not_exists=if_not_exists)

    def execute_replay(self, request: AdapterReplayRequest) -> None:
        self.adapter_actions.append(f"replay:{request.relations.root}")
        self.replay_requests.append(request)


def build_direct_execution_request(
    *, project_root: Path, selected_model_names: tuple[str, ...]
) -> DirectBuildRequest:
    write_direct_scope_project(project_root=project_root)
    analysis: CompileAnalysis = analyze_direct_scope_project(project_root=project_root)
    plan: DirectPlan = plan_direct_scope(
        analysis=analysis,
        snapshot=build_settled_direct_snapshot(),
        selected_model_names=selected_model_names,
    )
    return DirectBuildRequest(
        plan=plan,
        realized_project=analysis.realized_project,
        database="analytics",
        metadata_database="analytics",
        tool_version="test",
        stabilization_seconds=0,
        boundary_time="2026-07-28 00:00:00.000",
    )
