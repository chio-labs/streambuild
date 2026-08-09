"""Assemble the /api/state and /api/topics live overlays from warehouse reads."""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import cast

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterDirectFingerprintRecord,
    AdapterDirectFingerprintSnapshot,
    AdapterManagedSource,
    CatalogSnapshot,
    InspectedManagedTableState,
)
from streambuild.adapter.types import AdapterOptionalStateStatus
from streambuild.compiler.compile.main.build_model_storage_identity import (
    build_model_storage_identity,
)
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledSource,
    CompiledTableModel,
)
from streambuild.compiler.discovery.constants import SECONDS_BY_DURATION_UNIT
from streambuild.compiler.discovery.models import (
    KafkaLandingStep,
    KafkaSettings,
    SourceFreshnessPolicy,
)
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server.classes.kafka_lag_reader import KafkaLagReader
from streambuild.dev_server.classes.kafka_topic_reader import KafkaTopicReader
from streambuild.dev_server.constants import THROUGHPUT_WINDOW_LADDER
from streambuild.dev_server.models import (
    KafkaLagSnapshot,
    KafkaPartitionLag,
    KafkaTopicInfo,
    KafkaTopicsSnapshot,
)
from streambuild.dev_server.types import Freshness

_LANDED_AT_COLUMN: str = "_replay_landed_at"

_NO_MANAGED_SOURCES_REASON: str = (
    "no managed Kafka sources define broker connections; the dev server has no "
    "credentials to inspect a cluster"
)


@dataclass(frozen=True)
class _ManagedTopicSource:
    """One managed source resolved to its broker connection and raw relation."""

    source_name: str
    relation_name: str
    kafka: KafkaSettings


def build_state_payload(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection,
    database: str,
    kafka_lag_reader: KafkaLagReader | None = None,
) -> dict[str, object]:
    """Read the warehouse once and assemble the complete live overlay."""

    if kafka_lag_reader is not None:
        for source in analysis.compiled_project.sources:
            _kafka_lag(
                analysis=analysis,
                source=source,
                database=database,
                reader=kafka_lag_reader,
            )
    captured_at: str = connection.capture_warehouse_timestamp()
    catalog: CatalogSnapshot = connection.load_catalog(database)
    stats: dict[str, dict[str, int]] = _relation_stats(connection=connection, database=database)
    lineage_relations: tuple[str, ...] = _lineage_relation_names(catalog)
    extents: dict[str, dict[str, object]] = _extents(
        connection=connection, database=database, relation_names=lineage_relations
    )
    baselines: dict[str, AdapterDirectFingerprintRecord] = _fingerprint_baselines(
        analysis=analysis,
        connection=connection,
        database=database,
    )
    return {
        "capturedAt": captured_at,
        "models": _model_states(
            analysis=analysis,
            baselines=baselines,
            stats=stats,
            extents=extents,
            captured_at=captured_at,
        ),
        "sources": _source_states(
            analysis=analysis,
            connection=connection,
            database=database,
            stats=stats,
            extents=extents,
            captured_at=captured_at,
            kafka_lag_reader=kafka_lag_reader,
        ),
    }


def _relation_stats(*, connection: AdapterConnection, database: str) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for row in connection.query(build_relation_stats_query(database=database)).named_rows():
        stats[str(row["name"])] = {
            "rows": int(str(row["total_rows"])),
            "bytes": int(str(row["total_bytes"])),
            "parts": 0,
        }
    for row in connection.query(build_parts_query(database=database)).named_rows():
        entry: dict[str, int] | None = stats.get(str(row["table"]))
        if entry is not None:
            entry["parts"] = int(str(row["parts"]))
    return apply_bound_relation_stats(
        stats=stats,
        bindings=_active_bindings(connection=connection, database=database),
    )


