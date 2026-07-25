from streambuild.compiler.shared.models import (
    Column,
    DesiredTable,
    ObjectKey,
    TableSpec,
    TableStorage,
)


def build_table(
    include_partition_by: bool,
    include_ttl: bool,
    include_settings: bool,
) -> DesiredTable:
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
                partition_by=("toYYYYMM(_replay_landed_at)" if include_partition_by else None),
                ttl=("toDateTime(_replay_landed_at) + INTERVAL 30 DAY" if include_ttl else None),
                settings={"index_granularity": "8192", "allow_nullable_key": "1"}
                if include_settings
                else None,
            ),
        ),
    )
