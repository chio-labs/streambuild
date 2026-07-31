"""Execute the one physical population path used by every mode."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.compile.models import ObjectKey
from streambuild.executor.population._helpers.persistence import persist_population_watermarks
from streambuild.executor.population._helpers.relations import realize_population_objects
from streambuild.executor.population._helpers.replay import execute_population_replay
from streambuild.executor.population._helpers.roots import expand_fan_in_roots
from streambuild.executor.population._helpers.sources import (
    activate_population_sources,
)
from streambuild.executor.population._helpers.timing import wait_for_population_stabilization
from streambuild.executor.population._helpers.watermarks import resolve_population_watermarks
from streambuild.executor.population.models import (
    PopulationPlan,
    PopulationReplayExecution,
    PopulationRequest,
    PopulationResult,
    PopulationWatermark,
)


def execute_population(
    *, request: PopulationRequest, client: AdapterConnection
) -> PopulationResult:
    """Realize, stabilize, watermark, and replay one physical graph."""

    plan: PopulationPlan = expand_fan_in_roots(
        plan=request.plan, desired_state=request.desired_state
    )
    created_relation_names: tuple[str, ...] = realize_population_objects(
        client=client,
        plan=plan,
        desired_state=request.desired_state,
        default_database=request.default_database,
    )
    activate_population_sources(
        client=client,
        preparation=request.source_preparation,
        default_database=request.default_database,
    )
    wait_for_population_stabilization(request.stabilization_seconds)
    boundary_time: str = (
        request.boundary_time
        if request.boundary_time is not None
        else client.capture_warehouse_timestamp()
    )
    watermarks: tuple[PopulationWatermark, ...] = resolve_population_watermarks(
        client=client,
        plan=plan,
        desired_state=request.desired_state,
        default_database=request.default_database,
        boundary_time=boundary_time,
    )
    if request.watermark_metadata_database is not None:
        persist_population_watermarks(
            client=client,
            metadata_database=request.watermark_metadata_database,
            plan=plan,
            watermarks=watermarks,
        )
    replay_executions: tuple[PopulationReplayExecution, ...]
    completed_root_keys: tuple[ObjectKey, ...]
    replay_executions, completed_root_keys = execute_population_replay(
        client=client,
        plan=plan,
        desired_state=request.desired_state,
        default_database=request.default_database,
        watermarks=watermarks,
        boundary_time=boundary_time,
    )
    return PopulationResult(
        boundary_time=boundary_time,
        created_relation_names=created_relation_names,
        preserved_source_relation_names=request.source_preparation.preserved_relation_names,
        created_source_relation_names=request.source_preparation.created_relation_names,
        watermarks=watermarks,
        replay_executions=replay_executions,
        completed_root_keys=completed_root_keys,
    )
