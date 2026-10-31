"""Derive ClickHouse aggregate facts from a parsed model tree's aggregate function names."""

from sqltide.compiler.sql_analysis.constants import CLICKHOUSE_AGGREGATING_ENGINE_NAMES
from sqltide.compiler.sql_analysis.models import SqlAggregateFacts


def build_aggregate_facts(
    *, function_names: list[str], has_group_by: bool, engine: str
) -> SqlAggregateFacts:
    """Return query and engine aggregation facts without generic aliases."""

    engine_name: str = engine.partition("(")[0].strip()
    normalized_engine_name: str = engine_name.lower().removeprefix("replicated")
    return SqlAggregateFacts(
        has_group_by=has_group_by,
        function_names=tuple(dict.fromkeys(function_names)),
        engine_name=engine_name,
        engine_has_aggregate_semantics=(
            normalized_engine_name in CLICKHOUSE_AGGREGATING_ENGINE_NAMES
        ),
    )
