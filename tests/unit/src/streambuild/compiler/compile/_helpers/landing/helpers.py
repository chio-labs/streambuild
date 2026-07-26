from streambuild.spec.models import KafkaLandingStep, KafkaSettings, Pipeline


def build_pipeline(
    source_format: str = "JSONAsString",
    consumer_group: str | None = None,
    settings: dict[str, str] | None = None,
) -> Pipeline:
    return Pipeline(
        name="orders",
        source=KafkaLandingStep(
            name="orders",
            kafka=KafkaSettings(
                broker_list="kafka:9092",
                topic="source.orders.created",
                consumer_group=consumer_group,
                format=source_format,
                settings=settings,
            ),
        ),
        transforms=[],
    )
