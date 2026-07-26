"""Build a compiler-analyzed query for adapter replay."""

from sqlglot import exp, parse_one

from streambuild.adapter.models import AdapterPhysicalRelationMapping, AdapterReplayQuery
from streambuild.compiler.planner.exceptions import DeploymentPlanError


def build_adapter_replay_query(
    *,
    query: str,
    source_relation_name: str,
    database: str,
    physical_relation_mappings: tuple[AdapterPhysicalRelationMapping, ...],
) -> AdapterReplayQuery:
    """Rewrite side references physically and classify aggregate semantics."""

    parsed_expression: object = parse_one(query, dialect="clickhouse")
    if not isinstance(parsed_expression, exp.Select):
        raise DeploymentPlanError("Replay expects a SELECT query")
    expression: exp.Select = parsed_expression
    physical_name_by_logical_name: dict[str, str] = {
        mapping.logical_name: mapping.physical_name for mapping in physical_relation_mappings
    }
    table: exp.Table
    for table in expression.find_all(exp.Table):
        if table.name == source_relation_name:
            continue
        physical_name: str | None = physical_name_by_logical_name.get(table.name)
        if physical_name is not None:
            table.set("this", exp.to_identifier(physical_name))
            table.set("db", exp.to_identifier(database))
    return AdapterReplayQuery(
        query=expression.sql(dialect="clickhouse"),
        physical_relation_mappings=physical_relation_mappings,
        aggregate_semantics=(
            expression.find(exp.Group) is not None or expression.find(exp.AggFunc) is not None
        ),
    )
