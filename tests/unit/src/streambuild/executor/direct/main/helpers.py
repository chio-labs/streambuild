from pathlib import Path

from streambuild.adapter.exceptions import AdapterAuthenticationError
from streambuild.adapter.models import (
    AdapterDirectFingerprintRecord,
    AdapterMutationResult,
    AdapterQueryResult,
)
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


class DistinctCaptureDirectBuildConnection(RecordingDirectBuildConnection):
    def __init__(self) -> None:
        super().__init__()
        self._capture_results: list[AdapterQueryResult] = [
            AdapterQueryResult(rows=()),
            _capture_result(lower_value="10", upper_value="11"),
            _capture_result(lower_value="20", upper_value="21"),
        ]

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return self._capture_results.pop(0)


class MismatchedCaptureDirectBuildConnection(DistinctCaptureDirectBuildConnection):
    def __init__(self) -> None:
        super().__init__()
        self._capture_results[1] = _capture_result(
            lower_value="10",
            upper_value="11",
            driving_input_relation_name="tbl__wrong_root",
        )


class InvalidOffsetCaptureDirectBuildConnection(DistinctCaptureDirectBuildConnection):
    def __init__(self) -> None:
        super().__init__()
        invalid_result: AdapterQueryResult = self._capture_results[1]
        self._capture_results[1] = AdapterQueryResult(
            rows=(
                (
                    "tbl__alpha",
                    "offsets",
                    "_replay_offsets",
                    None,
                    *invalid_result.rows[0][4:],
                ),
            ),
            column_names=invalid_result.column_names,
        )


class DeniedFingerprintRenderingConnection(RecordingDirectBuildConnection):
    def render_direct_fingerprint_observations(
        self,
        *,
        database: str,
        fingerprints: tuple[AdapterDirectFingerprintRecord, ...],
    ) -> tuple[str, ...]:
        del database, fingerprints
        raise AdapterAuthenticationError("injected fingerprint rendering denial")


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


def build_direct_execution_snapshot() -> DirectWarehouseSnapshot:
    return _direct_prerequisite_snapshot()


def _capture_result(
    *,
    lower_value: str,
    upper_value: str,
    driving_input_relation_name: str = "tbl__alpha",
) -> AdapterQueryResult:
    return AdapterQueryResult(
        rows=(
            (
                driving_input_relation_name,
                "offsets",
                "_replay_partition=0",
                "0",
                "_replay_partition",
                "_replay_offset",
                "_replay_timestamp",
                lower_value,
                upper_value,
                upper_value,
                True,
                "2026-08-07 12:00:00.000",
            ),
        ),
        column_names=(
            "driving_input_relation_name",
            "replay_boundary_mode",
            "boundary_key",
            "partition_value",
            "source_partition_column_name",
            "source_position_column_name",
            "source_timestamp_column_name",
            "lower_value",
            "upper_value",
            "replay_cutoff_value",
            "cutoff_inclusive",
            "captured_at",
        ),
    )


def _direct_prerequisite_snapshot() -> DirectWarehouseSnapshot:
    return build_direct_snapshot(
        relation_names=("tbl__alpha", "mv__alpha"),
    )
