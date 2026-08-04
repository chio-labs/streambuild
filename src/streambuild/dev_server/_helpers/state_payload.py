"""Assemble the /api/state live overlay from warehouse reads."""

from __future__ import annotations

import datetime

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterTable,
    CatalogRelation,
    CatalogSnapshot,
)
from streambuild.compiler.compile.models import (
    CompiledModel,
    CompiledTableModel,
)
from streambuild.compiler.discovery.constants import SECONDS_BY_DURATION_UNIT
from streambuild.compiler.discovery.models import SourceFreshnessPolicy
from streambuild.compiler.pipeline.models import CompileAnalysis
from streambuild.dev_server._helpers.state_queries import (
    build_extents_query,
    build_partitions_query,
    build_parts_query,
    build_relation_stats_query,
    build_throughput_query,
    choose_throughput_window,
)
from streambuild.dev_server.types import Freshness

_LANDED_AT_COLUMN: str = "_replay_landed_at"


def build_state_payload(
    *,
    analysis: CompileAnalysis,
    connection: AdapterConnection,
    database: str,
) -> dict[str, object]:
    """Read the warehouse once and assemble the complete live overlay."""

    captured_at: str = connection.capture_warehouse_timestamp()
    catalog: CatalogSnapshot = connection.load_catalog(database)
    stats: dict[str, dict[str, int]] = _relation_stats(connection=connection, database=database)
    lineage_relations: tuple[str, ...] = _lineage_relation_names(catalog)
    extents: dict[str, dict[str, object]] = _extents(
        connection=connection, database=database, relation_names=lineage_relations
    )
    return {
        "capturedAt": captured_at,
        "models": _model_states(
            analysis=analysis,
            catalog=catalog,
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
    catalog: CatalogSnapshot,
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
            analysis=analysis, model=model, catalog=catalog, relation_name=relation_name
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
) -> dict[str, dict[str, object]]:
    states: dict[str, dict[str, object]] = {}
    for source in analysis.compiled_project.sources:
        relation_name: str = analysis.realized_project.relation_name_by_logical_key[source.key]
        extent: dict[str, object] = extents.get(relation_name, {})
        newest: str | None = _optional_str(extent.get("newest"))
        age: float | None = _age_seconds(newest=newest, captured_at=captured_at)
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
            "lagSeconds": age,
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
) -> list[dict[str, object]] | None:
    if not has_lineage:
        return None
    query: str = build_partitions_query(database=database, relation_name=relation_name)
    partitions: list[dict[str, object]] = []
    for row in connection.query(query).named_rows():
        partitions.append(
            {
                "partition": int(str(row["partition"])),
                "maxOffset": int(str(row["max_offset"])),
                "newestEventAt": str(row["newest"]),
            }
        )
    return partitions


def _drift_reasons(
    *,
    analysis: CompileAnalysis,
    model: CompiledModel,
    catalog: CatalogSnapshot,
    relation_name: str,
) -> tuple[str, ...]:
    if not isinstance(model, CompiledTableModel):
        return ()
    live: CatalogRelation | None = catalog.relation(relation_name)
    if live is None:
        return ()
    compiled_table: AdapterTable | None = _compiled_table(analysis=analysis, model=model)
    if compiled_table is None:
        return ()
    reasons: list[str] = []
    if _normalized_engine(live.engine) != _normalized_engine(compiled_table.engine):
        reasons.append("engine")
    if tuple(live.order_by) != tuple(compiled_table.order_by):
        reasons.append("order_by")
    if live.partition_by != compiled_table.partition_by:
        reasons.append("partition_by")
    if live.ttl != compiled_table.ttl:
        reasons.append("ttl")
    live_columns: tuple[tuple[str, str], ...] = tuple(
        (column.name, column.type) for column in live.columns
    )
    compiled_columns: tuple[tuple[str, str], ...] = tuple(
        (column.name, column.type) for column in compiled_table.columns
    )
    if live_columns != compiled_columns:
        reasons.append("columns")
    return tuple(reasons)


def _compiled_table(*, analysis: CompileAnalysis, model: CompiledModel) -> AdapterTable | None:
    for resource in analysis.realized_project.resources_by_logical_key.get(model.key, ()):
        if isinstance(resource, AdapterTable):
            return resource
    return None


def _normalized_engine(engine: str) -> str:
    return engine.replace("()", "").strip()


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
