import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest
from clickhouse_connect.driver.client import Client
from kafka import KafkaProducer

from streambuild.clickhouse.render._helpers.create_kafka_table import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render._helpers.create_materialized_view import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render._helpers.create_table import render_create_table_ddl
from streambuild.compiler.compile.models import CompiledPipeline
from streambuild.compiler.planner.types import RebuildExecutionMode
from streambuild.executor.audit_backfill.types import AuditAssessment
from streambuild.executor.backfill.main import execute_backfill
from streambuild.executor.backfill.models import BackfillExecutionResult
from streambuild.executor.publish.main import execute_publish
from streambuild.executor.publish.models import PublishRequest
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from streambuild.spec.models.types import SchemaChangeBackfillMode
from tests.e2e.src.streambuild.conftest import (
    E2EClickHouseConnectionSettings,
    E2EKafkaConnectionSettings,
)
from tests.e2e.src.streambuild.executor._test_types import (
    GreenfieldKafkaWorkflowE2ETestCase,
    KafkaLiveShadowWorkflowE2ETestCase,
    KafkaOffsetAuditWorkflowE2ETestCase,
    KafkaRecoveryWorkflowE2ETestCase,
    KafkaSchemaChangeWorkflowE2ETestCase,
)
from tests.e2e.src.streambuild.executor.helpers import (
    E2E_KAFKA_OFFSET_PROJECT_DIR,
    E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
    build_authored_greenfield_workflow_compiled_pipeline,
    build_future_replay_times,
    build_greenfield_workflow_request,
    build_kafka_producer,
    build_near_replay_times,
    build_schema_change_workflow_compiled_pipeline,
    prepare_authored_e2e_project,
    produce_kafka_messages,
    require_managed_source,
    run_streambuild_audit_backfill_cli,
    run_streambuild_backfill_cli,
    run_streambuild_doctor_cli,
    run_streambuild_publish_cli,
    run_streambuild_repair_active_view_cli,
    wait_for_row_count,
    wait_for_table_exists,
    wait_for_table_missing,
    with_schema_change_backfill_policy,
)
from tests.e2e.src.streambuild.executor.scenario import (
    KafkaLiveShadowScenarioResult,
    run_kafka_live_shadow_scenario,
)

GREENFIELD_CREATED_AT: str
GREENFIELD_BOUNDARY_TIME: str
GREENFIELD_CREATED_AT, GREENFIELD_BOUNDARY_TIME = build_future_replay_times(seconds_from_now=0)

RECOVERY_CREATED_AT: str
RECOVERY_BOUNDARY_TIME: str
RECOVERY_CREATED_AT, RECOVERY_BOUNDARY_TIME = build_future_replay_times(seconds_from_now=10)

