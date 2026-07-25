from streambuild.compiler.shared.models import (
    DesiredMaterializedView,
    MaterializedViewSpec,
    ObjectKey,
)


def build_materialized_view(query: str) -> DesiredMaterializedView:
    return DesiredMaterializedView(
        key=ObjectKey(
            database=None,
            object_type="materialized_view",
            name="mv__orders_enriched",
        ),
        deps=(),
        spec=MaterializedViewSpec(
            source_table_name="raw__orders",
            target_table_name="tbl__orders_enriched",
            query=query,
        ),
    )
