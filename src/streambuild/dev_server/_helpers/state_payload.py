"""Assemble the /api/state live overlay from warehouse reads."""

from __future__ import annotations

import datetime
import json
from hashlib import sha256

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import (
    AdapterDirectFingerprintRecord,
    AdapterDirectFingerprintSnapshot,
    CatalogSnapshot,
)
from streambuild.adapter.types import AdapterOptionalStateStatus
from streambuild.compiler.compile.main.build_model_storage_identity import (
    build_model_storage_identity,
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