OFFSET_AUDIT_CREATED_AT: str
OFFSET_AUDIT_BOUNDARY_TIME: str
OFFSET_AUDIT_CREATED_AT, OFFSET_AUDIT_BOUNDARY_TIME = build_future_replay_times(seconds_from_now=40)


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        GreenfieldKafkaWorkflowE2ETestCase(
            description="runs the greenfield Kafka workflow from landing ingest through publish",
            deployment_id="20260410T000000Z_ab12cd",
            created_at=GREENFIELD_CREATED_AT,
            boundary_time=GREENFIELD_BOUNDARY_TIME,
            expected_order_ids=("order-1", "order-2"),
            expected_audit_assessment=AuditAssessment.READY,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_kafka_backed_greenfield_pipeline_when_running_then_it_publishes_expected_rows(
    test_case: GreenfieldKafkaWorkflowE2ETestCase,
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_authored_e2e_project(
        fixture_project_dir=E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
        tmp_path=tmp_path,
        kafka_broker_list=e2e_kafka_connection_settings.internal_bootstrap_server,
        topic_suffix=e2e_clickhouse_database,
    )
    compiled_pipeline: CompiledPipeline = build_authored_greenfield_workflow_compiled_pipeline(
        project_dir=project_dir
    )
    target_table_name: str = compiled_pipeline.transforms[0].target_table_name
    e2e_clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=e2e_clickhouse_database,
        )
    )

    producer: KafkaProducer = build_kafka_producer(
        bootstrap_server=e2e_kafka_connection_settings.bootstrap_server
    )
    try:
        produce_kafka_messages(
            producer=producer,
            topic=require_managed_source(compiled_pipeline).kafka_table.spec.kafka.topic,
            messages=tuple(
                (order_id, json.dumps({"order_id": order_id}))
                for order_id in test_case.expected_order_ids
            ),
        )
    finally:
        producer.close()

    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=require_managed_source(compiled_pipeline).raw_table.name,
        expected_count=len(test_case.expected_order_ids),
    )

    run_streambuild_backfill_cli(
        project_dir=project_dir,
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )
    audit_result: dict[str, object] = run_streambuild_audit_backfill_cli(
        project_dir=project_dir,
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )
    run_streambuild_publish_cli(
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )

    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=f"{target_table_name}__{test_case.deployment_id}",
        expected_count=len(test_case.expected_order_ids),
    )
    published_rows: Sequence[Sequence[object]] = e2e_clickhouse_client.query(
        f"SELECT order_id FROM {e2e_clickhouse_database}.{target_table_name} ORDER BY order_id"
    ).result_rows

    assert audit_result["assessment"] == test_case.expected_audit_assessment
    assert tuple(row[0] for row in published_rows) == test_case.expected_order_ids


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        KafkaRecoveryWorkflowE2ETestCase(
            description="repairs a deleted stable view after publishing a Kafka-backed deployment",
            deployment_id="20260410T001000Z_ab12cd",
            created_at=RECOVERY_CREATED_AT,
            boundary_time=RECOVERY_BOUNDARY_TIME,
            expected_order_ids=("order-1", "order-2"),
            expected_doctor_state_kind="logical_view_missing",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_kafka_backed_published_deployment_when_view_is_deleted_then_repair_restores_it(
    test_case: KafkaRecoveryWorkflowE2ETestCase,
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_authored_e2e_project(
        fixture_project_dir=E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
        tmp_path=tmp_path,
        kafka_broker_list=e2e_kafka_connection_settings.internal_bootstrap_server,
        topic_suffix=e2e_clickhouse_database,
    )
    compiled_pipeline: CompiledPipeline = build_authored_greenfield_workflow_compiled_pipeline(
        project_dir=project_dir
    )
    target_table_name: str = compiled_pipeline.transforms[0].target_table_name
    e2e_clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=e2e_clickhouse_database,
        )
    )

    producer: KafkaProducer = build_kafka_producer(
        bootstrap_server=e2e_kafka_connection_settings.bootstrap_server
    )
    try:
        produce_kafka_messages(
            producer=producer,
            topic=require_managed_source(compiled_pipeline).kafka_table.spec.kafka.topic,
            messages=tuple(
                (order_id, json.dumps({"order_id": order_id}))
                for order_id in test_case.expected_order_ids
            ),
        )
    finally:
        producer.close()

    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=require_managed_source(compiled_pipeline).raw_table.name,
        expected_count=len(test_case.expected_order_ids),
    )

    run_streambuild_backfill_cli(
        project_dir=project_dir,
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )
    run_streambuild_publish_cli(
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )
    e2e_clickhouse_client.command(f"DROP VIEW {e2e_clickhouse_database}.{target_table_name}")
    wait_for_table_missing(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=target_table_name,
    )
    doctor_result: dict[str, object] = run_streambuild_doctor_cli(
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
    )
    repair_result: dict[str, object] = run_streambuild_repair_active_view_cli(
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        table_name=target_table_name,
        deployment_id=test_case.deployment_id,
    )

    wait_for_table_exists(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=target_table_name,
    )
    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=f"{target_table_name}__{test_case.deployment_id}",
        expected_count=len(test_case.expected_order_ids),
    )
    repaired_rows: Sequence[Sequence[object]] = e2e_clickhouse_client.query(
        f"SELECT order_id FROM {e2e_clickhouse_database}.{target_table_name} ORDER BY order_id"
    ).result_rows

    active_views: list[dict[str, object]] = cast(
        list[dict[str, object]], doctor_result["active_views"]
    )
    candidate_deployment_ids: tuple[str, ...] = tuple(
        cast(list[str], active_views[0]["candidate_deployment_ids"])
    )
    assert active_views[0]["state_kind"] == test_case.expected_doctor_state_kind
    assert candidate_deployment_ids == (test_case.deployment_id,)
    assert repair_result["target_table_name"] == f"{target_table_name}__{test_case.deployment_id}"
    assert tuple(row[0] for row in repaired_rows) == test_case.expected_order_ids


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        KafkaLiveShadowWorkflowE2ETestCase(
            description="keeps the staged shadow path live while a staged deployment is open",
            deployment_id="20260410T002000Z_ab12cd",
            initial_order_ids=("order-1", "order-2"),
            live_order_ids=("order-3", "order-4", "order-5"),
            expected_final_order_ids=("order-1", "order-2", "order-3", "order-4", "order-5"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_open_staged_kafka_deployment_when_new_rows_arrive_then_shadow_path_stays_live(
    test_case: KafkaLiveShadowWorkflowE2ETestCase,
    isolated_e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    isolated_e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
    isolated_e2e_clickhouse_client: Client,
    isolated_e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    scenario_result: KafkaLiveShadowScenarioResult = run_kafka_live_shadow_scenario(
        test_case=test_case,
        clickhouse_connection_settings=isolated_e2e_clickhouse_connection_settings,
        kafka_connection_settings=isolated_e2e_kafka_connection_settings,
        clickhouse_client=isolated_e2e_clickhouse_client,
        clickhouse_database=isolated_e2e_clickhouse_database,
        tmp_path=tmp_path,
    )

    assert scenario_result.deployment_id == test_case.deployment_id
    assert scenario_result.staged_order_ids == test_case.expected_final_order_ids
    assert tuple(row[0] for row in scenario_result.final_rows) == test_case.expected_final_order_ids


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        KafkaOffsetAuditWorkflowE2ETestCase(
            description="audits offset-mode staged deployment under live Kafka ingestion",
            deployment_id="20260410T004000Z_ef56gh",
            created_at=OFFSET_AUDIT_CREATED_AT,
            boundary_time=OFFSET_AUDIT_BOUNDARY_TIME,
            initial_order_ids=("order-1", "order-2"),
            live_order_ids=("order-3",),
            expected_audit_assessment=AuditAssessment.READY,
            expected_partitions_compared=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_offset_mode_staged_kafka_deployment_when_new_rows_arrive_then_audit_reports_catchup(
    test_case: KafkaOffsetAuditWorkflowE2ETestCase,
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_authored_e2e_project(
        fixture_project_dir=E2E_KAFKA_OFFSET_PROJECT_DIR,
        tmp_path=tmp_path,
        kafka_broker_list=e2e_kafka_connection_settings.internal_bootstrap_server,
        topic_suffix=e2e_clickhouse_database,
    )
    compiled_pipeline: CompiledPipeline = build_authored_greenfield_workflow_compiled_pipeline(
        project_dir=project_dir
    )
    e2e_clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=e2e_clickhouse_database,
        )
    )

    producer: KafkaProducer = build_kafka_producer(
        bootstrap_server=e2e_kafka_connection_settings.bootstrap_server
    )
    try:
        produce_kafka_messages(
            producer=producer,
            topic=require_managed_source(compiled_pipeline).kafka_table.spec.kafka.topic,
            messages=tuple(
                (order_id, json.dumps({"order_id": order_id}))
                for order_id in test_case.initial_order_ids
            ),
        )
    finally:
        producer.close()

    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=require_managed_source(compiled_pipeline).raw_table.name,
        expected_count=len(test_case.initial_order_ids),
    )

    run_streambuild_backfill_cli(
        project_dir=project_dir,
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )

    producer = build_kafka_producer(bootstrap_server=e2e_kafka_connection_settings.bootstrap_server)
    try:
        produce_kafka_messages(
            producer=producer,
            topic=require_managed_source(compiled_pipeline).kafka_table.spec.kafka.topic,
            messages=tuple(
                (order_id, json.dumps({"order_id": order_id}))
                for order_id in test_case.live_order_ids
            ),
        )
    finally:
        producer.close()

    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=require_managed_source(compiled_pipeline).raw_table.name,
        expected_count=len(test_case.initial_order_ids) + len(test_case.live_order_ids),
    )

    audit_result: dict[str, object] = run_streambuild_audit_backfill_cli(
        project_dir=project_dir,
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        deployment_id=test_case.deployment_id,
    )
    root_results: list[dict[str, object]] = cast(
        list[dict[str, object]], audit_result["root_results"]
    )
    root_result: dict[str, object] = root_results[0]
    offset_summary: dict[str, object] | None = cast(
        dict[str, object] | None, root_result["offset_catchup_summary"]
    )

    assert audit_result["assessment"] == test_case.expected_audit_assessment
    assert offset_summary is not None
    assert offset_summary["partitions_compared"] == test_case.expected_partitions_compared


@pytest.mark.e2e
@pytest.mark.parametrize(
    "test_case",
    [
        KafkaSchemaChangeWorkflowE2ETestCase(
            description="bounded non-breaking schema change seeds the prefix and replays the tail",
            initial_pipeline_kind="base",
            changed_pipeline_kind="add_column",
            initial_deployment_id="20260410T005000Z_ab12cd",
            changed_deployment_id="20260410T005500Z_cd34ef",
            lookback_seconds=8,
            expected_execution_mode=RebuildExecutionMode.SEEDED_BOUNDED_REBUILD,
            expected_view_column_names=(
                "order_id",
                "_replay_timestamp",
                "kafka_topic",
            ),
            expected_selected_columns=("order_id", "kafka_topic"),
            expected_selected_rows=(
                ("frontier-order", "source.orders.created"),
                ("historical-order", ""),
            ),
        ),
        KafkaSchemaChangeWorkflowE2ETestCase(
            description=(
                "bounded breaking remove-column change seeds the prefix and drops the removed "
                "column"
            ),
            initial_pipeline_kind="add_column",
            changed_pipeline_kind="remove_column",
            initial_deployment_id="20260410T006000Z_ab12cd",
            changed_deployment_id="20260410T006500Z_cd34ef",
            lookback_seconds=8,
            expected_execution_mode=RebuildExecutionMode.SEEDED_BOUNDED_REBUILD,
            expected_view_column_names=("order_id",),
            expected_selected_columns=("order_id",),
            expected_selected_rows=(
                ("frontier-order",),
                ("historical-order",),
            ),
        ),
        KafkaSchemaChangeWorkflowE2ETestCase(
            description="bounded breaking type change replays only the tail without seeding",
            initial_pipeline_kind="add_column",
            changed_pipeline_kind="type_change",
            initial_deployment_id="20260410T007000Z_ab12cd",
            changed_deployment_id="20260410T007500Z_cd34ef",
            lookback_seconds=8,
            expected_execution_mode=RebuildExecutionMode.UNSEEDED_BOUNDED_REBUILD,
            expected_view_column_names=(
                "order_id",
                "_replay_timestamp",
                "kafka_topic",
            ),
            expected_selected_columns=("order_id",),
            expected_selected_rows=(("frontier-order",),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_published_kafka_pipeline_when_schema_changes_then_bounded_policy_behaves_as_expected(
    test_case: KafkaSchemaChangeWorkflowE2ETestCase,
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
    e2e_clickhouse_client: Client,
    e2e_clickhouse_database: str,
) -> None:
    initial_compiled_pipeline: CompiledPipeline = build_schema_change_workflow_compiled_pipeline(
        kafka_broker_list=e2e_kafka_connection_settings.internal_bootstrap_server,
        pipeline_kind=test_case.initial_pipeline_kind,
        topic_suffix=e2e_clickhouse_database,
    )
    changed_compiled_pipeline: CompiledPipeline = with_schema_change_backfill_policy(
        compiled_pipeline=build_schema_change_workflow_compiled_pipeline(
            kafka_broker_list=e2e_kafka_connection_settings.internal_bootstrap_server,
            pipeline_kind=test_case.changed_pipeline_kind,
            topic_suffix=e2e_clickhouse_database,
        ),
        breaking_mode=SchemaChangeBackfillMode.BOUNDED,
        breaking_lookback_seconds=test_case.lookback_seconds,
        non_breaking_mode=SchemaChangeBackfillMode.BOUNDED,
        non_breaking_lookback_seconds=test_case.lookback_seconds,
    )
    e2e_clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(initial_compiled_pipeline).kafka_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(initial_compiled_pipeline).raw_table,
            database=e2e_clickhouse_database,
        )
    )
    e2e_clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(initial_compiled_pipeline).materialized_view,
            database=e2e_clickhouse_database,
        )
    )

    producer: KafkaProducer = build_kafka_producer(
        bootstrap_server=e2e_kafka_connection_settings.bootstrap_server
    )
    try:
        produce_kafka_messages(
            producer=producer,
            topic=require_managed_source(initial_compiled_pipeline).kafka_table.spec.kafka.topic,
            messages=(("historical-order", json.dumps({"order_id": "historical-order"})),),
        )
    finally:
        producer.close()

    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=require_managed_source(initial_compiled_pipeline).raw_table.name,
        expected_count=1,
    )
    initial_created_at: str
    initial_boundary_time: str
    initial_created_at, initial_boundary_time = build_near_replay_times(seconds_from_now=2)

    managed_client: ClickHouseClient = ClickHouseClient.from_config(
        ClickHouseConnectionConfig(
            host=e2e_clickhouse_connection_settings.host,
            port=e2e_clickhouse_connection_settings.port,
            username=e2e_clickhouse_connection_settings.username,
            password=e2e_clickhouse_connection_settings.password,
            database=e2e_clickhouse_database,
        )
    )
    try:
        execute_backfill(
            request=build_greenfield_workflow_request(
                clickhouse_database=e2e_clickhouse_database,
                compiled_pipeline=initial_compiled_pipeline,
                deployment_id=test_case.initial_deployment_id,
                created_at=initial_created_at,
                boundary_time=initial_boundary_time,
            ),
            client=managed_client,
        )
        execute_publish(
            request=PublishRequest(
                deployment_id=test_case.initial_deployment_id,
                metadata_database=e2e_clickhouse_database,
                default_database=e2e_clickhouse_database,
            ),
            client=managed_client,
        )
    finally:
        managed_client.close()

    time.sleep(test_case.lookback_seconds + 2)
    producer = build_kafka_producer(bootstrap_server=e2e_kafka_connection_settings.bootstrap_server)
    try:
        produce_kafka_messages(
            producer=producer,
            topic=require_managed_source(initial_compiled_pipeline).kafka_table.spec.kafka.topic,
            messages=(("frontier-order", json.dumps({"order_id": "frontier-order"})),),
        )
    finally:
        producer.close()

    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=require_managed_source(initial_compiled_pipeline).raw_table.name,
        expected_count=2,
    )
    changed_created_at: str
    changed_boundary_time: str
    changed_created_at, changed_boundary_time = build_near_replay_times(seconds_from_now=2)

    managed_client = ClickHouseClient.from_config(
        ClickHouseConnectionConfig(
            host=e2e_clickhouse_connection_settings.host,
            port=e2e_clickhouse_connection_settings.port,
            username=e2e_clickhouse_connection_settings.username,
            password=e2e_clickhouse_connection_settings.password,
            database=e2e_clickhouse_database,
        )
    )
    try:
        second_backfill_result: BackfillExecutionResult = execute_backfill(
            request=build_greenfield_workflow_request(
                clickhouse_database=e2e_clickhouse_database,
                compiled_pipeline=changed_compiled_pipeline,
                deployment_id=test_case.changed_deployment_id,
                created_at=changed_created_at,
                boundary_time=changed_boundary_time,
            ),
            client=managed_client,
        )
    finally:
        managed_client.close()

    expected_shadow_row_count: int = len(test_case.expected_selected_rows)
    wait_for_row_count(
        clickhouse_client=e2e_clickhouse_client,
        clickhouse_database=e2e_clickhouse_database,
        table_name=f"tbl__orders_enriched__{test_case.changed_deployment_id}",
        expected_count=expected_shadow_row_count,
    )

    managed_client = ClickHouseClient.from_config(
        ClickHouseConnectionConfig(
            host=e2e_clickhouse_connection_settings.host,
            port=e2e_clickhouse_connection_settings.port,
            username=e2e_clickhouse_connection_settings.username,
            password=e2e_clickhouse_connection_settings.password,
            database=e2e_clickhouse_database,
        )
    )
    try:
        execute_publish(
            request=PublishRequest(
                deployment_id=test_case.changed_deployment_id,
                metadata_database=e2e_clickhouse_database,
                default_database=e2e_clickhouse_database,
            ),
            client=managed_client,
        )
    finally:
        managed_client.close()

    selected_rows: Sequence[Sequence[object]] = e2e_clickhouse_client.query(
        "SELECT "
        + ", ".join(test_case.expected_selected_columns)
        + f" FROM {e2e_clickhouse_database}.tbl__orders_enriched ORDER BY order_id"
    ).result_rows
    described_columns: Sequence[Sequence[object]] = e2e_clickhouse_client.query(
        f"DESCRIBE TABLE {e2e_clickhouse_database}.tbl__orders_enriched"
    ).result_rows

    expected_selected_rows: list[tuple[object, ...]] = list(test_case.expected_selected_rows)
    if "kafka_topic" in test_case.expected_selected_columns:
        actual_topic_name: str = require_managed_source(
            changed_compiled_pipeline
        ).kafka_table.spec.kafka.topic
        expected_selected_rows = [
            (
                row[0],
                actual_topic_name if row[0] == "frontier-order" and len(row) > 1 else row[1],
            )
            if len(row) == 2
            else row
            for row in expected_selected_rows
        ]

    assert (
        second_backfill_result.bootstrap.deployment_plan.rebuild_subtrees[0].execution_mode
        == test_case.expected_execution_mode
    )
    assert tuple(row[0] for row in described_columns) == test_case.expected_view_column_names
    assert selected_rows == expected_selected_rows
