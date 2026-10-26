import json
from pathlib import Path

import pytest

from streambuild.cli.plan.main._render_direct_plan_json import render_direct_plan_json
from streambuild.cli.plan.main.render_direct_plan_text import render_direct_plan_text
from streambuild.compiler.planner.models import DirectWarehouseSnapshot
from streambuild.executor.direct.exceptions import DirectBuildError, DirectWorkflowExecutionError
from streambuild.executor.direct.main.assemble_direct_build_workflow import (
    assemble_direct_build_workflow,
)
from streambuild.executor.direct.main.execute_direct_build_workflow import (
    execute_direct_build_workflow,
)
from streambuild.executor.direct.main.plan_preserved_managed_sources import (
    plan_preserved_managed_sources,
)
from streambuild.executor.direct.models import DirectBuildRequest, DirectBuildWorkflow
from streambuild.executor.kafka_admin.main.reset_fresh_landing_offsets import (
    reset_fresh_landing_offsets,
)
from streambuild.executor.kafka_admin.models import ConsumerGroupOffsetReset
from streambuild.executor.population.models import (
    PopulationRealization,
    PopulationSourcePreparation,
    PopulationSourceRecreation,
)
from streambuild.executor.workflow.models import BuildWorkflow, WarehouseStatement
from streambuild.executor.workflow.types import StatementIntent, WorkflowMode, WorkflowPhase
from tests.unit.src.streambuild.executor.direct.main._test_types import (
    DirectSourceDriftBlockTestCase,
    DirectSourcePreservationTestCase,
    DirectSourceRecoveryTestCase,
    DirectSourceRecreationTestCase,
)
from tests.unit.src.streambuild.executor.direct.main.helpers import (
    FailingPausedSourceConnection,
    RecordingDirectBuildConnection,
    build_managed_source_execution_request,
    build_managed_source_snapshot,
)
from tests.unit.src.streambuild.executor.kafka_admin.helpers import RecordingClientFactory

