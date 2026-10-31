"""Parse SQLBuild-style MODEL header values."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal, cast

from sqltide._native import parse_model_header as _parse_native_model_header
from sqltide.compiler.discovery.constants import KAFKA_RETENTION_KEYS, MODEL_RETENTION_KEYS
from sqltide.compiler.discovery.exceptions import ModelHeaderSyntaxError, RetentionConfigError
from sqltide.compiler.discovery.main._parse_duration_seconds import parse_duration_seconds
from sqltide.compiler.discovery.models import KafkaRetentionPolicy, ModelRetentionPolicy
from sqltide.compiler.discovery.types import RetentionMissingBehavior

_COLUMN_NAME_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def parse_model_header(*, header: str) -> dict[str, object]:
    """Parse one MODEL header with SQLBuild's map and list grammar."""

    try:
        return _parse_native_model_header(header)
    except ValueError as error:
        raise ModelHeaderSyntaxError(str(error)) from None


def parse_model_retention(
    *, value: object, field_path: str
) -> ModelRetentionPolicy | Literal[False] | None:
    """Parse one typed model retention choice or explicit disable."""

    if value is None or value is False:
        return value
    mapping: Mapping[object, object] = _retention_mapping(value=value, field_path=field_path)
    _retention_allowed_keys(mapping=mapping, allowed=MODEL_RETENTION_KEYS, field_path=field_path)
    timestamp_column: str = _retention_column(
        value=mapping.get("timestamp_column"),
        field_path=f"{field_path}.timestamp_column",
    )
    cap_value: object | None = mapping.get("cap_at_column")
    cap_at_column: str | None = (
        None
        if cap_value is None
        else _retention_column(value=cap_value, field_path=f"{field_path}.cap_at_column")
    )
    when_missing_value: object = mapping.get("when_missing", RetentionMissingBehavior.ERROR)
    try:
        when_missing: RetentionMissingBehavior = RetentionMissingBehavior(when_missing_value)
    except (TypeError, ValueError) as error:
        raise RetentionConfigError(
            f"{field_path}.when_missing must be 'error' or 'skip'"
        ) from error
    return ModelRetentionPolicy(
        duration_seconds=_retention_duration(
            value=mapping.get("duration"), field_path=f"{field_path}.duration"
        ),
        timestamp_column=timestamp_column,
        cap_at_column=cap_at_column,
        when_missing=when_missing,
    )


def parse_kafka_retention(
    *, value: object, field_path: str
) -> KafkaRetentionPolicy | Literal[False] | None:
    """Parse one managed Kafka retention choice or explicit disable."""

    if value is None or value is False:
        return value
    mapping: Mapping[object, object] = _retention_mapping(value=value, field_path=field_path)
    _retention_allowed_keys(mapping=mapping, allowed=KAFKA_RETENTION_KEYS, field_path=field_path)
    return KafkaRetentionPolicy(
        duration_seconds=_retention_duration(
            value=mapping.get("duration"), field_path=f"{field_path}.duration"
        ),
        timestamp=_retention_choice(
            value=mapping.get("timestamp", "broker"),
            allowed=frozenset({"broker"}),
            field_path=f"{field_path}.timestamp",
        ),
        fallback=_retention_choice(
            value=mapping.get("fallback", "landed"),
            allowed=frozenset({"landed"}),
            field_path=f"{field_path}.fallback",
        ),
        cap_at=_optional_retention_choice(
            value=mapping.get("cap_at"),
            allowed=frozenset({"landed"}),
            field_path=f"{field_path}.cap_at",
        ),
    )


def _retention_mapping(*, value: object, field_path: str) -> Mapping[object, object]:
    if value is True or not isinstance(value, Mapping):
        raise RetentionConfigError(f"{field_path} must be false or a mapping")
    return cast(Mapping[object, object], value)


def _retention_allowed_keys(
    *, mapping: Mapping[object, object], allowed: frozenset[str], field_path: str
) -> None:
    invalid: tuple[str, ...] = tuple(sorted(str(key) for key in mapping if key not in allowed))
    if invalid:
        raise RetentionConfigError(f"{field_path} contains unsupported keys: {', '.join(invalid)}")


def _retention_duration(*, value: object, field_path: str) -> int:
    try:
        return parse_duration_seconds(value=value, field_path=field_path, allow_zero=False)
    except ValueError as error:
        raise RetentionConfigError(str(error)) from error


def _retention_column(*, value: object, field_path: str) -> str:
    if not isinstance(value, str) or _COLUMN_NAME_PATTERN.fullmatch(value) is None:
        raise RetentionConfigError(f"{field_path} must be an unqualified column name")
    return value


def _retention_choice(*, value: object, allowed: frozenset[str], field_path: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        expected: str = " or ".join(repr(item) for item in sorted(allowed))
        raise RetentionConfigError(f"{field_path} must be {expected}")
    return value


def _optional_retention_choice(
    *, value: object, allowed: frozenset[str], field_path: str
) -> str | None:
    return (
        None
        if value is None
        else _retention_choice(value=value, allowed=allowed, field_path=field_path)
    )
