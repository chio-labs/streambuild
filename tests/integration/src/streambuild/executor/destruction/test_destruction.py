import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path

import pytest
from clickhouse_connect.driver.client import Client

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.exceptions import AdapterWarehouseError
from streambuild.adapter.models import (
    AdapterMutationResult,
    AdapterOwnedResourceEvent,
    AdapterOwnedResourceSnapshot,
)
from streambuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from streambuild.cli.entry._helpers.compiler_profile import (
    build_compiler_adapter_profile,
)
from streambuild.compiler.compile.models import CompilerAdapterProfile, LogicalResourceKey
from streambuild.compiler.discovery.main.load_project_input_for_path import (
    load_project_input_for_path,
)
from streambuild.compiler.discovery.models import LoadedProject
from streambuild.compiler.pipeline.main.analyze_project import analyze_project
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.executor.destruction.classes.in_memory_destruction_plan_store import (
    InMemoryDestructionPlanStore,
)
from streambuild.executor.destruction.exceptions import DestructionResourceError
from streambuild.executor.destruction.main.assemble_destruction_workflow import (
    assemble_destruction_workflow,
)
from streambuild.executor.destruction.main.execute_destruction import execute_destruction
from streambuild.executor.destruction.main.plan_destruction import plan_destruction
from streambuild.executor.destruction.models import (
    DestructionExecutionResult,
    DestructionPlan,
    DestructionRequest,
)
from streambuild.executor.workflow.exceptions import WorkflowExecutionError
from streambuild.executor.workflow.main._execute_warehouse_workflow import (
    execute_warehouse_workflow,
)
from streambuild.executor.workflow.models import WarehouseStatement
from tests.integration.src.streambuild.cli.helpers import (
    build_managed_clickhouse_client,
    run_direct_build,
    write_direct_build_project,
)
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings
from tests.integration.src.streambuild.executor.destruction._test_types import (
    CompletionEventFailureIntegrationTestCase,
    DestructionIntegrationTestCase,
    OwnershipIntegrationTestCase,
    VirtualHistoryIntegrationTestCase,
)
from tests.integration.src.streambuild.executor.destruction.helpers import realized_relation_names


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        DestructionIntegrationTestCase(
            description="destroy preserves sources and reset preserves operation evidence",
            expected_destroy_outcome="succeeded",
            expected_reset_outcome="succeeded",
            expected_terminal_invocation_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_real_target_when_destroying_and_resetting_then_scope_and_evidence_are_exact(
    test_case: DestructionIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_root: Path = tmp_path / "project"
    write_direct_build_project(project_root=project_root)
    execution_connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    observation_connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    try:
        build_exit_code: int = run_direct_build(
            project_root=project_root,
            database=clickhouse_database,
            connection=execution_connection,
        )
        assert build_exit_code == 0
        loaded_project: LoadedProject | None = load_project_input_for_path(path=project_root)
        adapter_profile: CompilerAdapterProfile = build_compiler_adapter_profile(
            ClickHouseAdapter()
        )
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=project_root / "pipelines",
            loaded_project=loaded_project,
            adapter_profile=adapter_profile,
        )
        execution_connection.execute_workflow_sql(
            f"CREATE TABLE {clickhouse_database}.stale_raw_orders "
            "(id UInt64) ENGINE = MergeTree ORDER BY id;"
        )
        stale_event: AdapterOwnedResourceEvent = AdapterOwnedResourceEvent(
            event_id="owned-stale-source",
            event_type="owned",
            target_database=clickhouse_database,
            resource_database=clickhouse_database,
            resource_name="stale_raw_orders",
            resource_kind="table",
            pipeline_name="pl__orders",
            logical_resource_type="source",
            logical_resource_name="orders",
            resource_role="source_replay_table",
        )
        for statement in execution_connection.render_owned_resource_events(
            database=clickhouse_database,
            events=(stale_event,),
        ):
            execution_connection.execute_workflow_sql(statement)
        execution_connection.execute_workflow_sql(
            f"CREATE TABLE {clickhouse_database}.tbl__orders_enriched_backup "
            "(id UInt64) ENGINE = MergeTree ORDER BY id;"
        )
        destroy_request: DestructionRequest = DestructionRequest(
            operation="destroy_pipelines",
            target="test",
            database=clickhouse_database,
            metadata_database=clickhouse_database,
            pipeline_names=("pl__orders",),
        )
        destroy_plan: DestructionPlan = plan_destruction(
            request=destroy_request,
            analysis=analysis,
            connection=execution_connection,
        )
        destroy_store: InMemoryDestructionPlanStore = InMemoryDestructionPlanStore()
        destroy_store.save(plan=destroy_plan, actor="integration")
        destroy_reviewed_at: datetime = destroy_store.mark_reviewed(
            plan_id=destroy_plan.plan_id,
            actor="integration",
        )
        destroy_result: DestructionExecutionResult = execute_destruction(
            frozen_plan=destroy_plan,
            actor_id="integration",
            actor_name="integration",
            challenge_responses=destroy_plan.challenges,
            reviewed_at=destroy_reviewed_at,
            store=destroy_store,
            connection=execution_connection,
            observation_connection=observation_connection,
            project_dir=project_root,
            replan=lambda: plan_destruction(
                request=destroy_request,
                analysis=analysis,
                connection=execution_connection,
            ),
        )
        assert destroy_result.outcome == test_case.expected_destroy_outcome

        destroy_catalog_names: frozenset[str] = execution_connection.load_catalog(
            clickhouse_database
        ).relation_names()
        source_keys: tuple[LogicalResourceKey, ...] = tuple(
            source.key for source in analysis.realized_project.project.sources
        )
        model_keys: tuple[LogicalResourceKey, ...] = tuple(
            model.key for model in analysis.realized_project.project.models
        )
        source_relation_names: frozenset[str] = realized_relation_names(
            analysis=analysis,
            logical_keys=source_keys,
        )
        model_relation_names: frozenset[str] = realized_relation_names(
            analysis=analysis,
            logical_keys=model_keys,
        )
        assert source_relation_names <= destroy_catalog_names
        assert "stale_raw_orders" in destroy_catalog_names
        assert not model_relation_names & destroy_catalog_names

        reset_request: DestructionRequest = DestructionRequest(
            operation="reset_target",
            target="test",
            database=clickhouse_database,
            metadata_database=clickhouse_database,
        )
        reset_plan: DestructionPlan = plan_destruction(
            request=reset_request,
            analysis=analysis,
            connection=execution_connection,
        )
        assert "stale_raw_orders" in {relation.name for relation in reset_plan.relations}
        assert "tbl__orders_enriched_backup" not in {
            relation.name for relation in reset_plan.relations
        }
        reset_store: InMemoryDestructionPlanStore = InMemoryDestructionPlanStore()
        reset_store.save(plan=reset_plan, actor="integration")
        reset_reviewed_at: datetime = reset_store.mark_reviewed(
            plan_id=reset_plan.plan_id,
            actor="integration",
        )
        reset_result: DestructionExecutionResult = execute_destruction(
            frozen_plan=reset_plan,
            actor_id="integration",
            actor_name="integration",
            challenge_responses=reset_plan.challenges,
            reviewed_at=reset_reviewed_at,
            store=reset_store,
            connection=execution_connection,
            observation_connection=observation_connection,
            project_dir=project_root,
            replan=lambda: plan_destruction(
                request=reset_request,
                analysis=analysis,
                connection=execution_connection,
            ),
        )
        assert reset_result.outcome == test_case.expected_reset_outcome

        remaining_names: frozenset[str] = execution_connection.load_catalog(
            clickhouse_database
        ).relation_names()
        assert not source_relation_names & remaining_names
        assert "stale_raw_orders" not in remaining_names
        assert "tbl__orders_enriched_backup" in remaining_names
        assert all(
            name.startswith("_streambuild_") or name == "tbl__orders_enriched_backup"
            for name in remaining_names
        )
        owned_after_reset: AdapterOwnedResourceSnapshot = execution_connection.load_owned_resources(
            database=clickhouse_database,
            target_database=clickhouse_database,
        )
        assert owned_after_reset.resources == ()
        invocation_count: int = int(
            clickhouse_client.query(
                f"SELECT count() FROM {clickhouse_database}._streambuild_invocations "
                "WHERE command IN ('destroy pipelines', 'reset target')"
            ).result_rows[0][0]
        )
        statement_count: int = int(
            clickhouse_client.query(
                f"SELECT count() FROM {clickhouse_database}._streambuild_run_statements "
                f"WHERE invocation_id = '{reset_result.invocation_id}'"
            ).result_rows[0][0]
        )
        assert invocation_count == test_case.expected_terminal_invocation_count
        assert statement_count == len(
            assemble_destruction_workflow(plan=reset_plan, connection=execution_connection)
        )
    finally:
        observation_connection.close()
        execution_connection.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipIntegrationTestCase(
            description="manual replacement refuses reset",
            expected_error_match="not the generation recorded",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_manually_recreated_relation_when_planning_reset_then_generation_is_refused(
    test_case: OwnershipIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_root: Path = tmp_path / "replacement-project"
    write_direct_build_project(project_root=project_root)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    try:
        assert (
            run_direct_build(
                project_root=project_root,
                database=clickhouse_database,
                connection=connection,
            )
            == 0
        )
        loaded_project: LoadedProject | None = load_project_input_for_path(path=project_root)
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=project_root / "pipelines",
            loaded_project=loaded_project,
            adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
        )
        connection.execute_workflow_sql(
            f"DROP TABLE {clickhouse_database}.tbl__orders_enriched SYNC;"
        )
        connection.execute_workflow_sql(
            f"CREATE TABLE {clickhouse_database}.tbl__orders_enriched "
            "(replacement UInt64) ENGINE = MergeTree ORDER BY replacement;"
        )

        with pytest.raises(DestructionResourceError, match=test_case.expected_error_match):
            plan_destruction(
                request=DestructionRequest(
                    operation="reset_target",
                    target="test",
                    database=clickhouse_database,
                    metadata_database=clickhouse_database,
                ),
                analysis=analysis,
                connection=connection,
            )
    finally:
        connection.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipIntegrationTestCase(
            description="partial drop records exact tombstone",
            expected_error_match="injected second drop failure",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_second_drop_failure_when_destroying_then_first_drop_has_durable_tombstone(
    test_case: OwnershipIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root: Path = tmp_path / "partial-project"
    write_direct_build_project(project_root=project_root)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    try:
        assert (
            run_direct_build(
                project_root=project_root,
                database=clickhouse_database,
                connection=connection,
            )
            == 0
        )
        loaded_project: LoadedProject | None = load_project_input_for_path(path=project_root)
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=project_root / "pipelines",
            loaded_project=loaded_project,
            adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
        )
        plan: DestructionPlan = plan_destruction(
            request=DestructionRequest(
                operation="destroy_pipelines",
                target="test",
                database=clickhouse_database,
                metadata_database=clickhouse_database,
                pipeline_names=("pl__orders",),
            ),
            analysis=analysis,
            connection=connection,
        )
        statements: tuple[WarehouseStatement, ...] = assemble_destruction_workflow(
            plan=plan,
            connection=connection,
        )
        drops: tuple[WarehouseStatement, ...] = tuple(
            filter(lambda statement: statement.sql.startswith("DROP "), statements)
        )
        original_mutation: Callable[..., AdapterMutationResult] = (
            connection.execute_workflow_mutation
        )

        def raise_injected_failure(**_: object) -> AdapterMutationResult:
            raise AdapterWarehouseError("injected second drop failure")

        mutation_by_sql: defaultdict[str, Callable[..., AdapterMutationResult]] = defaultdict(
            lambda: original_mutation
        )
        mutation_by_sql[drops[1].sql] = raise_injected_failure

        def route_mutation(*, statement: str, query_id: str | None) -> AdapterMutationResult:
            return mutation_by_sql[statement](statement=statement, query_id=query_id)

        monkeypatch.setattr(connection, "execute_workflow_mutation", route_mutation)

        with pytest.raises(WorkflowExecutionError, match=test_case.expected_error_match):
            execute_warehouse_workflow(statements=statements, connection=connection)

        first_name: str = drops[0].sql.split("`.`", maxsplit=1)[1].split("`", maxsplit=1)[0]
        second_name: str = drops[1].sql.split("`.`", maxsplit=1)[1].split("`", maxsplit=1)[0]
        active: AdapterOwnedResourceSnapshot = connection.load_owned_resources(
            database=clickhouse_database,
            target_database=clickhouse_database,
        )
        active_names: frozenset[str] = frozenset(
            resource.resource_name for resource in active.resources
        )
        assert first_name not in active_names
        assert second_name in active_names
    finally:
        connection.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        CompletionEventFailureIntegrationTestCase(
            description="first drop completion failure records an exact partial prefix",
            expected_outcome="failed",
            expected_residual_status="observed",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_drop_completion_event_failure_when_destroying_then_partial_evidence_is_exact(
    test_case: CompletionEventFailureIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root: Path = tmp_path / "completion-event-project"
    write_direct_build_project(project_root=project_root)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    observation_connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    try:
        assert (
            run_direct_build(
                project_root=project_root,
                database=clickhouse_database,
                connection=connection,
            )
            == 0
        )
        loaded_project: LoadedProject | None = load_project_input_for_path(path=project_root)
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=project_root / "pipelines",
            loaded_project=loaded_project,
            adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
        )
        request: DestructionRequest = DestructionRequest(
            operation="destroy_pipelines",
            target="test",
            database=clickhouse_database,
            metadata_database=clickhouse_database,
            pipeline_names=("pl__orders",),
        )
        plan: DestructionPlan = plan_destruction(
            request=request,
            analysis=analysis,
            connection=connection,
        )
        statements: tuple[WarehouseStatement, ...] = assemble_destruction_workflow(
            plan=plan,
            connection=connection,
        )
        drops: tuple[WarehouseStatement, ...] = tuple(
            filter(lambda statement: statement.sql.startswith("DROP "), statements)
        )
        first_drop: WarehouseStatement = drops[0]
        second_drop: WarehouseStatement = drops[1]
        first_drop_index: int = statements.index(first_drop)
        first_tombstone: WarehouseStatement = statements[first_drop_index + 1]
        assert first_tombstone.step_id.startswith("record_dropped_relation_0001_")
        original_observation_mutation: Callable[..., AdapterMutationResult] = (
            observation_connection.execute_workflow_mutation
        )

        def fail_first_drop_completion(
            *, statement: str, query_id: str | None
        ) -> AdapterMutationResult:
            action: Callable[..., AdapterMutationResult] = {
                True: raise_injected_completion_failure,
                False: original_observation_mutation,
            }["statement_completed" in statement and first_drop.step_id in statement]
            return action(statement=statement, query_id=query_id)

        def raise_injected_completion_failure(**_: object) -> AdapterMutationResult:
            raise AdapterWarehouseError("injected first drop completion event failure")

        monkeypatch.setattr(
            observation_connection,
            "execute_workflow_mutation",
            fail_first_drop_completion,
        )
        store: InMemoryDestructionPlanStore = InMemoryDestructionPlanStore()
        store.save(plan=plan, actor="integration")
        reviewed_at: datetime = store.mark_reviewed(plan_id=plan.plan_id, actor="integration")

        result: DestructionExecutionResult = execute_destruction(
            frozen_plan=plan,
            actor_id="integration",
            actor_name="integration",
            challenge_responses=plan.challenges,
            reviewed_at=reviewed_at,
            store=store,
            connection=connection,
            observation_connection=observation_connection,
            project_dir=project_root,
            replan=lambda: plan_destruction(
                request=request,
                analysis=analysis,
                connection=connection,
            ),
        )

        first_name: str = first_drop.sql.split("`.`", maxsplit=1)[1].split("`", maxsplit=1)[0]
        second_name: str = second_drop.sql.split("`.`", maxsplit=1)[1].split("`", maxsplit=1)[0]
        expected_completed: tuple[int, ...] = tuple(
            statement.sequence for statement in statements[: first_tombstone.sequence]
        )
        expected_pending: tuple[int, ...] = tuple(
            statement.sequence for statement in statements[first_tombstone.sequence :]
        )
        catalog_names: frozenset[str] = connection.load_catalog(
            clickhouse_database
        ).relation_names()
        active: AdapterOwnedResourceSnapshot = connection.load_owned_resources(
            database=clickhouse_database,
            target_database=clickhouse_database,
        )
        active_names: frozenset[str] = frozenset(
            resource.resource_name for resource in active.resources
        )
        invocation_rows: Sequence[Sequence[object]] = clickhouse_client.query(
            f"SELECT outcome, summary_json FROM {clickhouse_database}._streambuild_invocations "
            f"WHERE invocation_id = '{result.invocation_id}'"
        ).result_rows
        assert len(invocation_rows) == 1
        summary: dict[str, object] = json.loads(str(invocation_rows[0][1]))

        assert result.outcome == test_case.expected_outcome
        assert result.residual_catalog_status == test_case.expected_residual_status
        assert result.completed_statement_sequences == expected_completed
        assert result.pending_statement_sequences == expected_pending
        assert result.remaining_relation_names is not None
        assert first_name not in catalog_names
        assert second_name in catalog_names
        assert first_name not in active_names
        assert second_name in active_names
        assert invocation_rows[0][0] == test_case.expected_outcome
        assert summary["completedStatementSequences"] == list(expected_completed)
        assert summary["pendingStatementSequences"] == list(expected_pending)
        assert summary["remainingObjects"] == list(result.remaining_relation_names)
        assert summary["actor"] == {"id": "integration", "username": "integration"}
        assert summary["planId"] == plan.plan_id
        assert summary["submittedChallenges"] == list(plan.challenges)
    finally:
        observation_connection.close()
        connection.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        VirtualHistoryIntegrationTestCase(
            description="pre-ledger virtual history is reset but not pipeline destroyed",
            expected_reset_relation_names=("retired_binding", "retired_physical"),
            expected_destroy_excluded_names=("retired_binding", "retired_physical"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_preledger_virtual_history_when_planning_then_only_reset_includes_relations(
    test_case: VirtualHistoryIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_root: Path = tmp_path / "virtual-history-project"
    write_direct_build_project(project_root=project_root)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    try:
        loaded_project: LoadedProject | None = load_project_input_for_path(path=project_root)
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=project_root / "pipelines",
            loaded_project=loaded_project,
            adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
        )
        for statement in connection.render_migrate_metadata_state(clickhouse_database):
            connection.execute_workflow_sql(statement)
        connection.execute_workflow_sql(
            f"CREATE TABLE {clickhouse_database}.retired_physical "
            "(id UInt64) ENGINE = MergeTree ORDER BY id;"
        )
        connection.execute_workflow_sql(
            f"CREATE VIEW {clickhouse_database}.retired_binding AS "
            f"SELECT * FROM {clickhouse_database}.retired_physical;"
        )
        connection.execute_workflow_sql(
            f"INSERT INTO {clickhouse_database}._streambuild_virtual_deployments "
            "(deployment_id, workflow_fingerprint, replay_lineage_mode, boundary_time, "
            "created_at, tool_version) VALUES ('retired-deployment', 'retired-workflow', "
            "'offsets', now64(3, 'UTC'), now64(3, 'UTC'), 'test');"
        )
        connection.execute_workflow_sql(
            f"INSERT INTO {clickhouse_database}._streambuild_virtual_object_state "
            "(state_id, observation_id, state_kind, deployment_id, logical_database_name, "
            "logical_object_type, logical_object_name, physical_database_name, "
            "physical_relation_name, logical_model_database, logical_model_name, "
            "is_selected_root, object_fingerprint, canonical_query, observed_at) VALUES "
            "('retired-deployment', 'retired-observation', 'deployment', "
            "'retired-deployment', NULL, 'table', 'retired_binding', NULL, "
            "'retired_physical', NULL, 'retired_model', false, 'retired-fingerprint', "
            "NULL, now64(3, 'UTC'));"
        )
        connection.execute_workflow_sql(
            f"INSERT INTO {clickhouse_database}._streambuild_virtual_publications "
            "(publication_id, deployment_id, operation, previous_deployment_id, "
            "logical_database_name, logical_view_name, physical_database_name, "
            "physical_relation_name, published_at) VALUES ('retired-publication', "
            "'retired-deployment', 'promote', NULL, "
            f"'{clickhouse_database}', 'retired_binding', '{clickhouse_database}', "
            "'retired_physical', now64(3, 'UTC'));"
        )

        reset: DestructionPlan = plan_destruction(
            request=DestructionRequest(
                operation="reset_target",
                target="test",
                database=clickhouse_database,
                metadata_database=clickhouse_database,
            ),
            analysis=analysis,
            connection=connection,
        )
        destroy: DestructionPlan = plan_destruction(
            request=DestructionRequest(
                operation="destroy_pipelines",
                target="test",
                database=clickhouse_database,
                metadata_database=clickhouse_database,
                pipeline_names=("pl__orders",),
            ),
            analysis=analysis,
            connection=connection,
        )

        reset_names: frozenset[str] = frozenset(relation.name for relation in reset.relations)
        destroy_names: frozenset[str] = frozenset(relation.name for relation in destroy.relations)
        assert set(test_case.expected_reset_relation_names) <= reset_names
        assert set(test_case.expected_destroy_excluded_names).isdisjoint(destroy_names)
    finally:
        connection.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    [
        OwnershipIntegrationTestCase(
            description="pre-ledger live manifest mismatch refuses bootstrap",
            expected_error_match="does not exactly match",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_preledger_manifest_mismatch_when_planning_then_bootstrap_is_refused(
    test_case: OwnershipIntegrationTestCase,
    clickhouse_connection_settings: ClickHouseConnectionSettings,
    clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_root: Path = tmp_path / "bootstrap-refusal-project"
    write_direct_build_project(project_root=project_root)
    connection: AdapterConnection = build_managed_clickhouse_client(
        clickhouse_connection_settings,
        database=clickhouse_database,
    )
    try:
        loaded_project: LoadedProject | None = load_project_input_for_path(path=project_root)
        analysis: CompileAnalysis = analyze_project(
            pipelines_root=project_root / "pipelines",
            loaded_project=loaded_project,
            adapter_profile=build_compiler_adapter_profile(ClickHouseAdapter()),
        )
        for statement in connection.render_migrate_metadata_state(clickhouse_database):
            connection.execute_workflow_sql(statement)
        connection.execute_workflow_sql(
            f"CREATE TABLE {clickhouse_database}.tbl__orders_enriched "
            "(replacement UInt64) ENGINE = MergeTree ORDER BY replacement;"
        )

        with pytest.raises(DestructionResourceError, match=test_case.expected_error_match):
            plan_destruction(
                request=DestructionRequest(
                    operation="destroy_pipelines",
                    target="test",
                    database=clickhouse_database,
                    metadata_database=clickhouse_database,
                    pipeline_names=("pl__orders",),
                ),
                analysis=analysis,
                connection=connection,
            )
    finally:
        connection.close()


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
