"""Render normalized retention policies into adapter storage expressions."""

from __future__ import annotations

from collections.abc import Mapping

from streambuild.compiler.compile.exceptions import PipelineCompileError
from streambuild.compiler.compile.models import ModelRetentionResolution
from streambuild.compiler.compile.types import RetentionOrigin
from streambuild.compiler.discovery.models import (
    KafkaRetentionPolicy,
    LoadedPipeline,
    ModelRetentionPolicy,
    TransformStep,
)
from streambuild.compiler.discovery.types import (
    KafkaRetentionReference,
    RetentionMissingBehavior,
)

_DATE_TYPE_NAMES: frozenset[str] = frozenset({"Date", "Date32"})
_DATETIME_TYPE_PREFIX: str = "DateTime"


def render_kafka_retention(*, policy: KafkaRetentionPolicy) -> str:
    """Render retention over StreamBuild's fixed managed Kafka replay columns."""

    timestamp: str = "_replay_timestamp"
    if policy.fallback == KafkaRetentionReference.LANDED:
        timestamp = f"ifNull({timestamp}, _replay_landed_at)"
    if policy.cap_at == KafkaRetentionReference.LANDED:
        timestamp = f"least({timestamp}, _replay_landed_at)"
    return f"{timestamp} + {_interval(policy.duration_seconds)}"


def render_model_retention(
    *, policy: ModelRetentionPolicy, available_columns: Mapping[str, str], model_name: str
) -> str | None:
    """Render a model policy only when its required output columns are available."""

    required: tuple[str, ...] = tuple(
        column
        for column in (policy.timestamp_column, policy.cap_at_column)
        if column is not None and column not in available_columns
    )
    if required:
        if policy.when_missing == RetentionMissingBehavior.SKIP:
            return None
        raise PipelineCompileError(
            f"Model '{model_name}' retention requires missing output columns: {', '.join(required)}"
        )
    incompatible: tuple[str, ...] = tuple(
        f"{column} ({available_columns[column]})"
        for column in (policy.timestamp_column, policy.cap_at_column)
        if column is not None and not _is_timestamp_type(available_columns[column])
    )
    if incompatible:
        raise PipelineCompileError(
            f"Model '{model_name}' retention columns must be non-null Date or DateTime values: "
            f"{', '.join(incompatible)}"
        )
    timestamp: str = policy.timestamp_column
    if policy.cap_at_column is not None:
        timestamp = f"least({timestamp}, {policy.cap_at_column})"
    return f"{timestamp} + {_interval(policy.duration_seconds)}"


def effective_model_retention(
    *, loaded_pipeline: LoadedPipeline, transform: TransformStep
) -> ModelRetentionResolution:
    """Resolve explicit, pipeline, then project model retention."""

    if transform.ttl is not None:
        return ModelRetentionResolution()
    if transform.retention is not None:
        return ModelRetentionResolution(
            value=transform.retention,
            origin=RetentionOrigin.MODEL,
        )
    if loaded_pipeline.pipeline.model_retention is not None:
        return ModelRetentionResolution(
            value=loaded_pipeline.pipeline.model_retention,
            origin=RetentionOrigin.PIPELINE,
        )
    if loaded_pipeline.project is not None:
        return ModelRetentionResolution(
            value=loaded_pipeline.project.model_retention,
            origin=(
                RetentionOrigin.PROJECT
                if loaded_pipeline.project.model_retention is not None
                else None
            ),
        )
    return ModelRetentionResolution()


def _interval(duration_seconds: int) -> str:
    units: tuple[tuple[str, int], ...] = (
        ("DAY", 86_400),
        ("HOUR", 3_600),
        ("MINUTE", 60),
    )
    for unit, seconds in units:
        if duration_seconds % seconds == 0:
            return f"INTERVAL {duration_seconds // seconds} {unit}"
    return f"INTERVAL {duration_seconds} SECOND"


def _is_timestamp_type(column_type: str) -> bool:
    return not column_type.startswith("Nullable(") and (
        column_type in _DATE_TYPE_NAMES or column_type.startswith(_DATETIME_TYPE_PREFIX)
    )
