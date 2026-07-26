"""Shadow object creation for backfill bootstrap execution."""

from dataclasses import replace

from sqlglot import exp, parse_one

from streambuild.clickhouse.render._helpers.create_kafka_table import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render._helpers.create_materialized_view import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render._helpers.create_table import render_create_table_ddl
from streambuild.compiler.compile.models import DesiredState
from streambuild.compiler.planner.constants import DEPLOYMENT_PHASE_PLAN
from streambuild.compiler.planner.models import DeploymentPlan
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_TABLE,
    RAW_TABLE_NAME_PREFIX,
)
from streambuild.compiler.shared.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    MaterializedViewSpec,
    ObjectKey,
)
from streambuild.executor.backfill.exceptions import BackfillExecutionError
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient


def create_shadow_objects(
    *,
    client: ClickHouseClient,
    deployment_plan: DeploymentPlan,
    desired_state: DesiredState,
    default_database: str,
) -> None:
    """Create staged physical objects for the planned backfill deployment."""

    _ensure_live_landing_objects(
        client=client,
        desired_state=desired_state,
        default_database=default_database,
    )
    object_by_key: dict[ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView] = {
        object_.key: object_ for object_ in desired_state.objects
    }
    physical_name_by_key: dict[ObjectKey, str] = {
        prepared.logical_key: prepared.physical_name
        for prepared in deployment_plan.prepared_shadow_objects
    }
    for target_key in _ordered_shadow_creation_keys(
        desired_state=desired_state, deployment_plan=deployment_plan
    ):
        desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = object_by_key[
            target_key
        ]
        database: str = desired_object.key.database or default_database
        client.command(
            _render_shadow_ddl(
                desired_object=desired_object,
                physical_name=physical_name_by_key[target_key],
                physical_name_by_key=physical_name_by_key,
                database=database,
            )
        )


def _ensure_live_landing_objects(
    *,
    client: ClickHouseClient,
    desired_state: DesiredState,
    default_database: str,
) -> None:
    existing_names: set[str] = _existing_table_names(client=client, database=default_database)
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        database: str = desired_object.key.database or default_database
        if isinstance(desired_object, DesiredKafkaTable):
            client.command(
                render_create_kafka_table_ddl(
                    table=desired_object,
                    database=database,
                    if_not_exists=True,
                )
            )
            existing_names.add(desired_object.name)
            continue
        if isinstance(desired_object, DesiredTable) and desired_object.name.startswith(
            RAW_TABLE_NAME_PREFIX
        ):
            if desired_object.name in existing_names:
                continue
            client.command(
                render_create_table_ddl(
                    table=desired_object,
                    database=database,
                )
            )
            existing_names.add(desired_object.name)
            continue
        if isinstance(
            desired_object, DesiredMaterializedView
        ) and desired_object.target_table_name.startswith(RAW_TABLE_NAME_PREFIX):
            if desired_object.name in existing_names:
                continue
            client.command(
                render_create_materialized_view_ddl(
                    materialized_view=desired_object,
                    database=database,
                )
            )
            existing_names.add(desired_object.name)


def _existing_table_names(*, client: ClickHouseClient, database: str) -> set[str]:
    rows: tuple[tuple[object, ...], ...] = client.query(
        f"SELECT name FROM system.tables WHERE database = '{database}'"
    ).rows
    return {str(row[0]) for row in rows}


def _render_shadow_ddl(
    *,
    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView,
    physical_name: str,
    physical_name_by_key: dict[ObjectKey, str],
    database: str,
) -> str:
    if isinstance(desired_object, DesiredKafkaTable):
        raise BackfillExecutionError("Backfill bootstrap does not support shadow Kafka tables")
    if isinstance(desired_object, DesiredTable):
        return render_create_table_ddl(
            table=replace(
                desired_object,
                key=replace(desired_object.key, name=physical_name),
            ),
            database=database,
        )

    shadow_source_name: str = _shadow_table_name(
        logical_name=desired_object.source_table_name,
        physical_name_by_key=physical_name_by_key,
    )
    shadow_target_name: str = _shadow_table_name(
        logical_name=desired_object.target_table_name,
        physical_name_by_key=physical_name_by_key,
    )
    return render_create_materialized_view_ddl(
        materialized_view=replace(
            desired_object,
            key=replace(desired_object.key, name=physical_name),
            spec=MaterializedViewSpec(
                source_table_name=shadow_source_name,
                target_table_name=shadow_target_name,
                query=_rewrite_shadow_query_tables(
                    query=desired_object.query,
                    physical_name_by_key=physical_name_by_key,
                ),
            ),
        ),
        database=database,
    )


def _shadow_table_name(
    *,
    logical_name: str,
    physical_name_by_key: dict[ObjectKey, str],
) -> str:
    key: ObjectKey
    physical_name: str
    for key, physical_name in physical_name_by_key.items():
        if key.object_type == DESIRED_OBJECT_TYPE_TABLE and key.name == logical_name:
            return physical_name
    return logical_name


def _rewrite_shadow_query_tables(
    *,
    query: str,
    physical_name_by_key: dict[ObjectKey, str],
) -> str:
    expression: exp.Expr = parse_one(query, dialect="clickhouse")
    table_name_to_physical_name: dict[str, str] = {
        key.name: physical_name
        for key, physical_name in physical_name_by_key.items()
        if key.object_type == DESIRED_OBJECT_TYPE_TABLE
    }
    table: exp.Table
    for table in expression.find_all(exp.Table):
        if table.db:
            continue
        physical_name: str | None = table_name_to_physical_name.get(table.name)
        if physical_name is None:
            continue
        table.set("this", exp.to_identifier(physical_name))

    return expression.sql(dialect="clickhouse")


def _ordered_shadow_creation_keys(
    *,
    desired_state: DesiredState,
    deployment_plan: DeploymentPlan,
) -> tuple[ObjectKey, ...]:
    planned_keys: set[ObjectKey] = {
        step.target_key
        for step in deployment_plan.steps
        if step.phase == DEPLOYMENT_PHASE_PLAN and step.target_key is not None
    }
    object_by_key: dict[ObjectKey, DesiredKafkaTable | DesiredTable | DesiredMaterializedView] = {
        object_.key: object_ for object_ in desired_state.objects
    }
    ordered_keys: list[ObjectKey] = []
    visited_keys: set[ObjectKey] = set()

    def visit(key: ObjectKey) -> None:
        if key not in planned_keys or key in visited_keys:
            return
        visited_keys.add(key)
        desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView = object_by_key[
            key
        ]
        dependency_key: ObjectKey
        for dependency_key in desired_object.deps:
            visit(dependency_key)
        ordered_keys.append(key)

    desired_object: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for desired_object in desired_state.objects:
        visit(desired_object.key)
    return tuple(ordered_keys)
