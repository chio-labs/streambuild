import json
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from shutil import copytree
from typing import Any

from clickhouse_connect.driver.client import Client
from kafka import KafkaProducer

from streambuild.clickhouse.render.main.render_create_kafka_table_ddl import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render.main.render_create_materialized_view_ddl import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render.main.render_create_table_ddl import render_create_table_ddl
from streambuild.compiler.compile.main.compile_pipeline import compile_pipeline
from streambuild.compiler.compile.models import (
    Column,
    CompiledManagedSource,
    CompiledPipeline,
    CompiledTransformStep,
    DesiredKafkaTable,
    DesiredState,
    KafkaSettings,
    KafkaTableSpec,
)
from streambuild.compiler.desired_state.main.build_desired_state import build_desired_state
from streambuild.compiler.discovery.main.discover_pipelines import discover_pipelines
from streambuild.compiler.discovery.models import (
    LoadedPipeline,
    SchemaChangeBackfillPolicy,
    SchemaChangeBackfillRule,
)
from streambuild.compiler.discovery.types import ReplayLineageMode, SchemaChangeBackfillMode
from streambuild.executor.backfill.models import BackfillBootstrapRequest
from tests.e2e.src.streambuild.conftest import (
    E2EClickHouseConnectionSettings,
    E2EKafkaConnectionSettings,
)
from tests.e2e.src.streambuild.executor._test_types import (
    KafkaLiveShadowScenarioResult,
    KafkaLiveShadowWorkflowE2ETestCase,
)
from tests.integration.src.streambuild.compiler.planner.helpers import (
    build_changed_schema_variant_compiled_pipeline,
)
from tests.integration.src.streambuild.executor.backfill.helpers import (
    build_offset_replay_compiled_pipeline,
    build_scalar_replay_compiled_pipeline,
)

E2E_KAFKA_TIMESTAMP_PROJECT_DIR: Path = Path("tests/fixtures/e2e_kafka_timestamp_project")
E2E_KAFKA_OFFSET_PROJECT_DIR: Path = Path("tests/fixtures/e2e_kafka_offset_project")
REPO_ROOT: Path = Path(__file__).resolve().parents[5]


def require_managed_source(compiled_pipeline: CompiledPipeline) -> CompiledManagedSource:
    assert isinstance(compiled_pipeline.source, CompiledManagedSource), (
        "Expected compiled pipeline to use a managed Kafka source"
    )
    return compiled_pipeline.source


def build_greenfield_workflow_compiled_pipeline(
    *, kafka_broker_list: str, topic_suffix: str | None = None
) -> CompiledPipeline:
    compiled_pipeline: CompiledPipeline = build_scalar_replay_compiled_pipeline(
        ReplayLineageMode.TIMESTAMP
    )
    return _with_kafka_broker_list_and_topic(
        compiled_pipeline=compiled_pipeline,
        kafka_broker_list=kafka_broker_list,
        topic_suffix=topic_suffix,
    )


def build_authored_greenfield_workflow_compiled_pipeline(*, project_dir: Path) -> CompiledPipeline:
    loaded_pipelines: list[LoadedPipeline] = discover_pipelines(project_dir / "pipelines")
    assert not (len(loaded_pipelines) != 1), "Expected exactly one authored e2e pipeline fixture"
    return compile_pipeline(loaded_pipelines[0])


def prepare_authored_e2e_project(
    *,
    fixture_project_dir: Path,
    tmp_path: Path,
    kafka_broker_list: str,
    topic_suffix: str,
) -> Path:
    project_dir: Path = tmp_path / fixture_project_dir.name
    copytree(fixture_project_dir, project_dir)
    pipeline_file: Path = project_dir / "pipelines" / "order_events" / "pipeline.yml"
    pipeline_contents: str = pipeline_file.read_text(encoding="utf-8")
    pipeline_contents = pipeline_contents.replace(
        "broker_list: kafka:9092", f"broker_list: {kafka_broker_list}"
    )
    pipeline_contents = pipeline_contents.replace(
        "topic: source.order_events.created",
        f"topic: source.order_events.created_{topic_suffix}",
    )
    pipeline_file.write_text(pipeline_contents, encoding="utf-8")
    return project_dir


