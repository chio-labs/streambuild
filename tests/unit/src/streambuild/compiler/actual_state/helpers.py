from streambuild.clickhouse.inspect.models import RootDeploymentInspection
from streambuild.compiler.actual_state.models import (
    ActualKafkaTable,
    ActualMaterializedView,
    ActualStateInspection,
    ActualTable,
)
from streambuild.compiler.compile.constants import (
    DESIRED_OBJECT_TYPE_KAFKA_TABLE,
    DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
    DESIRED_OBJECT_TYPE_TABLE,
)
from streambuild.compiler.compile.models import (
    Column,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredState,
    DesiredTable,
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


def build_projection_characterization_inputs() -> tuple[DesiredState, ActualStateInspection]:
    kafka_key: ObjectKey = ObjectKey(database=None, object_type="kafka_table", name="kafka__orders")
    raw_key: ObjectKey = ObjectKey(database=None, object_type="table", name="raw__orders")
    landing_mv_key: ObjectKey = ObjectKey(
        database=None,
        object_type="materialized_view",
        name="mv__orders_landing",
    )
    transform_key: ObjectKey = ObjectKey(
        database=None, object_type="table", name="tbl__orders_enriched"
    )
    raw_storage: TableStorage = TableStorage(
        engine="MergeTree()",
        order_by=("order_id",),
        partition_by="toYYYYMM(created_at)",
        ttl="created_at + INTERVAL 30 DAY",
        settings={"index_granularity": "8192"},
    )
    desired_state: DesiredState = DesiredState(
        objects=(
            DesiredKafkaTable(
                key=kafka_key,
                deps=(),
                spec=KafkaTableSpec(
                    columns=(Column(name="message", type="String"),),
                    kafka=KafkaSettings(
                        broker_list="kafka:9092",
                        topic="source.orders.created",
                        consumer_group="streambuild_orders_orders",
                        format="JSONAsString",
                        settings={"kafka_num_consumers": "4"},
                    ),
                ),
            ),
            DesiredTable(
                key=raw_key,
                deps=(kafka_key,),
                spec=TableSpec(
                    columns=(Column(name="order_id", type="String"),),
                    storage=raw_storage,
                ),
            ),
            DesiredMaterializedView(
                key=landing_mv_key,
                deps=(kafka_key, raw_key),
                spec=MaterializedViewSpec(
                    source_table_name="kafka__orders",
                    target_table_name="raw__orders",
                    query="SELECT message AS order_id FROM kafka__orders",
                ),
            ),
            DesiredTable(
                key=transform_key,
                deps=(raw_key,),
                spec=TableSpec(
                    columns=(Column(name="order_id", type="String"),),
                    storage=raw_storage,
                ),
            ),
        ),
        replay_anchor_keys=frozenset({raw_key}),
        mutable_ref_warning_keys=frozenset(),
    )
    inspection: ActualStateInspection = ActualStateInspection(
        existing_names=frozenset({kafka_key.name, raw_key.name, landing_mv_key.name}),
        active_deployment_by_root={
            transform_key: RootDeploymentInspection(
                root_key=transform_key,
                state_kind="active_view_present",
                active_deployment_id="dep_a",
            )
        },
        object_state_by_deployment_and_key={},
        latest_object_state_by_key={},
        active_physical_names_by_logical_name={transform_key.name: "tbl__orders_enriched__dep_a"},
        active_table_specs_by_name={
            "tbl__orders_enriched__dep_a": TableSpec(
                columns=(Column(name="order_id", type="String"),),
                storage=TableStorage(
                    engine="MergeTree()",
                    order_by=("order_id",),
                    ttl=None,
                    settings=None,
                ),
            )
        },
    )
    return desired_state, inspection
