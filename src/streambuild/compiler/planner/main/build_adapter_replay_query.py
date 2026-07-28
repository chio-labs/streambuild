"""Build a compiler-analyzed query for adapter replay."""

from streambuild.adapter.models import AdapterPhysicalRelationMapping, AdapterReplayQuery
from streambuild.compiler.planner.exceptions import DeploymentPlanError
from streambuild.compiler.sql_analysis.exceptions import SqlAnalysisError
from streambuild.compiler.sql_analysis.main.rewrite_query import rewrite_query
from streambuild.compiler.sql_analysis.models import SqlQueryRewriteResult, SqlRelationRewrite


def build_adapter_replay_query(
    *,
    query: str,
    source_relation_name: str,
    database: str,
    physical_relation_mappings: tuple[AdapterPhysicalRelationMapping, ...],
) -> AdapterReplayQuery:
    """Rewrite side references physically and classify aggregate semantics."""

    try:
        result: SqlQueryRewriteResult = rewrite_query(
            sql=query,
            dialect="clickhouse",
            relation_rewrites=tuple(
                SqlRelationRewrite(
                    source_name=mapping.logical_name,
                    target_relation=f"{database}.{mapping.physical_name}",
                )
                for mapping in physical_relation_mappings
                if mapping.logical_name != source_relation_name
            ),
        )
    except SqlAnalysisError as error:
        raise DeploymentPlanError(str(error)) from None
    return AdapterReplayQuery(
        query=result.query,
        physical_relation_mappings=physical_relation_mappings,
        aggregate_semantics=result.has_aggregate_semantics,
    )