def _active_bindings(
    *, connection: AdapterConnection, database: str
) -> tuple[tuple[str, str], ...]:
    """Logical-to-physical pairs, empty for adapters without stable bindings."""

    if not connection.capabilities.stable_logical_bindings:
        return ()
    inspected: InspectedManagedTableState = connection.inspect_managed_table_state(database)
    return tuple(
        (binding.logical_name, binding.physical_name) for binding in inspected.active_bindings
    )


def apply_bound_relation_stats(
    *, stats: dict[str, dict[str, int]], bindings: tuple[tuple[str, str], ...]
) -> dict[str, dict[str, int]]:
    """Measure a stable logical view by the deployment relation it is bound to."""

    logical_name: str
    physical_name: str
    for logical_name, physical_name in bindings:
        measured: dict[str, int] | None = stats.get(physical_name)
        if measured is not None:
            stats[logical_name] = dict(measured)
    return stats


def _lineage_relation_names(catalog: CatalogSnapshot) -> tuple[str, ...]:
    names: list[str] = []
    for relation in catalog.relations:
        column_names: frozenset[str] = frozenset(column.name for column in relation.columns)
        if _LANDED_AT_COLUMN in column_names:
            names.append(relation.name)
    return tuple(names)


def _extents(
    *,
    connection: AdapterConnection,
    database: str,
    relation_names: tuple[str, ...],
) -> dict[str, dict[str, object]]:
    if not relation_names:
        return {}
    extents: dict[str, dict[str, object]] = {}
    query: str = build_extents_query(database=database, relation_names=relation_names)
    for row in connection.query(query).named_rows():
        extents[str(row["relation"])] = {
            "oldest": str(row["oldest"]),
            "newest": str(row["newest"]),
            "rows": int(str(row["rows"])),
        }
    return extents


def _model_states(
    *,
    analysis: CompileAnalysis,
    baselines: dict[str, AdapterDirectFingerprintRecord],
    stats: dict[str, dict[str, int]],
    extents: dict[str, dict[str, object]],
    captured_at: str,
) -> dict[str, dict[str, object]]:
    policy_by_model: dict[str, SourceFreshnessPolicy | None] = _policies_by_model(analysis)
    states: dict[str, dict[str, object]] = {}
    for model in analysis.compiled_project.models:
        relation_name: str = analysis.realized_project.relation_name_by_logical_key[model.key]
        relation_stats: dict[str, int] = stats.get(relation_name, {})
        extent: dict[str, object] = extents.get(relation_name, {})
        newest: str | None = _optional_str(extent.get("newest"))
        drift_reasons: tuple[str, ...] = _drift_reasons(
            model=model,
            baseline=baselines.get(model.key.name),
        )
        states[model.key.name] = {
            "relationName": relation_name,
            "rows": relation_stats.get("rows"),
            "diskBytes": relation_stats.get("bytes"),
            "parts": relation_stats.get("parts"),
            "oldestRowAt": _optional_str(extent.get("oldest")),
            "newestRowAt": newest,
            "lagSeconds": _age_seconds(newest=newest, captured_at=captured_at),
            "freshness": _freshness(
                newest=newest,
                captured_at=captured_at,
                policy=policy_by_model.get(model.key.name),
            ),
            "drift": bool(drift_reasons),
            "driftReasons": list(drift_reasons),
        }
    return states