_FRESH_SOURCE_STEP_IDS: tuple[str, ...] = (
    "prepare_source_kafka__orders",
    "prepare_source_raw__orders",
    "bootstrap_source_mv__orders",
)
_RECREATION_STEP_IDS: tuple[str, ...] = (
    "pause_source_mv__orders",
    "drop_source_kafka__orders",
    "recreate_source_kafka__orders",
    "activate_source_mv__orders",
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceRecreationTestCase(
            description="declared consumer setting absent from the deployed source",
            declared_settings=(("kafka_max_block_size", "500"),),
            catalog_setting_overrides=(),
            omitted_catalog_settings=("kafka_max_block_size",),
            expected_drifted_settings=("kafka_max_block_size",),
            expected_source_step_ids=_RECREATION_STEP_IDS,
            expected_recovery_step_ids=(
                "recover_source_kafka__orders",
                "recover_source_mv__orders",
            ),
            expected_recreate_sql_fragments=(
                "CREATE TABLE analytics.kafka__orders",
                "kafka_topic_list = 'source.orders'",
                "kafka_group_name = 'streambuild_direct_scope_test_orders_analytics'",
                "kafka_max_block_size = '500'",
            ),
        ),
        DirectSourceRecreationTestCase(
            description="topic changed in the project",
            declared_settings=(),
            catalog_setting_overrides=(("kafka_topic_list", "source.orders.previous"),),
            omitted_catalog_settings=(),
            expected_drifted_settings=("kafka_topic_list",),
            expected_source_step_ids=_RECREATION_STEP_IDS,
            expected_recovery_step_ids=(
                "recover_source_kafka__orders",
                "recover_source_mv__orders",
            ),
            expected_recreate_sql_fragments=(
                "kafka_topic_list = 'source.orders'",
                "kafka_group_name = 'streambuild_direct_scope_test_orders_analytics'",
            ),
        ),
        DirectSourceRecreationTestCase(
            description="out-of-band broker and consumer setting changes",
            declared_settings=(("kafka_num_consumers", "2"),),
            catalog_setting_overrides=(
                ("kafka_broker_list", "kafka-old:9092"),
                ("kafka_num_consumers", "4"),
            ),
            omitted_catalog_settings=(),
            expected_drifted_settings=("kafka_broker_list", "kafka_num_consumers"),
            expected_source_step_ids=_RECREATION_STEP_IDS,
            expected_recovery_step_ids=(
                "recover_source_kafka__orders",
                "recover_source_mv__orders",
            ),
            expected_recreate_sql_fragments=(
                "kafka_broker_list = 'kafka:9092'",
                "kafka_num_consumers = '2'",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_settings_only_source_drift_when_planning_then_source_is_recreated_and_landing_kept(
    test_case: DirectSourceRecreationTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_managed_source_execution_request(
        project_root=tmp_path,
        declared_settings=test_case.declared_settings,
    )
    snapshot: DirectWarehouseSnapshot = build_managed_source_snapshot(
        request=request,
        catalog_setting_overrides=test_case.catalog_setting_overrides,
        omitted_catalog_settings=test_case.omitted_catalog_settings,
    )

    preparation: PopulationSourcePreparation
    realizations: tuple[PopulationRealization, ...]
    preparation, realizations = plan_preserved_managed_sources(
        plan=request.plan,
        realized_project=request.realized_project,
        catalog=snapshot.catalog,
        database=request.database,
    )
    workflow: DirectBuildWorkflow = assemble_direct_build_workflow(
        request=request,
        client=RecordingDirectBuildConnection(),
        snapshot=snapshot,
        plan_json=render_direct_plan_json(plan=request.plan, adapter_name="clickhouse"),
    )
    client_factory: RecordingClientFactory = RecordingClientFactory()
    resets: tuple[ConsumerGroupOffsetReset, ...] = reset_fresh_landing_offsets(
        source_preparation=preparation,
        client_factory=client_factory,
    )

    plan_text: str = render_direct_plan_text(
        plan=request.plan,
        adapter_name="clickhouse",
        source_recreations=workflow.recreated_sources,
    )
    plan_payload: dict = json.loads(
        render_direct_plan_json(
            plan=request.plan,
            adapter_name="clickhouse",
            source_recreations=workflow.recreated_sources,
        )
    )

    recreation: PopulationSourceRecreation = preparation.recreated_sources[0]
    step_ids: tuple[str, ...] = tuple(statement.step_id for statement in workflow.statements)
    sql_by_step_id: dict[str, str] = {
        statement.step_id: statement.sql for statement in workflow.statements
    }
    recreate_sql: str = sql_by_step_id["recreate_source_kafka__orders"]
    source_step_positions: tuple[int, ...] = tuple(
        step_ids.index(step_id) for step_id in test_case.expected_source_step_ids
    )
    assert len(preparation.recreated_sources) == 1
    assert recreation.managed_source.resource.name == "kafka__orders"
    assert recreation.landing_view_name == "mv__orders"
    assert recreation.landing_relation_name == "raw__orders"
    assert recreation.consumer_group == "streambuild_direct_scope_test_orders_analytics"
    assert recreation.drifted_setting_names == test_case.expected_drifted_settings
    assert preparation.preserved_relation_names == ("raw__orders", "mv__orders")
    assert preparation.created_relation_names == ()
    assert realizations == ()
    assert resets == ()
    assert client_factory.clients == []
    assert source_step_positions == tuple(sorted(source_step_positions))
    assert set(step_ids).isdisjoint(_FRESH_SOURCE_STEP_IDS)
    assert step_ids.index("recreate_source_kafka__orders") < step_ids.index("replay_alpha")
    assert all(fragment in recreate_sql for fragment in test_case.expected_recreate_sql_fragments)
    assert "IF NOT EXISTS" not in recreate_sql
    assert tuple(statement.step_id for statement in workflow.source_recovery_statements) == (
        test_case.expected_recovery_step_ids
    )
    assert workflow.recreated_sources == preparation.recreated_sources
    assert (
        "kafka__orders and mv__orders are recreated with the declared settings "
        f"({', '.join(test_case.expected_drifted_settings)}); raw__orders and its rows are kept"
    ) in plan_text
    assert plan_payload["source_recreations"][0]["drifted_settings"] == list(
        test_case.expected_drifted_settings
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourcePreservationTestCase(
            description="matching source is preserved untouched",
            declared_settings=(("kafka_max_block_size", "500"),),
            catalog_setting_overrides=(),
            expected_preserved_relation_names=("kafka__orders", "raw__orders", "mv__orders"),
        ),
        DirectSourcePreservationTestCase(
            description="secret setting masked by the catalog is not treated as drift",
            declared_settings=(("kafka_sasl_password", "example-secret"),),
            catalog_setting_overrides=(("kafka_sasl_password", "[HIDDEN]"),),
            expected_preserved_relation_names=("kafka__orders", "raw__orders", "mv__orders"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_undrifted_source_when_planning_then_source_is_preserved(
    test_case: DirectSourcePreservationTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_managed_source_execution_request(
        project_root=tmp_path,
        declared_settings=test_case.declared_settings,
    )
    snapshot: DirectWarehouseSnapshot = build_managed_source_snapshot(
        request=request,
        catalog_setting_overrides=test_case.catalog_setting_overrides,
    )

    preparation: PopulationSourcePreparation
    preparation, _realizations = plan_preserved_managed_sources(
        plan=request.plan,
        realized_project=request.realized_project,
        catalog=snapshot.catalog,
        database=request.database,
    )

    assert preparation.recreated_sources == ()
    assert preparation.preserved_relation_names == test_case.expected_preserved_relation_names


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceDriftBlockTestCase(
            description="landing column drift blocks",
            catalog_setting_overrides=(),
            extra_landing_columns=(("customer_id", "String"),),
            expected_error_fragments=("raw__orders landing columns no longer match",),
            unexpected_error_fragments=("kafka__orders setting",),
        ),
        DirectSourceDriftBlockTestCase(
            description="landing column drift blocks alongside source settings drift",
            catalog_setting_overrides=(("kafka_topic_list", "source.orders.previous"),),
            extra_landing_columns=(("customer_id", "String"),),
            expected_error_fragments=("raw__orders landing columns no longer match",),
            unexpected_error_fragments=("kafka__orders setting",),
        ),
        DirectSourceDriftBlockTestCase(
            description="settings drift under a different consumer group blocks",
            catalog_setting_overrides=(
                ("kafka_topic_list", "source.orders.previous"),
                ("kafka_group_name", "streambuild_orders"),
            ),
            extra_landing_columns=(),
            expected_error_fragments=(
                "kafka__orders consumes as consumer group 'streambuild_orders' but the project "
                "declares 'streambuild_direct_scope_test_orders_analytics'",
            ),
            unexpected_error_fragments=("landing columns",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unrecoverable_source_drift_when_planning_then_build_is_blocked(
    test_case: DirectSourceDriftBlockTestCase,
    tmp_path: Path,
) -> None:
    request: DirectBuildRequest = build_managed_source_execution_request(
        project_root=tmp_path,
        declared_settings=(),
    )
    snapshot: DirectWarehouseSnapshot = build_managed_source_snapshot(
        request=request,
        catalog_setting_overrides=test_case.catalog_setting_overrides,
        extra_landing_columns=test_case.extra_landing_columns,
    )

    with pytest.raises(DirectBuildError) as raised:
        plan_preserved_managed_sources(
            plan=request.plan,
            realized_project=request.realized_project,
            catalog=snapshot.catalog,
            database=request.database,
        )

    message: str = str(raised.value)
    assert all(fragment in message for fragment in test_case.expected_error_fragments)
    assert not any(fragment in message for fragment in test_case.unexpected_error_fragments)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSourceRecoveryTestCase(
            description="dropped managed source is restored when its recreation fails",
            expected_failed_step_id="recreate_source_kafka__orders",
            expected_attempted_mutations=(
                "DROP TABLE IF EXISTS analytics.kafka__orders SYNC;",
                "SELECT invalid;",
                "CREATE TABLE IF NOT EXISTS analytics.kafka__orders (message String);",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failed_source_recreation_when_executing_then_source_is_recovered(
    test_case: DirectSourceRecoveryTestCase,
) -> None:
    workflow: DirectBuildWorkflow = DirectBuildWorkflow(
        template=BuildWorkflow(
            mode=WorkflowMode.DIRECT,
            plan_json="{}",
            statements=(
                WarehouseStatement(
                    sequence=1,
                    step_id="drop_source_kafka__orders",
                    phase=WorkflowPhase.PREPARATION,
                    intent=StatementIntent.MUTATION,
                    sql="DROP TABLE IF EXISTS analytics.kafka__orders SYNC;",
                ),
                WarehouseStatement(
                    sequence=2,
                    step_id="recreate_source_kafka__orders",
                    phase=WorkflowPhase.PREPARATION,
                    intent=StatementIntent.MUTATION,
                    sql="SELECT invalid;",
                ),
            ),
        ),
        runtime_replays=(),
        workflow_id="workflow-1",
        source_recovery_statements=(
            WarehouseStatement(
                sequence=1,
                step_id="recover_source_kafka__orders",
                phase=WorkflowPhase.FINALIZATION,
                intent=StatementIntent.MUTATION,
                sql="CREATE TABLE IF NOT EXISTS analytics.kafka__orders (message String);",
            ),
        ),
    )
    connection: FailingPausedSourceConnection = FailingPausedSourceConnection()

    with pytest.raises(DirectWorkflowExecutionError) as raised:
        execute_direct_build_workflow(workflow=workflow, connection=connection)

    assert tuple(connection.attempted_mutations) == test_case.expected_attempted_mutations
    assert raised.value.failed_step_id == test_case.expected_failed_step_id