def run_kafka_live_shadow_scenario(
    *,
    test_case: KafkaLiveShadowWorkflowE2ETestCase,
    clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    kafka_connection_settings: E2EKafkaConnectionSettings,
    clickhouse_client: Client,
    clickhouse_database: str,
    tmp_path: Path,
) -> KafkaLiveShadowScenarioResult:
    project_dir: Path = prepare_authored_e2e_project(
        fixture_project_dir=E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
        tmp_path=tmp_path,
        kafka_broker_list=kafka_connection_settings.internal_bootstrap_server,
        topic_suffix=clickhouse_database,
    )
    compiled_pipeline: CompiledPipeline = build_authored_greenfield_workflow_compiled_pipeline(
        project_dir=project_dir
    )
    target_table_name: str = compiled_pipeline.transforms[0].target_table_name
    clickhouse_client.command(
        render_create_kafka_table_ddl(
            table=require_managed_source(compiled_pipeline).kafka_table,
            database=clickhouse_database,
        )
    )
    clickhouse_client.command(
        render_create_table_ddl(
            table=require_managed_source(compiled_pipeline).raw_table,
            database=clickhouse_database,
        )
    )
    clickhouse_client.command(
        render_create_materialized_view_ddl(
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
            database=clickhouse_database,
        )
    )

    producer: KafkaProducer = build_kafka_producer(
        bootstrap_server=kafka_connection_settings.bootstrap_server
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
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=require_managed_source(compiled_pipeline).raw_table.name,
        expected_count=len(test_case.initial_order_ids),
    )
    run_streambuild_backfill_cli(
        project_dir=project_dir,
        host=clickhouse_connection_settings.host,
        port=clickhouse_connection_settings.port,
        username=clickhouse_connection_settings.username,
        password=clickhouse_connection_settings.password,
        database=clickhouse_database,
        deployment_id=test_case.deployment_id,
    )

    staged_table_name: str = f"{target_table_name}__{test_case.deployment_id}"
    wait_for_live_shadow_row_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        raw_table_name=require_managed_source(compiled_pipeline).raw_table.name,
        staged_table_name=staged_table_name,
        expected_count=len(test_case.initial_order_ids),
    )

    producer = build_kafka_producer(bootstrap_server=kafka_connection_settings.bootstrap_server)
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

    total_order_count: int = len(test_case.initial_order_ids) + len(test_case.live_order_ids)
    wait_for_row_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=require_managed_source(compiled_pipeline).raw_table.name,
        expected_count=total_order_count,
    )
    wait_for_live_shadow_row_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        raw_table_name=require_managed_source(compiled_pipeline).raw_table.name,
        staged_table_name=staged_table_name,
        expected_count=total_order_count,
    )
    staged_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id FROM {clickhouse_database}.{staged_table_name} ORDER BY order_id"
    ).result_rows

    run_streambuild_publish_cli(
        host=clickhouse_connection_settings.host,
        port=clickhouse_connection_settings.port,
        username=clickhouse_connection_settings.username,
        password=clickhouse_connection_settings.password,
        database=clickhouse_database,
        deployment_id=test_case.deployment_id,
    )
    final_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id FROM {clickhouse_database}.{target_table_name} ORDER BY order_id"
    ).result_rows
    return KafkaLiveShadowScenarioResult(
        staged_table_name=staged_table_name,
        staged_order_ids=tuple(str(row[0]) for row in staged_rows),
        deployment_id=test_case.deployment_id,
        final_rows=tuple(tuple(row) for row in final_rows),
    )


