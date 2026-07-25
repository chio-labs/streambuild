from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualTable,
)
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_KAFKA_TABLE,
    DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
    DESIRED_OBJECT_TYPE_TABLE,
)
from streambuild.compiler.shared.models import (
    Column,
    KafkaSettings,
    KafkaTableSpec,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)


def build_actual_objects() -> tuple[ActualKafkaTable | ActualTable | ActualMaterializedView, ...]:
    kafka_spec: KafkaTableSpec = KafkaTableSpec(
        columns=(Column(name="message", type="String"),),
        kafka=KafkaSettings(
            broker_list="kafka:9092",
            topic="source.orders.created",
            consumer_group="streambuild_orders_orders",
            format="JSONAsString",
            settings={"kafka_num_consumers": "4"},
        ),
    )
    table_spec: TableSpec = TableSpec(
        columns=(
            Column(name="order_id", type="String"),
            Column(name="updated_at", type="DateTime64(3)"),
        ),
        storage=TableStorage(
            engine="ReplacingMergeTree(updated_at)",
            order_by=("order_id", "updated_at"),
            partition_by="toYYYYMM(updated_at)",
            ttl="toDateTime(updated_at) + INTERVAL 30 DAY",
            settings={"index_granularity": "8192"},
        ),
    )
    materialized_view_spec: MaterializedViewSpec = MaterializedViewSpec(
        source_table_name="raw__orders",
        target_table_name="tbl__orders_enriched",
        query="SELECT * FROM raw__orders",
    )
    return (
        ActualTable(
            key=ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_TABLE,
                name="tbl__orders_enriched",
            ),
            spec=table_spec,
        ),
        ActualMaterializedView(
            key=ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
                name="mv__orders_enriched",
            ),
            spec=materialized_view_spec,
        ),
        ActualKafkaTable(
            key=ObjectKey(
                database=None,
                object_type=DESIRED_OBJECT_TYPE_KAFKA_TABLE,
                name="kafka__orders",
            ),
            spec=kafka_spec,
        ),
    )