def _source_states(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection,
    database: str,
    stats: dict[str, dict[str, int]],
    extents: dict[str, dict[str, object]],
    captured_at: str,
    kafka_lag_reader: KafkaLagReader | None,
) -> dict[str, dict[str, object]]:
    states: dict[str, dict[str, object]] = {}
    for source in analysis.compiled_project.sources:
        relation_name: str = analysis.realized_project.relation_name_by_logical_key[source.key]
        extent: dict[str, object] = extents.get(relation_name, {})
        newest: str | None = _optional_str(extent.get("newest"))
        age: float | None = _age_seconds(newest=newest, captured_at=captured_at)
        kafka_lag: KafkaLagSnapshot | None = _kafka_lag(
            analysis=analysis,
            source=source,
            database=database,
            reader=kafka_lag_reader,
        )
        throughput: dict[str, object] | None = _throughput(
            connection=connection,
            database=database,
            relation_name=relation_name,
            newest_age_seconds=age,
            has_lineage=relation_name in extents,
        )
        states[source.key.name] = {
            "relationName": relation_name,
            "rows": stats.get(relation_name, {}).get("rows"),
            "oldestEventAt": _optional_str(extent.get("oldest")),
            "newestEventAt": newest,
            "lastArrivalSeconds": age,
            "kafkaLagMessages": None if kafka_lag is None else kafka_lag.total_messages,
            "freshness": _freshness(
                newest=newest, captured_at=captured_at, policy=source.source.freshness
            ),
            "throughput": throughput,
            "rowsPerSecond": _rows_per_second(throughput),
            "partitions": _partitions(
                connection=connection,
                database=database,
                relation_name=relation_name,
                has_lineage=relation_name in extents,
                kafka_lag=kafka_lag,
            ),
        }
    return states


def _policies_by_model(
    analysis: CompileAnalysis,
) -> dict[str, SourceFreshnessPolicy | None]:
    policies: dict[str, SourceFreshnessPolicy | None] = {}
    for pipeline in analysis.compiled_project.pipelines:
        source_policy: SourceFreshnessPolicy | None = (
            None if pipeline.source is None else pipeline.source.source.freshness
        )
        for model in pipeline.models:
            policies[model.key.name] = source_policy
    return policies


def _throughput(
    *,
    connection: AdapterConnection,
    database: str,
    relation_name: str,
    newest_age_seconds: float | None,
    has_lineage: bool,
) -> dict[str, object] | None:
    if not has_lineage:
        return None
    window_seconds: int
    bucket_seconds: int
    window_seconds, bucket_seconds = choose_throughput_window(newest_age_seconds=newest_age_seconds)
    query: str = build_throughput_query(
        database=database,
        relation_name=relation_name,
        window_seconds=window_seconds,
        bucket_seconds=bucket_seconds,
    )
    counts_by_bucket: dict[int, int] = {}
    for row in connection.query(query).named_rows():
        counts_by_bucket[int(str(row["bucket"]))] = int(str(row["rows"]))
    buckets: list[int] = _zero_filled_buckets(
        counts_by_bucket=counts_by_bucket,
        window_seconds=window_seconds,
        bucket_seconds=bucket_seconds,
    )
    return {
        "windowSeconds": window_seconds,
        "bucketSeconds": bucket_seconds,
        "buckets": buckets,
    }


