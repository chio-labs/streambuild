from collections.abc import Iterator
from dataclasses import replace
from typing import cast

from streambuild.adapter.models import (
    AdapterQueryResult,
    AdapterReplayRequest,
    AdapterReplayResult,
)
from streambuild.compiler.compile.models import (
    CompiledPipeline,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
    MaterializedViewSpec,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.executor.population.models import (
    PopulationObject,
    PopulationPlan,
    PopulationRoot,
)
from tests.integration.src.streambuild.executor.backfill.helpers import build_desired_state
from tests.unit.src.streambuild.cli.helpers import RecordingAdapterConnection


class AdoptedFanInConnection(RecordingAdapterConnection):
    def __init__(self, query_results: tuple[AdapterQueryResult, ...]) -> None:
        super().__init__()
        self._query_results: Iterator[AdapterQueryResult] = iter(query_results)
        self.replay_requests: list[AdapterReplayRequest] = []

    def query(self, statement: str) -> AdapterQueryResult:
        self.statements.append(statement)
        return next(self._query_results)

    def execute_replay(self, request: AdapterReplayRequest) -> AdapterReplayResult:
        self.replay_requests.append(request)
        return AdapterReplayResult(written_rows=1)


def build_adopted_fan_in_population(
    *,
    compiled_pipeline: CompiledPipeline,
    replay_lineage_mode: ReplayLineageMode,
    physical_suffix: str,
) -> tuple[DesiredState, PopulationPlan]:
    base_state: DesiredState = build_desired_state((compiled_pipeline,))
    alpha_view: DesiredMaterializedView = cast(DesiredMaterializedView, base_state.objects[0])
    alpha_table: DesiredTable = cast(DesiredTable, base_state.objects[1])
    fan_in_table: DesiredTable = replace(
        alpha_table,
        key=replace(alpha_table.key, name="tbl__orders_fan_in"),
        deps=(alpha_table.key,),
        logical_model_name="orders_fan_in",
    )
    selected_columns: str = ", ".join(column.name for column in fan_in_table.columns)
    fan_in_view: DesiredMaterializedView = replace(
        alpha_view,
        key=replace(alpha_view.key, name="mv__orders_fan_in"),
        deps=(alpha_table.key, fan_in_table.key),
        spec=MaterializedViewSpec(
            source_table_name=alpha_table.name,
            target_table_name=fan_in_table.name,
            query=f"SELECT {selected_columns} FROM {alpha_table.name}",
        ),
        logical_model_name="orders_fan_in",
    )
    desired_state: DesiredState = replace(
        base_state,
        objects=(*base_state.objects, fan_in_view, fan_in_table),
    )
    plan: PopulationPlan = PopulationPlan(
        execution_id=f"fan-in-{physical_suffix or 'direct'}",
        roots=(
            PopulationRoot(
                root_key=fan_in_table.key,
                affected_keys=(fan_in_table.key, fan_in_view.key),
                upstream_boundary_key=alpha_table.key,
                replay_lineage_mode=replay_lineage_mode,
            ),
        ),
        objects=(
            PopulationObject(
                logical_key=alpha_table.key,
                physical_name=f"{alpha_table.name}{physical_suffix}",
            ),
            PopulationObject(
                logical_key=fan_in_table.key,
                physical_name=f"{fan_in_table.name}{physical_suffix}",
            ),
            PopulationObject(
                logical_key=fan_in_view.key,
                physical_name=f"{fan_in_view.name}{physical_suffix}",
            ),
        ),
    )
    return desired_state, plan
