"""Landing-step compile helpers."""

from streambuild.compiler.compile._helpers.naming import (
    kafka_table_name,
    landing_mv_name,
    raw_table_name,
)
from streambuild.compiler.compile.constants import RAW_LANDING_COLUMNS
from streambuild.compiler.compile.models import CompiledExternalSource, CompiledManagedSource
from streambuild.compiler.shared.constants import (
    DESIRED_OBJECT_TYPE_KAFKA_TABLE,
    DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
    DESIRED_OBJECT_TYPE_TABLE,
    REPLAY_OFFSET_COLUMN_NAME,
    REPLAY_PARTITION_COLUMN_NAME,
)
from streambuild.compiler.shared.models import (
    Column,
    DesiredKafkaTable,
    DesiredMaterializedView,
    DesiredTable,
    KafkaTableSpec,
    MaterializedViewSpec,
    ObjectKey,
    TableSpec,
    TableStorage,
)
from streambuild.compiler.shared.models import (
    KafkaSettings as ComparableKafkaSettings,
)
from streambuild.spec.models.pipeline import Pipeline
from streambuild.spec.models.steps import ExternalTableSourceStep, KafkaLandingStep, KafkaSettings


def compile_kafka_landing(pipeline: Pipeline) -> CompiledManagedSource:
    """Compile desired landing objects for a pipeline source."""

    if not isinstance(pipeline.source, KafkaLandingStep):
        raise RuntimeError("Managed landing compilation requires a KafkaLandingStep source")
    source: KafkaLandingStep = pipeline.source
    resolved_kafka_settings: ComparableKafkaSettings = normalize_kafka_settings(
        pipeline_name=pipeline.name,
        source_name=source.name,
        kafka_settings=source.kafka,
    )
    kafka_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_KAFKA_TABLE,
        name=kafka_table_name(source.name),
    )
    raw_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_TABLE,
        name=raw_table_name(source.name),
    )
    mv_key: ObjectKey = ObjectKey(
        database=None,
        object_type=DESIRED_OBJECT_TYPE_MATERIALIZED_VIEW,
        name=landing_mv_name(source.name),
    )
    raw_table_name_value: str = raw_table_name(source.name)
    return CompiledManagedSource(
        kafka_table=DesiredKafkaTable(
            key=kafka_key,
            deps=(),
            spec=KafkaTableSpec(
                columns=kafka_landing_columns(resolved_kafka_settings.format),
                kafka=resolved_kafka_settings,
            ),
        ),
        raw_table=DesiredTable(
            key=raw_key,
            deps=(),
            spec=TableSpec(
                columns=raw_landing_columns(),
                storage=TableStorage(
                    engine="MergeTree()",
                    order_by=(REPLAY_PARTITION_COLUMN_NAME, REPLAY_OFFSET_COLUMN_NAME),
                ),
            ),
        ),
        materialized_view=DesiredMaterializedView(
            key=mv_key,
            deps=(kafka_key, raw_key),
            spec=MaterializedViewSpec(
                source_table_name=kafka_table_name(source.name),
                target_table_name=raw_table_name_value,
                query=build_landing_query(source.name),
            ),
        ),
    )


def compile_external_source(pipeline: Pipeline) -> CompiledExternalSource:
    """Compile adopted source metadata for an external replay-driving table."""

    if not isinstance(pipeline.source, ExternalTableSourceStep):
        raise RuntimeError("External source compilation requires an ExternalTableSourceStep source")
    source: ExternalTableSourceStep = pipeline.source
    return CompiledExternalSource(
        source=source,
        source_key=ObjectKey(
            database=None,
            object_type=DESIRED_OBJECT_TYPE_TABLE,
            name=source.table_name,
        ),
    )


def raw_landing_columns() -> tuple[Column, ...]:
    """Return the standard raw-landing column set."""

    return RAW_LANDING_COLUMNS


def kafka_landing_columns(table_format: str) -> tuple[Column, ...]:
    """Return the Kafka source-table columns for a supported source format."""

    if table_format == "JSONAsString":
        return (Column(name="message", type="String"),)

    raise ValueError(
        f"Kafka landing currently supports only the 'JSONAsString' format; got '{table_format}'"
    )


def normalize_kafka_settings(
    *,
    pipeline_name: str,
    source_name: str,
    kafka_settings: KafkaSettings,
) -> ComparableKafkaSettings:
    """Normalize authored Kafka settings into a desired Kafka table contract."""

    validate_kafka_setting_overrides(kafka_settings)
    resolved_consumer_group: str = kafka_settings.consumer_group or default_consumer_group(
        pipeline_name=pipeline_name,
        source_name=source_name,
    )
    return ComparableKafkaSettings(
        broker_list=kafka_settings.broker_list,
        topic=kafka_settings.topic,
        consumer_group=resolved_consumer_group,
        format=kafka_settings.format,
        settings=kafka_settings.settings,
    )


def validate_kafka_setting_overrides(kafka_settings: KafkaSettings) -> None:
    """Reject escape-hatch settings that overlap with typed Kafka settings."""

    if kafka_settings.settings is None:
        return

    overlapping_keys: tuple[str, ...] = tuple(
        sorted(
            key
            for key in kafka_settings.settings
            if key
            in {
                "kafka_broker_list",
                "kafka_topic_list",
                "kafka_group_name",
                "kafka_format",
            }
        )
    )
    if overlapping_keys:
        raise ValueError(
            "Kafka settings override map cannot redefine typed Kafka settings: "
            + ", ".join(overlapping_keys)
        )


def default_consumer_group(*, pipeline_name: str, source_name: str) -> str:
    """Return the deterministic default consumer group for a landing step."""

    return f"streambuild_{pipeline_name}_{source_name}"


def build_landing_query(logical_name: str) -> str:
    """Build the standard raw landing query."""

    kafka_source_table_name: str = kafka_table_name(logical_name)
    return (
        "SELECT\n"
        "    _key AS kafka_key,\n"
        "    message AS kafka_value,\n"
        "    _topic AS kafka_topic,\n"
        "    _partition AS kafka_partition,\n"
        "    _offset AS kafka_offset,\n"
        "    _timestamp AS kafka_timestamp,\n"
        "    _partition AS _replay_partition,\n"
        "    _offset AS _replay_offset,\n"
        "    _timestamp AS _replay_timestamp,\n"
        "    '' AS kafka_headers,\n"
        "    now64(3) AS kafka_landed_at,\n"
        "    now64(3) AS _replay_landed_at\n"
        f"FROM {kafka_source_table_name}"
    )