def _zero_filled_buckets(
    *,
    counts_by_bucket: dict[int, int],
    window_seconds: int,
    bucket_seconds: int,
) -> list[int]:
    if not counts_by_bucket:
        return [0] * (window_seconds // bucket_seconds)
    newest_bucket: int = max(counts_by_bucket)
    bucket_count: int = window_seconds // bucket_seconds
    start: int = newest_bucket - (bucket_count - 1) * bucket_seconds
    return [
        counts_by_bucket.get(start + index * bucket_seconds, 0) for index in range(bucket_count)
    ]


def _rows_per_second(throughput: dict[str, object] | None) -> float | None:
    if throughput is None:
        return None
    buckets: object = throughput.get("buckets")
    window: object = throughput.get("windowSeconds")
    if not isinstance(buckets, list) or not isinstance(window, int) or window == 0:
        return None
    return round(float(sum(buckets)) / float(window), 3)


def _partitions(
    *,
    connection: AdapterConnection,
    database: str,
    relation_name: str,
    has_lineage: bool,
    kafka_lag: KafkaLagSnapshot | None,
) -> list[dict[str, object]] | None:
    if not has_lineage and kafka_lag is None:
        return None
    lag_by_partition: dict[int, KafkaPartitionLag] = {
        item.partition: item for item in (() if kafka_lag is None else kafka_lag.partitions)
    }
    partitions_by_id: dict[int, dict[str, object]] = {}
    if has_lineage:
        query: str = build_partitions_query(database=database, relation_name=relation_name)
        for row in connection.query(query).named_rows():
            partition: int = int(str(row["partition"]))
            broker_lag: KafkaPartitionLag | None = lag_by_partition.get(partition)
            partitions_by_id[partition] = {
                "partition": partition,
                "maxOffset": int(str(row["max_offset"])),
                "newestEventAt": str(row["newest"]),
                "committedOffset": None if broker_lag is None else broker_lag.committed_offset,
                "endOffset": None if broker_lag is None else broker_lag.end_offset,
                "kafkaLagMessages": None if broker_lag is None else broker_lag.lag_messages,
            }
    for partition, broker_lag in lag_by_partition.items():
        partitions_by_id.setdefault(
            partition,
            {
                "partition": partition,
                "maxOffset": None,
                "newestEventAt": None,
                "committedOffset": broker_lag.committed_offset,
                "endOffset": broker_lag.end_offset,
                "kafkaLagMessages": broker_lag.lag_messages,
            },
        )
    return [partitions_by_id[partition] for partition in sorted(partitions_by_id)]


def _kafka_lag(
    *,
    analysis: CompileAnalysis,
    source: CompiledSource,
    database: str,
    reader: KafkaLagReader | None,
) -> KafkaLagSnapshot | None:
    if not isinstance(source.source, KafkaLandingStep) or reader is None:
        return None
    managed_source: AdapterManagedSource | None = next(
        (
            resource
            for resource in analysis.realized_project.resources_by_logical_key.get(source.key, ())
            if isinstance(resource, AdapterManagedSource)
        ),
        None,
    )
    if managed_source is None:
        return None
    kafka: KafkaSettings = replace(
        source.source.kafka,
        broker_list=managed_source.broker_list,
        topic=managed_source.topic,
        consumer_group=managed_source.consumer_group,
        format=managed_source.format,
        settings=dict(managed_source.settings) or None,
    )
    return reader.read(kafka=kafka, database=database)


def _drift_reasons(
    *,
    model: CompiledModel,
    baseline: AdapterDirectFingerprintRecord | None,
) -> tuple[str, ...]:
    """Compare compiled identity against the last applied direct baseline."""

    if not isinstance(model, CompiledTableModel) or baseline is None:
        return ()
    reasons: list[str] = []
    if sha256(model.query.encode()).hexdigest() != baseline.definition_hash:
        reasons.append("query")
    baseline_storage: object = _baseline_storage(baseline)
    if baseline_storage != build_model_storage_identity(model):
        reasons.append("storage")
    return tuple(reasons)


def _fingerprint_baselines(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection,
    database: str,
) -> dict[str, AdapterDirectFingerprintRecord]:
    identities: tuple[str, ...] = tuple(
        f"{database}.{model.key.name}" for model in analysis.compiled_project.models
    )
    snapshot: AdapterDirectFingerprintSnapshot = connection.load_direct_fingerprints(
        database=database,
        logical_model_identities=identities,
    )
    if snapshot.status != AdapterOptionalStateStatus.AVAILABLE:
        return {}
    prefix: str = f"{database}."
    return {
        record.logical_model_identity.removeprefix(prefix): record for record in snapshot.baselines
    }


def _baseline_storage(baseline: AdapterDirectFingerprintRecord) -> object:
    try:
        metadata: object = json.loads(baseline.identity_metadata)
    except (TypeError, ValueError):
        return None
    if not isinstance(metadata, dict):
        return None
    return metadata.get("storage")


def _freshness(
    *,
    newest: str | None,
    captured_at: str,
    policy: SourceFreshnessPolicy | None,
) -> str | None:
    if policy is None:
        return None
    age: float | None = _age_seconds(newest=newest, captured_at=captured_at)
    if age is None:
        return str(Freshness.STALLED)
    error_after: float | None = _policy_seconds(policy.error_after)
    if error_after is not None and age > error_after:
        return str(Freshness.STALLED)
    warn_after: float | None = _policy_seconds(policy.warn_after)
    if warn_after is not None and age > warn_after:
        return str(Freshness.LAGGING)
    return str(Freshness.FRESH)


def _policy_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    return float(value[:-1]) * SECONDS_BY_DURATION_UNIT[value[-1]]


def _age_seconds(*, newest: str | None, captured_at: str) -> float | None:
    if newest is None:
        return None
    newest_at: datetime.datetime | None = _parse_warehouse_timestamp(newest)
    now_at: datetime.datetime | None = _parse_warehouse_timestamp(captured_at)
    if newest_at is None or now_at is None:
        return None
    return round((now_at - newest_at).total_seconds(), 3)


def _parse_warehouse_timestamp(value: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError:
        return None


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def build_relation_stats_query(*, database: str) -> str:
    """Approximate rows and bytes for every relation in one scan of system.tables."""

    return (
        "SELECT name, coalesce(total_rows, 0) AS total_rows, "
        "coalesce(total_bytes, 0) AS total_bytes "
        f"FROM system.tables WHERE database = '{database}'"
    )


def build_parts_query(*, database: str) -> str:
    """Active part counts per relation in one scan of system.parts."""

    return (
        "SELECT table, count() AS parts "
        f"FROM system.parts WHERE database = '{database}' AND active GROUP BY table"
    )


def build_extents_query(*, database: str, relation_names: tuple[str, ...]) -> str:
    """Oldest and newest landed event per lineage-bearing relation, batched."""

    selects: list[str] = [
        (
            f"SELECT '{name}' AS relation, "
            "toString(min(_replay_landed_at)) AS oldest, "
            "toString(max(_replay_landed_at)) AS newest, "
            "count() AS rows "
            f"FROM `{database}`.`{name}` HAVING count() > 0"
        )
        for name in relation_names
    ]
    return " UNION ALL ".join(selects)


def build_throughput_query(
    *,
    database: str,
    relation_name: str,
    window_seconds: int,
    bucket_seconds: int,
) -> str:
    """Landed-event counts per bucket over one window of a lineage-bearing relation."""

    return (
        "SELECT toUnixTimestamp(toStartOfInterval("
        f"_replay_landed_at, INTERVAL {bucket_seconds} SECOND)) AS bucket, "
        "count() AS rows "
        f"FROM `{database}`.`{relation_name}` "
        f"WHERE _replay_landed_at >= now64(3) - INTERVAL {window_seconds} SECOND "
        "GROUP BY bucket ORDER BY bucket"
    )


def build_partitions_query(*, database: str, relation_name: str) -> str:
    """Per-partition landed offsets for one managed raw relation."""

    return (
        "SELECT _replay_partition AS partition, "
        "max(_replay_offset) AS max_offset, "
        "toString(max(_replay_landed_at)) AS newest "
        f"FROM `{database}`.`{relation_name}` GROUP BY partition ORDER BY partition"
    )


def choose_throughput_window(*, newest_age_seconds: float | None) -> tuple[int, int]:
    """Pick the smallest ladder rung whose window still contains the newest event."""

    if newest_age_seconds is None:
        return THROUGHPUT_WINDOW_LADDER[-1]
    for window_seconds, bucket_seconds in THROUGHPUT_WINDOW_LADDER:
        if newest_age_seconds < window_seconds:
            return (window_seconds, bucket_seconds)
    return THROUGHPUT_WINDOW_LADDER[-1]


def build_topics_payload(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection | None,
    database: str | None,
    topic_reader: KafkaTopicReader,
    kafka_lag_reader: KafkaLagReader,
) -> dict[str, object]:
    """Merge broker topic inventories with managed-source lag and retained stats."""

    managed: tuple[_ManagedTopicSource, ...] = _managed_topic_sources(analysis)
    if not managed:
        return {
            "available": False,
            "reason": _NO_MANAGED_SOURCES_REASON,
            "pendingBrokers": [],
            "topics": [],
        }
    snapshots: dict[str, KafkaTopicsSnapshot | None] = {}
    for entry in managed:
        if entry.kafka.broker_list not in snapshots:
            snapshots[entry.kafka.broker_list] = topic_reader.read(kafka=entry.kafka)
    stats: dict[str, dict[str, int]] = _retained_stats(connection=connection, database=database)
    topics: dict[str, dict[str, object]] = {}
    for broker_list, snapshot in snapshots.items():
        for topic in () if snapshot is None else snapshot.topics:
            topics[topic.name] = _broker_topic_item(topic=topic, broker_list=broker_list)
    for entry in managed:
        item: dict[str, object] = topics.setdefault(
            entry.kafka.topic,
            {
                "name": entry.kafka.topic,
                "brokerList": entry.kafka.broker_list,
                "partitions": None,
                "replicationFactor": None,
                "internal": False,
                "sources": [],
                "lagMessages": None,
                "retainedRows": None,
                "retainedBytes": None,
            },
        )
        sources: list[dict[str, object]] = cast("list[dict[str, object]]", item["sources"])
        sources.append({"name": entry.source_name, "relationName": entry.relation_name})
        lag: KafkaLagSnapshot | None = kafka_lag_reader.read(
            kafka=entry.kafka, database=database or ""
        )
        item["lagMessages"] = None if lag is None else lag.total_messages
        relation_stats: dict[str, int] | None = stats.get(entry.relation_name)
        item["retainedRows"] = None if relation_stats is None else relation_stats["rows"]
        item["retainedBytes"] = None if relation_stats is None else relation_stats["bytes"]
    return {
        "available": True,
        "reason": None,
        "pendingBrokers": sorted(
            broker_list for broker_list, snapshot in snapshots.items() if snapshot is None
        ),
        "topics": [topics[name] for name in sorted(topics)],
    }


def _broker_topic_item(*, topic: KafkaTopicInfo, broker_list: str) -> dict[str, object]:
    return {
        "name": topic.name,
        "brokerList": broker_list,
        "partitions": topic.partition_count,
        "replicationFactor": topic.replication_factor,
        "internal": topic.internal,
        "sources": [],
        "lagMessages": None,
        "retainedRows": None,
        "retainedBytes": None,
    }


def _managed_topic_sources(analysis: CompileAnalysis) -> tuple[_ManagedTopicSource, ...]:
    entries: list[_ManagedTopicSource] = []
    for source in analysis.compiled_project.sources:
        if not isinstance(source.source, KafkaLandingStep):
            continue
        managed_source: AdapterManagedSource | None = next(
            (
                resource
                for resource in analysis.realized_project.resources_by_logical_key.get(
                    source.key, ()
                )
                if isinstance(resource, AdapterManagedSource)
            ),
            None,
        )
        if managed_source is None:
            continue
        entries.append(
            _ManagedTopicSource(
                source_name=source.key.name,
                relation_name=analysis.realized_project.relation_name_by_logical_key[source.key],
                kafka=replace(
                    source.source.kafka,
                    broker_list=managed_source.broker_list,
                    topic=managed_source.topic,
                    consumer_group=managed_source.consumer_group,
                    format=managed_source.format,
                    settings=dict(managed_source.settings) or None,
                ),
            )
        )
    return tuple(entries)


def _retained_stats(
    *, connection: AdapterConnection | None, database: str | None
) -> dict[str, dict[str, int]]:
    if connection is None or database is None:
        return {}
    stats: dict[str, dict[str, int]] = {}
    for row in connection.query(build_relation_stats_query(database=database)).named_rows():
        stats[str(row["name"])] = {
            "rows": int(str(row["total_rows"])),
            "bytes": int(str(row["total_bytes"])),
        }
    return stats
