from streambuild.compiler.compile.models import (
    Column,
    DesiredKafkaTable,
    KafkaSettings,
    KafkaTableSpec,
    ObjectKey,
)


def build_kafka_table(extra_settings: dict[str, str] | None = None) -> DesiredKafkaTable:
    return DesiredKafkaTable(
        key=ObjectKey(
            database=None,
            object_type="kafka_table",
            name="kafka__orders",
        ),
        deps=(),
        spec=KafkaTableSpec(
            columns=(Column(name="message", type="String"),),
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
                consumer_group="streambuild_orders_orders",
                format="JSONAsString",
                settings=extra_settings,
            ),
        ),
    )
