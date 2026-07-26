from streambuild.compiler.shared.models import (
    Column,
    DesiredTable,
    ObjectKey,
    TableSpec,
    TableStorage,
)


def build_table(
    *,
    partition_by: str | None,
    ttl: str | None,
    settings: dict[str, str] | None,
) -> DesiredTable:
    """Build the desired table a render test case describes."""

    return DesiredTable(
        key=ObjectKey(
            database=None,
            object_type="table",
            name="tbl__orders_enriched",
        ),
        deps=(),
        spec=TableSpec(
            columns=(
                Column(name="order_id", type="String"),
                Column(name="_replay_landed_at", type="DateTime64(3)", default="now64(3)"),
            ),
            storage=TableStorage(
                engine="ReplacingMergeTree(_replay_landed_at)",
                order_by=("order_id", "_replay_landed_at"),
                partition_by=partition_by,
                ttl=ttl,
                settings=settings,
            ),
        ),
    )
