from dataclasses import replace
from typing import cast

import pytest

from streambuild.adapter.models import AdapterQueryResult, AdapterReplayRequest
from streambuild.compiler.compile.models import (
    CompiledPipeline,
    DesiredState,
    DesiredTable,
    ObjectKey,
)
from streambuild.compiler.discovery.types import ReplayLineageMode
from streambuild.executor.population._helpers.replay import execute_population_replay
from streambuild.executor.population._helpers.watermarks import resolve_population_watermarks
from streambuild.executor.population.exceptions import PopulationExecutionError
from streambuild.executor.population.models import (
    PopulationPlan,
    PopulationReplayExecution,
    PopulationWatermark,
)
from tests.integration.src.streambuild.executor.backfill.helpers import (
    build_external_source_cursor_replay_compiled_pipeline,
    build_external_source_offset_replay_compiled_pipeline,
)
from tests.unit.src.streambuild.executor.population._helpers._test_types import (
    AdoptedFanInReplayTestCase,
    WatermarkTraversalErrorTestCase,
)
from tests.unit.src.streambuild.executor.population._helpers.helpers import (
    AdoptedFanInConnection,
    build_adopted_fan_in_population,
)


@pytest.mark.parametrize(
    "test_case",
    (
        AdoptedFanInReplayTestCase(
            description="direct adopted offset fan-in resolves physical cutoff and replays",
            compiled_pipeline_builder=build_external_source_offset_replay_compiled_pipeline,
            replay_lineage_mode=ReplayLineageMode.OFFSETS,
            physical_suffix="",
            watermark_column_names=("_replay_partition", "cutoff_offset"),
            watermark_rows=((2, 11),),
            expected_query_fragments=(
                "FROM analytics.orders_existing",
                "event_partition AS _replay_partition",
                "max(event_offset)",
                "event_landed_at <=",
            ),
            expected_boundary_key="_replay_partition=2",
            expected_cutoff_value="11",
            expected_partition_value="2",
            expected_anchor_suffix="",
            expected_written_rows=1,
        ),
        AdoptedFanInReplayTestCase(
            description=(
                "virtual-environment adopted offset fan-in resolves physical cutoff and replays"
            ),
            compiled_pipeline_builder=build_external_source_offset_replay_compiled_pipeline,
            replay_lineage_mode=ReplayLineageMode.OFFSETS,
            physical_suffix="__dep",
            watermark_column_names=("_replay_partition", "cutoff_offset"),
            watermark_rows=((2, 11),),
            expected_query_fragments=(
                "FROM analytics.orders_existing",
                "event_partition AS _replay_partition",
                "max(event_offset)",
                "event_landed_at <=",
            ),
            expected_boundary_key="_replay_partition=2",
            expected_cutoff_value="11",
            expected_partition_value="2",
            expected_anchor_suffix="__dep",
            expected_written_rows=1,
        ),
        AdoptedFanInReplayTestCase(
            description="direct adopted cursor fan-in resolves physical cutoff and replays",
            compiled_pipeline_builder=build_external_source_cursor_replay_compiled_pipeline,
            replay_lineage_mode=ReplayLineageMode.CURSOR,
            physical_suffix="",
            watermark_column_names=("cutoff_offset",),
            watermark_rows=((9,),),
            expected_query_fragments=(
                "max(event_cursor)",
                "FROM analytics.orders_existing",
            ),
            expected_boundary_key="_replay_cursor",
            expected_cutoff_value="9",
            expected_partition_value=None,
            expected_anchor_suffix="",
            expected_written_rows=1,
        ),
        AdoptedFanInReplayTestCase(
            description=(
                "virtual-environment adopted cursor fan-in resolves physical cutoff and replays"
            ),
            compiled_pipeline_builder=build_external_source_cursor_replay_compiled_pipeline,
            replay_lineage_mode=ReplayLineageMode.CURSOR,
            physical_suffix="__dep",
            watermark_column_names=("cutoff_offset",),
            watermark_rows=((9,),),
            expected_query_fragments=(
                "max(event_cursor)",
                "FROM analytics.orders_existing",
            ),
            expected_boundary_key="_replay_cursor",
            expected_cutoff_value="9",
            expected_partition_value=None,
            expected_anchor_suffix="__dep",
            expected_written_rows=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_adopted_fan_in_when_replaying_then_resolves_external_cutoff_for_each_mode(
    test_case: AdoptedFanInReplayTestCase,
) -> None:
    compiled_pipeline: CompiledPipeline = test_case.compiled_pipeline_builder()
    desired_state: DesiredState
    plan: PopulationPlan
    desired_state, plan = build_adopted_fan_in_population(
        compiled_pipeline=compiled_pipeline,
        replay_lineage_mode=test_case.replay_lineage_mode,
        physical_suffix=test_case.physical_suffix,
    )
    connection: AdoptedFanInConnection = AdoptedFanInConnection(
        (
            AdapterQueryResult(
                column_names=test_case.watermark_column_names,
                rows=test_case.watermark_rows,
            ),
            AdapterQueryResult(rows=((1,),)),
            AdapterQueryResult(rows=((1,),)),
        )
    )

    watermarks: tuple[PopulationWatermark, ...] = resolve_population_watermarks(
        client=connection,
        plan=plan,
        desired_state=desired_state,
        default_database="analytics",
        boundary_time="2026-07-31 12:00:00.000",
    )
    executions: tuple[PopulationReplayExecution, ...]
    completed_keys: tuple[object, ...]
    executions, completed_keys = execute_population_replay(
        client=connection,
        plan=plan,
        desired_state=desired_state,
        default_database="analytics",
        watermarks=watermarks,
        boundary_time="2026-07-31 12:00:00.000",
    )
    replay_request: AdapterReplayRequest = connection.replay_requests[0]

    assert tuple(
        fragment in connection.statements[0] for fragment in test_case.expected_query_fragments
    ) == tuple(True for _fragment in test_case.expected_query_fragments)
    assert watermarks[0].boundary_key == test_case.expected_boundary_key
    assert watermarks[0].cutoff_value == test_case.expected_cutoff_value
    assert replay_request.boundaries[0].partition_value == test_case.expected_partition_value
    assert replay_request.relations.anchor == (
        f"tbl__orders_enriched{test_case.expected_anchor_suffix}"
    )
    assert executions[0].written_rows == test_case.expected_written_rows
    assert completed_keys == (plan.roots[0].root_key,)


@pytest.mark.parametrize(
    "test_case",
    (
        WatermarkTraversalErrorTestCase(
            description="reports a cycle while resolving a replay watermark input",
            parent_name="tbl__orders_enriched",
            expected_error_fragment="upstream table traversal contains a cycle",
        ),
        WatermarkTraversalErrorTestCase(
            description="reports an unknown parent while resolving a replay watermark input",
            parent_name="missing_upstream",
            expected_error_fragment="is neither a desired table nor an adopted source",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_watermark_traversal_when_resolving_then_reports_structured_error(
    test_case: WatermarkTraversalErrorTestCase,
) -> None:
    desired_state: DesiredState
    plan: PopulationPlan
    desired_state, plan = build_adopted_fan_in_population(
        compiled_pipeline=build_external_source_offset_replay_compiled_pipeline(),
        replay_lineage_mode=ReplayLineageMode.OFFSETS,
        physical_suffix="",
    )
    alpha_table: DesiredTable = cast(DesiredTable, desired_state.objects[1])
    broken_parent_key: ObjectKey = replace(alpha_table.key, name=test_case.parent_name)
    broken_alpha_table: DesiredTable = replace(alpha_table, deps=(broken_parent_key,))
    broken_state: DesiredState = replace(
        desired_state,
        objects=(desired_state.objects[0], broken_alpha_table, *desired_state.objects[2:]),
    )
    connection: AdoptedFanInConnection = AdoptedFanInConnection(())

    with pytest.raises(PopulationExecutionError, match=test_case.expected_error_fragment):
        resolve_population_watermarks(
            client=connection,
            plan=plan,
            desired_state=broken_state,
            default_database="analytics",
            boundary_time="2026-07-31 12:00:00.000",
        )
