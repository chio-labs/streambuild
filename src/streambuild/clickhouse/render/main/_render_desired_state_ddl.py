"""Render ClickHouse DDL for deployment-oriented desired state."""

from streambuild.clickhouse.render.main.render_create_kafka_table_ddl import (
    render_create_kafka_table_ddl,
)
from streambuild.clickhouse.render.main.render_create_materialized_view_ddl import (
    render_create_materialized_view_ddl,
)
from streambuild.clickhouse.render.main.render_create_table_ddl import render_create_table_ddl
from streambuild.clickhouse.render.models import RenderedClickHouseDdl
from streambuild.compiler.compile.models import (
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
)


def render_desired_state_ddl(
    *,
    desired_state: DesiredState,
    database: str,
) -> tuple[RenderedClickHouseDdl, ...]:
    """Render the current desired state into deterministic ordered DDL statements."""

    rendered_objects: list[RenderedClickHouseDdl] = []
    object_: DesiredKafkaTable | DesiredTable | DesiredMaterializedView
    for object_ in desired_state.objects:
        object_database: str = object_.key.database or database
        rendered_objects.append(
            RenderedClickHouseDdl(
                key=object_.key,
                ddl=_render_desired_object_ddl(
                    object_=object_,
                    database=object_database,
                ),
            )
        )

    return tuple(rendered_objects)


def _render_desired_object_ddl(
    *,
    object_: DesiredKafkaTable | DesiredTable | DesiredMaterializedView,
    database: str,
) -> str:
    """Render a single desired object into ClickHouse DDL."""

    if isinstance(object_, DesiredKafkaTable):
        return render_create_kafka_table_ddl(
            table=object_,
            database=database,
        )

    if isinstance(object_, DesiredTable):
        return render_create_table_ddl(table=object_, database=database)

    return render_create_materialized_view_ddl(materialized_view=object_, database=database)