def prepare_external_source_e2e_project(*, tmp_path: Path) -> Path:
    project_dir: Path = tmp_path / "external_source_project"
    pipeline_dir: Path = project_dir / "pipelines" / "orders"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "streambuild_project.yml").write_text("{}\n", encoding="utf-8")
    (pipeline_dir / "pipeline.yml").write_text(
        """
source:
  kind: kafka
  name: orders
  table_name: orders_existing
  replay_boundary:
    mode: timestamp
    columns:
      _replay_timestamp: event_timestamp
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (pipeline_dir / "orders_enriched.sql").write_text(
        """
MODEL (
  engine: "MergeTree()",
  order_by: ["order_id"],
);

SELECT
  CAST(order_id AS String) AS order_id,
  CAST(_replay_timestamp AS DateTime64(3)) AS _replay_timestamp
FROM __ref("orders")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return project_dir


def prepare_external_source_cursor_e2e_project(*, tmp_path: Path) -> Path:
    project_dir: Path = tmp_path / "external_source_cursor_project"
    pipeline_dir: Path = project_dir / "pipelines" / "orders"
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "streambuild_project.yml").write_text("{}\n", encoding="utf-8")
    (pipeline_dir / "pipeline.yml").write_text(
        """
source:
  kind: stream_table
  name: orders
  table_name: orders_existing
  replay_boundary:
    mode: cursor
    columns:
      _replay_cursor: event_cursor
      _replay_timestamp: event_timestamp
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (pipeline_dir / "orders_enriched.sql").write_text(
        """
MODEL (
  engine: "MergeTree()",
  order_by: ["order_id"],
);

SELECT
  CAST(order_id AS String) AS order_id,
  CAST(_replay_cursor AS UInt64) AS _replay_cursor
FROM __ref("orders")
""".strip()
        + "\n",
        encoding="utf-8",
    )
    return project_dir


def run_streambuild_backfill_cli(
    *,
    project_dir: Path,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    deployment_id: str,
) -> None:
    _run_streambuild_cli(
        command=(
            "backfill",
            "--project-dir",
            str(project_dir),
            "--host",
            host,
            "--port",
            str(port),
            "--username",
            username,
            "--password",
            password,
            "--database",
            database,
            "--deployment-id",
            deployment_id,
            "--auto-approve",
        )
    )


def run_streambuild_audit_backfill_cli(
    *,
    project_dir: Path,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    deployment_id: str,
) -> dict[str, object]:
    return _run_streambuild_cli_json(
        command=(
            "audit",
            "backfill",
            "--project-dir",
            str(project_dir),
            "--host",
            host,
            "--port",
            str(port),
            "--username",
            username,
            "--password",
            password,
            "--database",
            database,
            "--deployment-id",
            deployment_id,
            "--json",
        )
    )


def run_streambuild_publish_cli(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    deployment_id: str,
) -> None:
    _run_streambuild_cli(
        command=(
            "publish",
            "--host",
            host,
            "--port",
            str(port),
            "--username",
            username,
            "--password",
            password,
            "--database",
            database,
            "--deployment-id",
            deployment_id,
        )
    )


def run_streambuild_doctor_cli(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
) -> dict[str, object]:
    return _run_streambuild_cli_json(
        command=(
            "doctor",
            "--host",
            host,
            "--port",
            str(port),
            "--username",
            username,
            "--password",
            password,
            "--database",
            database,
        )
    )


def run_streambuild_repair_active_view_cli(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    table_name: str,
    deployment_id: str,
) -> dict[str, object]:
    return _run_streambuild_cli_json(
        command=(
            "repair",
            "active-view",
            "--host",
            host,
            "--port",
            str(port),
            "--username",
            username,
            "--password",
            password,
            "--database",
            database,
            "--table",
            table_name,
            "--deployment-id",
            deployment_id,
        )
    )


def _run_streambuild_cli(*, command: tuple[str, ...]) -> None:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["uv", "run", "stb", *command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert not (result.returncode != 0), (
        f"stb {' '.join(command)} failed with code {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def _run_streambuild_cli_json(*, command: tuple[str, ...]) -> dict[str, object]:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["uv", "run", "stb", *command],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert not (result.returncode != 0), (
        f"stb {' '.join(command)} failed with code {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    return json.loads(result.stdout)


def build_changed_greenfield_workflow_compiled_pipeline(
    *, kafka_broker_list: str, topic_suffix: str | None = None
) -> CompiledPipeline:
    compiled_pipeline: CompiledPipeline = build_greenfield_workflow_compiled_pipeline(
        kafka_broker_list=kafka_broker_list,
        topic_suffix=topic_suffix,
    )
    original_transform: CompiledTransformStep = compiled_pipeline.transforms[0]
    changed_query: str = f"{original_transform.materialized_view.query} WHERE 1 = 1"
    changed_transform: CompiledTransformStep = replace(
        original_transform,
        resolved_query=f"{original_transform.resolved_query} WHERE 1 = 1",
        materialized_view=replace(
            original_transform.materialized_view,
            spec=replace(original_transform.materialized_view.spec, query=changed_query),
        ),
    )
    return replace(compiled_pipeline, transforms=(changed_transform,))


def build_greenfield_workflow_request(
    *,
    clickhouse_database: str,
    compiled_pipeline: CompiledPipeline,
    deployment_id: str,
    created_at: str,
    boundary_time: str,
) -> BackfillBootstrapRequest:
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=clickhouse_database,
        metadata_database=clickhouse_database,
        replay_lineage_mode=compiled_pipeline.effective_replay_lineage_mode,
        deployment_id=deployment_id,
        created_at=created_at,
        boundary_time=boundary_time,
        stabilization_seconds=0.0,
    )


def build_offset_workflow_compiled_pipeline(
    *, kafka_broker_list: str, topic_suffix: str | None = None
) -> CompiledPipeline:
    compiled_pipeline: CompiledPipeline = build_offset_replay_compiled_pipeline()
    return _with_kafka_broker_list_and_topic(
        compiled_pipeline=compiled_pipeline,
        kafka_broker_list=kafka_broker_list,
        topic_suffix=topic_suffix,
    )


SCHEMA_CHANGE_PIPELINE_BUILDERS: dict[str, Callable[[], CompiledPipeline]] = {
    "base": lambda: build_scalar_replay_compiled_pipeline(ReplayLineageMode.TIMESTAMP),
    "add_column": lambda: build_changed_schema_variant_compiled_pipeline("add_column"),
    "remove_column": lambda: build_changed_schema_variant_compiled_pipeline("remove_column"),
    "type_change": lambda: _build_non_boundary_type_change_compiled_pipeline(),
}


def build_schema_change_workflow_compiled_pipeline(
    *, kafka_broker_list: str, pipeline_kind: str, topic_suffix: str | None = None
) -> CompiledPipeline:
    builder: Callable[[], CompiledPipeline] = SCHEMA_CHANGE_PIPELINE_BUILDERS[pipeline_kind]
    compiled_pipeline: CompiledPipeline = builder()
    return _with_kafka_broker_list_and_topic(
        compiled_pipeline=compiled_pipeline,
        kafka_broker_list=kafka_broker_list,
        topic_suffix=topic_suffix,
    )


def with_schema_change_backfill_policy(
    *,
    compiled_pipeline: CompiledPipeline,
    breaking_mode: SchemaChangeBackfillMode | str,
    breaking_lookback_seconds: int | None,
    non_breaking_mode: SchemaChangeBackfillMode | str,
    non_breaking_lookback_seconds: int | None,
) -> CompiledPipeline:
    original_transform: CompiledTransformStep = compiled_pipeline.transforms[0]
    return replace(
        compiled_pipeline,
        transforms=(
            replace(
                original_transform,
                target_table=replace(
                    original_transform.target_table,
                    schema_change_backfill=SchemaChangeBackfillPolicy(
                        breaking=SchemaChangeBackfillRule(
                            mode=SchemaChangeBackfillMode(breaking_mode),
                            lookback_seconds=breaking_lookback_seconds,
                        ),
                        non_breaking=SchemaChangeBackfillRule(
                            mode=SchemaChangeBackfillMode(non_breaking_mode),
                            lookback_seconds=non_breaking_lookback_seconds,
                        ),
                    ),
                ),
            ),
        ),
    )


def build_near_replay_times(*, seconds_from_now: int) -> tuple[str, str]:
    replay_time: datetime = datetime.now(tz=UTC) + timedelta(seconds=seconds_from_now)
    boundary_time: str = replay_time.strftime("%Y-%m-%d %H:%M:%S.000")
    created_at: str = replay_time.strftime("%Y-%m-%d %H:%M:%S.123")
    return created_at, boundary_time


def _with_kafka_broker_list_and_topic(
    *,
    compiled_pipeline: CompiledPipeline,
    kafka_broker_list: str,
    topic_suffix: str | None,
) -> CompiledPipeline:
    original_kafka_table: DesiredKafkaTable = require_managed_source(compiled_pipeline).kafka_table
    base_topic_name: str = original_kafka_table.spec.kafka.topic
    topic_parts: tuple[str, ...] = tuple(filter(None, (base_topic_name, topic_suffix)))
    topic_name: str = "_".join(topic_parts)
    kafka_table: DesiredKafkaTable = DesiredKafkaTable(
        key=original_kafka_table.key,
        deps=original_kafka_table.deps,
        spec=KafkaTableSpec(
            columns=original_kafka_table.spec.columns,
            kafka=KafkaSettings(
                broker_list=kafka_broker_list,
                topic=topic_name,
                consumer_group=original_kafka_table.spec.kafka.consumer_group,
                format=original_kafka_table.spec.kafka.format,
                settings=original_kafka_table.spec.kafka.settings,
            ),
        ),
    )
    return CompiledPipeline(
        pipeline=compiled_pipeline.pipeline,
        project=compiled_pipeline.project,
        file_path=compiled_pipeline.file_path,
        relation_names=compiled_pipeline.relation_names,
        relation_sqls=compiled_pipeline.relation_sqls,
        effective_replay_lineage_mode=compiled_pipeline.effective_replay_lineage_mode,
        source=CompiledManagedSource(
            kafka_table=kafka_table,
            raw_table=require_managed_source(compiled_pipeline).raw_table,
            materialized_view=require_managed_source(compiled_pipeline).materialized_view,
        ),
        transforms=compiled_pipeline.transforms,
    )


def _build_non_boundary_type_change_compiled_pipeline() -> CompiledPipeline:
    base_pipeline: CompiledPipeline = build_changed_schema_variant_compiled_pipeline("add_column")
    original_transform: CompiledTransformStep = base_pipeline.transforms[0]
    changed_query: str = original_transform.materialized_view.query.replace(
        "CAST(kafka_topic AS String) AS kafka_topic",
        "CAST(kafka_topic AS FixedString(128)) AS kafka_topic",
    )
    changed_column_types: dict[str, str] = {"kafka_topic": "FixedString(128)"}
    changed_columns: tuple[Column, ...] = tuple(
        replace(column, type=changed_column_types.get(column.name, column.type))
        for column in original_transform.target_table.columns
    )
    return replace(
        base_pipeline,
        transforms=(
            replace(
                original_transform,
                resolved_query=original_transform.resolved_query.replace(
                    "CAST(kafka_topic AS String) AS kafka_topic",
                    "CAST(kafka_topic AS FixedString(128)) AS kafka_topic",
                ),
                materialized_view=replace(
                    original_transform.materialized_view,
                    spec=replace(original_transform.materialized_view.spec, query=changed_query),
                ),
                target_table=replace(
                    original_transform.target_table,
                    spec=replace(
                        original_transform.target_table.spec,
                        columns=changed_columns,
                    ),
                ),
            ),
        ),
    )


def build_offset_workflow_request(
    *,
    clickhouse_database: str,
    compiled_pipeline: CompiledPipeline,
    deployment_id: str,
    created_at: str,
    boundary_time: str,
) -> BackfillBootstrapRequest:
    desired_state: DesiredState = build_desired_state((compiled_pipeline,))
    return BackfillBootstrapRequest(
        desired_state=desired_state,
        default_database=clickhouse_database,
        metadata_database=clickhouse_database,
        replay_lineage_mode="offsets",
        deployment_id=deployment_id,
        created_at=created_at,
        boundary_time=boundary_time,
        stabilization_seconds=0.0,
    )


def build_kafka_producer(*, bootstrap_server: str) -> KafkaProducer:
    return KafkaProducer(bootstrap_servers=bootstrap_server)


def build_future_replay_times(*, seconds_from_now: int) -> tuple[str, str]:
    replay_time: datetime = datetime.now(tz=UTC) + timedelta(minutes=5, seconds=seconds_from_now)
    boundary_time: str = replay_time.strftime("%Y-%m-%d %H:%M:%S.000")
    created_at: str = replay_time.strftime("%Y-%m-%d %H:%M:%S.123")
    return created_at, boundary_time


def produce_kafka_messages(
    *,
    producer: KafkaProducer,
    topic: str,
    messages: tuple[tuple[str, str], ...],
) -> None:
    message_key: str
    message_value: str
    for message_key, message_value in messages:
        producer.send(
            topic,
            key=message_key.encode("utf-8"),
            value=message_value.encode("utf-8"),
        )
    producer.flush()


def wait_for_live_shadow_row_count(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    raw_table_name: str,
    staged_table_name: str,
    expected_count: int,
    timeout_seconds: float = 45.0,
) -> None:
    try:
        wait_for_row_count(
            clickhouse_client=clickhouse_client,
            clickhouse_database=clickhouse_database,
            table_name=staged_table_name,
            expected_count=expected_count,
            timeout_seconds=timeout_seconds,
        )
    except AssertionError as error:
        raise AssertionError(
            build_live_shadow_debug_message(
                clickhouse_client=clickhouse_client,
                clickhouse_database=clickhouse_database,
                raw_table_name=raw_table_name,
                staged_table_name=staged_table_name,
                error=error,
            )
        ) from error


def build_live_shadow_debug_message(
    *,
    clickhouse_client: Client,
    clickhouse_database: str,
    raw_table_name: str,
    staged_table_name: str,
    error: AssertionError,
) -> str:
    staged_mv_name: str = staged_table_name.replace("tbl__", "mv__", 1)
    live_table_name: str = staged_table_name.rsplit("__", maxsplit=1)[0]
    raw_count: int = _query_table_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=raw_table_name,
    )
    staged_count: int = _query_table_count(
        clickhouse_client=clickhouse_client,
        clickhouse_database=clickhouse_database,
        table_name=staged_table_name,
    )
    latest_raw_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT _replay_partition, _replay_offset, _replay_timestamp FROM "
        f"{clickhouse_database}.{raw_table_name} "
        "ORDER BY _replay_partition DESC, _replay_offset DESC LIMIT 5"
    ).result_rows
    latest_staged_rows: Sequence[Sequence[object]] = clickhouse_client.query(
        f"SELECT order_id, _replay_timestamp FROM {clickhouse_database}.{staged_table_name} "
        "ORDER BY _replay_timestamp DESC, order_id DESC LIMIT 5"
    ).result_rows
    live_count: int | None = clickhouse_client.query(
        "SELECT anyOrNull(total_rows) FROM system.tables "
        f"WHERE database = '{clickhouse_database}' AND name = '{live_table_name}'"
    ).result_rows[0][0]
    staged_mv_metadata: Sequence[object] = clickhouse_client.query(
        "SELECT count() > 0, anyOrNull(create_table_query) FROM system.tables "
        f"WHERE database = '{clickhouse_database}' AND name = '{staged_mv_name}'"
    ).result_rows[0]
    staged_mv_exists: bool = bool(staged_mv_metadata[0])
    staged_mv_ddl: str | None = staged_mv_metadata[1]
    return (
        f"{error}. raw_count={raw_count}, staged_count={staged_count}, "
        f"live_count={live_count}, staged_mv_exists={staged_mv_exists}, "
        f"latest_raw_rows={tuple(latest_raw_rows)}, "
        f"latest_staged_rows={tuple(latest_staged_rows)}, "
        f"staged_mv_ddl={staged_mv_ddl!r}"
    )


def _query_table_count(
    *, clickhouse_client: Client, clickhouse_database: str, table_name: str
) -> int:
    return int(
        clickhouse_client.query(
            f"SELECT count() FROM {clickhouse_database}.{table_name}"
        ).result_rows[0][0]
    )


def wait_for_row_count(
    *,
    clickhouse_client: Client,
    table_name: str,
    clickhouse_database: str,
    expected_count: int,
    timeout_seconds: float = 25.0,
    poll_interval_seconds: float = 0.5,
) -> None:
    deadline: float = time.time() + timeout_seconds
    while time.time() < deadline:
        result: Any = clickhouse_client.query(
            f"SELECT count() FROM {clickhouse_database}.{table_name}"
        )
        actual_count: int = int(result.result_rows[0][0])
        if actual_count >= expected_count:
            return
        time.sleep(poll_interval_seconds)
    raise AssertionError(
        f"Timed out waiting for {clickhouse_database}.{table_name} to reach {expected_count} rows"
    )


def wait_for_table_exists(
    *,
    clickhouse_client: Client,
    table_name: str,
    clickhouse_database: str,
    timeout_seconds: float = 15.0,
    poll_interval_seconds: float = 0.5,
) -> None:
    deadline: float = time.time() + timeout_seconds
    while time.time() < deadline:
        result: Any = clickhouse_client.query(
            "SELECT count() FROM system.tables "
            f"WHERE database = '{clickhouse_database}' AND name = '{table_name}'"
        )
        if int(result.result_rows[0][0]) > 0:
            return
        time.sleep(poll_interval_seconds)
    raise AssertionError(f"Timed out waiting for {clickhouse_database}.{table_name} to exist")


def wait_for_table_missing(
    *,
    clickhouse_client: Client,
    table_name: str,
    clickhouse_database: str,
    timeout_seconds: float = 15.0,
    poll_interval_seconds: float = 0.5,
) -> None:
    deadline: float = time.time() + timeout_seconds
    while time.time() < deadline:
        result: Any = clickhouse_client.query(
            "SELECT count() FROM system.tables "
            f"WHERE database = '{clickhouse_database}' AND name = '{table_name}'"
        )
        if int(result.result_rows[0][0]) == 0:
            return
        time.sleep(poll_interval_seconds)
    raise AssertionError(f"Timed out waiting for {clickhouse_database}.{table_name} to disappear")
