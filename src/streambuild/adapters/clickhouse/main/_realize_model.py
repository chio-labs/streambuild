"""Realize one logical model as ClickHouse resources."""

from streambuild.adapter.models import (
    AdapterMaterializedView,
    AdapterModelRealization,
    AdapterModelRealizationRequest,
    AdapterTable,
    AdapterView,
    AdapterViewRealizationRequest,
)
from streambuild.adapters.clickhouse.constants import CLICKHOUSE_MATERIALIZED_VIEW_NAME_PREFIX


def realize_clickhouse_model(
    *, request: AdapterModelRealizationRequest | AdapterViewRealizationRequest
) -> AdapterModelRealization:
    """Realize one logical model as its ClickHouse resources."""

    if isinstance(request, AdapterViewRealizationRequest):
        return AdapterModelRealization(
            relation_name=request.target_relation_name,
            resources=(
                AdapterView(
                    name=request.target_relation_name,
                    query=request.resolved_query,
                    database_template=request.resolved_database_template,
                ),
            ),
        )

    return AdapterModelRealization(
        relation_name=request.target_relation_name,
        resources=(
            AdapterTable(
                name=request.target_relation_name,
                columns=request.columns,
                engine=request.engine,
                order_by=request.order_by,
                partition_by=request.partition_by,
                ttl=request.ttl,
                settings=request.settings,
            ),
            AdapterMaterializedView(
                name=f"{CLICKHOUSE_MATERIALIZED_VIEW_NAME_PREFIX}{request.logical_name}",
                source_relation_name=request.source_relation_name,
                target_relation_name=request.target_relation_name,
                query=request.resolved_query,
                database_template=request.resolved_database_template,
            ),
        ),
    )
