"""Backfill execution entrypoint."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.executor.backfill._helpers.bootstrap import execute_backfill_bootstrap
from streambuild.executor.backfill.models import (
    BackfillBootstrapRequest,
    BackfillBootstrapResult,
    BackfillExecutionResult,
    BackfillRootReplayResult,
)
from streambuild.executor.population.main._execute_population import execute_population
from streambuild.executor.population.main._prepare_population_sources import (
    prepare_population_sources,
)
from streambuild.executor.population.models import (
    PopulationObject,
    PopulationPlan,
    PopulationRequest,
    PopulationResult,
    PopulationRoot,
    PopulationSourcePreparation,
)


def execute_backfill(
    *,
    request: BackfillBootstrapRequest,
    client: AdapterConnection,
) -> BackfillExecutionResult:
    """Execute staged backfill through boundary capture and supported replay steps."""

    bootstrap_result: BackfillBootstrapResult = execute_backfill_bootstrap(
        request=request, client=client
    )
    source_preparation: PopulationSourcePreparation = prepare_population_sources(
        client=client,
        desired_state=request.desired_state,
        default_database=request.default_database,
        existing_relation_names=bootstrap_result.existing_relation_names,
    )
    population: PopulationResult = execute_population(
        request=PopulationRequest(
            plan=_population_plan(
                deployment_plan=bootstrap_result.deployment_plan,
                execution_id=bootstrap_result.deployment_id,
                replay_lineage_mode=request.replay_lineage_mode,
            ),
            desired_state=request.desired_state,
            default_database=request.default_database,
            source_preparation=source_preparation,
            stabilization_seconds=request.stabilization_seconds,
            boundary_time=request.boundary_time,
            watermark_metadata_database=request.metadata_database,
        ),
        client=client,
    )
    return BackfillExecutionResult(
        bootstrap=bootstrap_result,
        boundary_time=population.boundary_time,
        replay_results=tuple(
            BackfillRootReplayResult(
                root_key=execution.root_key,
                written_rows=execution.written_rows,
            )
            for execution in population.replay_executions
        ),
    )


def _population_plan(
    *, deployment_plan: DeploymentPlan, execution_id: str, replay_lineage_mode: str
) -> PopulationPlan:
    return PopulationPlan(
        execution_id=execution_id,
        roots=tuple(
            PopulationRoot(
                root_key=subtree.root_key,
                affected_keys=subtree.affected_keys,
                upstream_boundary_key=subtree.upstream_boundary_key,
                replay_lineage_mode=replay_lineage_mode,
                execution_mode=subtree.execution_mode,
                forced_start_time=subtree.forced_start_time,
                execution_lookback_seconds=subtree.execution_lookback_seconds,
            )
            for subtree in deployment_plan.rebuild_subtrees
            if subtree.replay_required
        ),
        objects=tuple(
            PopulationObject(
                logical_key=prepared.logical_key,
                physical_name=prepared.physical_name,
            )
            for prepared in deployment_plan.prepared_shadow_objects
        ),
    )
