"""Realize one logical source as ClickHouse resources."""

from streambuild.adapter.constants import MANAGED_SOURCE_KIND_KAFKA
from streambuild.adapter.exceptions import AdapterConfigurationError
from streambuild.adapter.models import (
    AdapterAdoptedSourceRealizationRequest,
    AdapterColumn,
    AdapterManagedSource,
    AdapterManagedSourceRealizationRequest,
    AdapterMaterializedView,
    AdapterSourceRealization,
    AdapterTable,
)
from streambuild.adapters.clickhouse.constants import (
    CLICKHOUSE_FRAMEWORK_KAFKA_SETTING_KEYS,
    CLICKHOUSE_KAFKA_TABLE_NAME_PREFIX,
    CLICKHOUSE_MATERIALIZED_VIEW_NAME_PREFIX,
    CLICKHOUSE_RAW_TABLE_NAME_PREFIX,
    CLICKHOUSE_SUPPORTED_KAFKA_FORMAT,
)

_REPLAY_PARTITION_COLUMN_NAME: str = "_replay_partition"
_REPLAY_OFFSET_COLUMN_NAME: str = "_replay_offset"


def realize_clickhouse_source(
    *,
    request: AdapterManagedSourceRealizationRequest | AdapterAdoptedSourceRealizationRequest,
) -> AdapterSourceRealization:
    """Realize one logical source using ClickHouse resource conventions."""

    if isinstance(request, AdapterAdoptedSourceRealizationRequest):
        return AdapterSourceRealization(relation_name=request.relation_name, resources=())
    _validate_managed_source_request(request)
    kafka_name: str = f"{CLICKHOUSE_KAFKA_TABLE_NAME_PREFIX}{request.logical_name}"
    raw_name: str = f"{CLICKHOUSE_RAW_TABLE_NAME_PREFIX}{request.logical_name}"
    consumer_group: str = request.consumer_group or (
        f"streambuild_{request.logical_name}_{request.logical_name}"
    )
    return AdapterSourceRealization(
        relation_name=raw_name,
        resources=(
            AdapterManagedSource(
                source_kind=request.source_kind,
                name=kafka_name,
                columns=(AdapterColumn(name="message", type="String"),),
                broker_list=request.broker_list,
                topic=request.topic,
                consumer_group=consumer_group,
                format=request.format,
                settings=request.settings,
                naming_macro_fingerprint=request.naming_macro_fingerprint,
            ),
            AdapterTable(
                name=raw_name,
                columns=_raw_landing_columns(),
                engine="MergeTree()",
                order_by=(_REPLAY_PARTITION_COLUMN_NAME, _REPLAY_OFFSET_COLUMN_NAME),
                ttl=request.ttl,
            ),
            AdapterMaterializedView(
                name=f"{CLICKHOUSE_MATERIALIZED_VIEW_NAME_PREFIX}{request.logical_name}",
                source_relation_name=kafka_name,
                target_relation_name=raw_name,
                query=_landing_query(
                    logical_name=request.logical_name,
                    kafka_relation_name=kafka_name,
                ),
                database_template=_landing_query(
                    logical_name=request.logical_name,
                    kafka_relation_name=kafka_name,
                ),
            ),
        ),
    )


def _validate_managed_source_request(request: AdapterManagedSourceRealizationRequest) -> None:
    if request.source_kind != MANAGED_SOURCE_KIND_KAFKA:
        raise AdapterConfigurationError(
            f"ClickHouse cannot realize managed source kind '{request.source_kind}'"
        )
    if request.format != CLICKHOUSE_SUPPORTED_KAFKA_FORMAT:
        raise AdapterConfigurationError(
            "ClickHouse Kafka landing currently supports only the "
            f"'{CLICKHOUSE_SUPPORTED_KAFKA_FORMAT}' format; got '{request.format}'"
        )
    overlapping_keys: tuple[str, ...] = tuple(
        sorted(
            key
            for key, _value in request.settings
            if key in CLICKHOUSE_FRAMEWORK_KAFKA_SETTING_KEYS
        )
    )
    if overlapping_keys:
        raise AdapterConfigurationError(
            "Kafka settings override map cannot redefine typed Kafka settings: "
            + ", ".join(overlapping_keys)
        )


def _raw_landing_columns() -> tuple[AdapterColumn, ...]:
    return (
        AdapterColumn(name="kafka_key", type="String"),
        AdapterColumn(name="kafka_value", type="String"),
        AdapterColumn(name="kafka_topic", type="String"),
        AdapterColumn(name="kafka_partition", type="Int32"),
        AdapterColumn(name="kafka_offset", type="Int64"),
        AdapterColumn(name="kafka_timestamp", type="Nullable(DateTime64(3))"),
        AdapterColumn(name=_REPLAY_PARTITION_COLUMN_NAME, type="Int32"),
        AdapterColumn(name=_REPLAY_OFFSET_COLUMN_NAME, type="Int64"),
        AdapterColumn(name="_replay_timestamp", type="Nullable(DateTime64(3))"),
        AdapterColumn(name="kafka_header_keys", type="Array(String)"),
        AdapterColumn(name="kafka_header_values", type="Array(String)"),
        AdapterColumn(name="kafka_landed_at", type="DateTime64(3)"),
        AdapterColumn(name="_replay_landed_at", type="DateTime64(3)"),
    )


def _landing_query(*, logical_name: str, kafka_relation_name: str) -> str:
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
        "    _headers.name AS kafka_header_keys,\n"
        "    _headers.value AS kafka_header_values,\n"
        "    now64(3) AS kafka_landed_at,\n"
        "    now64(3) AS _replay_landed_at\n"
        f"FROM {kafka_relation_name}"
    )
