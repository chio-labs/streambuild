"""Warehouse-backed message browsing compiled from typed, whitelisted predicate documents."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.dev_server.exceptions import MessageQueryValidationError, MessageSchemaError
from streambuild.dev_server.models import (
    MessageFacetsRequest,
    MessageQueryCursor,
    MessageQueryMode,
    MessageQueryPredicate,
    MessagesQueryRequest,
)

_LIMIT_MIN: int = 1
_LIMIT_MAX: int = 500
_VALUE_PREVIEW_BYTES: int = 512
_RECORD_VALUE_MAX_BYTES: int = 16_777_216
_FACET_VALUE_LIMIT: int = 20
_NEWEST_WINDOWS_SECONDS: tuple[int | None, ...] = (3_600, 86_400, None)
_FACET_NEWEST_WINDOW_SECONDS: int = 86_400
_PATH_MAX_DEPTH: int = 8
_PATH_SEGMENT_MAX_CHARS: int = 64
_PREVIEW_PATH_MAX_COUNT: int = 4
_TIME_COLUMN_BY_NAME: dict[str, str] = {
    "landed": "_replay_landed_at",
    "kafka": "kafka_timestamp",
}
_HEADER_KEYS_COLUMN_NAME: str = "kafka_header_keys"
_MODE_KIND_NEWEST: str = "newest"
_MODE_KIND_TIME_RANGE: str = "timeRange"
_MODE_KIND_OFFSET_RANGE: str = "offsetRange"
_MODE_KINDS: frozenset[str] = frozenset(
    {_MODE_KIND_NEWEST, _MODE_KIND_TIME_RANGE, _MODE_KIND_OFFSET_RANGE}
)
_FORBIDDEN_SEGMENT_CHARS: frozenset[str] = frozenset({"'", '"', "`", "\\"})
_CONTROL_CHARACTER_LIMIT: int = 32
_OP_IN: str = "in"
_OP_CONTAINS: str = "contains"
_OP_EXISTS: str = "exists"
_OP_GT: str = "gt"
_OP_LT: str = "lt"
_NUMERIC_JSON_OPERATORS: dict[str, str] = {_OP_GT: ">", _OP_LT: "<"}


@dataclass(frozen=True)
class _MessagesQueryDocument:
    """One validated message browsing request compiled to SQL fragments."""

    mode_kind: str
    conditions: tuple[str, ...]
    limit: int
    cursor_condition: str | None
    preview_projections: tuple[str, ...]


def parse_messages_document(request: MessagesQueryRequest) -> _MessagesQueryDocument:
    """Validate one wire request and compile it to escaped SQL fragments."""

    if request.mode.kind not in _MODE_KINDS:
        raise MessageQueryValidationError(f"unsupported mode kind '{request.mode.kind}'")
    if request.timeColumn not in _TIME_COLUMN_BY_NAME:
        raise MessageQueryValidationError(f"unsupported time column '{request.timeColumn}'")
    if len(request.previewPaths) > _PREVIEW_PATH_MAX_COUNT:
        raise MessageQueryValidationError(
            f"previewPaths allows at most {_PREVIEW_PATH_MAX_COUNT} paths"
        )
    conditions: list[str] = [_predicate_condition(predicate) for predicate in request.predicates]
    conditions.extend(
        _mode_conditions(mode=request.mode, time_column=_TIME_COLUMN_BY_NAME[request.timeColumn])
    )
    return _MessagesQueryDocument(
        mode_kind=request.mode.kind,
        conditions=tuple(conditions),
        limit=min(max(request.limit, _LIMIT_MIN), _LIMIT_MAX),
        cursor_condition=(None if request.cursor is None else _cursor_condition(request.cursor)),
        preview_projections=tuple(
            f"{_json_string_expression(path=tuple(path), field_name='previewPaths')} "
            f"AS preview_{index}"
            for index, path in enumerate(request.previewPaths)
        ),
    )


def build_messages_sql(
    *,
    database: str,
    relation_name: str,
    document: _MessagesQueryDocument,
    window_seconds: int | None,
) -> str:
    """Render the message list SELECT for one bounded window."""

    projections: str = "".join(f", {projection}" for projection in document.preview_projections)
    return (
        "SELECT toString(_replay_landed_at) AS landed_at, "
        "toString(kafka_timestamp) AS kafka_timestamp, "
        "_replay_partition AS partition, _replay_offset AS offset, "
        "kafka_key AS key, length(kafka_key) AS key_bytes, "
        f"substring(kafka_value, 1, {_VALUE_PREVIEW_BYTES}) AS value_preview, "
        "length(kafka_value) AS value_bytes, "
        "kafka_header_keys AS header_keys, kafka_header_values AS header_values"
        f"{projections} "
        f"FROM `{database}`.`{relation_name}`"
        f"{_where_clause(document=document, window_seconds=window_seconds)} "
        "ORDER BY _replay_landed_at DESC, _replay_partition DESC, _replay_offset DESC "
        f"LIMIT {document.limit}"
    )


def read_source_messages(
    *,
    connection: AdapterConnection,
    database: str,
    relation_name: str,
    request: MessagesQueryRequest,
) -> dict[str, object]:
    """Return the newest matching messages, widening the window until satisfied."""

    document: _MessagesQueryDocument = parse_messages_document(request)
    windows: tuple[int | None, ...] = (
        _NEWEST_WINDOWS_SECONDS if document.mode_kind == _MODE_KIND_NEWEST else (None,)
    )
    rows: tuple[Mapping[str, object], ...] = ()
    used_window: int | None = None
    for window_seconds in windows:
        rows = connection.query(
            build_messages_sql(
                database=database,
                relation_name=relation_name,
                document=document,
                window_seconds=window_seconds,
            )
        ).named_rows()
        used_window = window_seconds
        if len(rows) >= document.limit:
            break
    row_payloads: list[dict[str, object]] = [
        _row_payload(row=row, preview_count=len(document.preview_projections)) for row in rows
    ]
    return {
        "rows": row_payloads,
        "nextCursor": _next_cursor(row_payloads=row_payloads, limit=document.limit),
        "windowSeconds": used_window,
        "limit": document.limit,
    }


def build_record_sql(*, database: str, relation_name: str, partition: int, offset: int) -> str:
    """Render the single-record primary-key lookup."""

    _require_non_negative(value=partition, field_name="partition")
    _require_non_negative(value=offset, field_name="offset")
    return (
        "SELECT toString(_replay_landed_at) AS landed_at, "
        "toString(kafka_timestamp) AS kafka_timestamp, "
        "_replay_partition AS partition, _replay_offset AS offset, "
        "kafka_topic AS topic, kafka_key AS key, length(kafka_key) AS key_bytes, "
        f"substring(kafka_value, 1, {_RECORD_VALUE_MAX_BYTES}) AS value, "
        "length(kafka_value) AS value_bytes, "
        "kafka_header_keys AS header_keys, kafka_header_values AS header_values "
        f"FROM `{database}`.`{relation_name}` "
        f"WHERE _replay_partition = {partition} AND _replay_offset = {offset} LIMIT 1"
    )


def read_source_message_record(
    *,
    connection: AdapterConnection,
    database: str,
    relation_name: str,
    partition: int,
    offset: int,
) -> dict[str, object] | None:
    """Return one full message by replay coordinates, or None when absent."""

    rows: tuple[Mapping[str, object], ...] = connection.query(
        build_record_sql(
            database=database,
            relation_name=relation_name,
            partition=partition,
            offset=offset,
        )
    ).named_rows()
    if not rows:
        return None
    row: Mapping[str, object] = rows[0]
    value_bytes: int = int(str(row["value_bytes"]))
    return {
        "landedAt": str(row["landed_at"]),
        "kafkaTimestamp": _optional_str(row["kafka_timestamp"]),
        "partition": int(str(row["partition"])),
        "offset": int(str(row["offset"])),
        "topic": str(row["topic"]),
        "key": str(row["key"]),
        "keyBytes": int(str(row["key_bytes"])),
        "value": str(row["value"]),
        "valueBytes": value_bytes,
        "valueTruncated": value_bytes > _RECORD_VALUE_MAX_BYTES,
        "headers": _header_pairs(row),
    }


def build_facets_sql(
    *,
    database: str,
    relation_name: str,
    document: _MessagesQueryDocument,
    facet_path: tuple[str | int, ...],
) -> tuple[str, str]:
    """Render the facet top-values and totals statements over one filtered window."""

    window_seconds: int | None = (
        _FACET_NEWEST_WINDOW_SECONDS if document.mode_kind == _MODE_KIND_NEWEST else None
    )
    facet_document: _MessagesQueryDocument = _MessagesQueryDocument(
        mode_kind=document.mode_kind,
        conditions=document.conditions,
        limit=document.limit,
        cursor_condition=None,
        preview_projections=(),
    )
    inner: str = (
        f"SELECT {_json_string_expression(path=facet_path, field_name='facetPath')} "
        f"AS facet_value FROM `{database}`.`{relation_name}`"
        f"{_where_clause(document=facet_document, window_seconds=window_seconds)}"
    )
    top_values: str = (
        f"SELECT facet_value, count() AS n FROM ({inner}) WHERE facet_value != '' "
        f"GROUP BY facet_value ORDER BY n DESC, facet_value ASC LIMIT {_FACET_VALUE_LIMIT}"
    )
    totals: str = f"SELECT count() AS total, countIf(facet_value = '') AS null_count FROM ({inner})"
    return top_values, totals


def read_source_message_facets(
    *,
    connection: AdapterConnection,
    database: str,
    relation_name: str,
    request: MessageFacetsRequest,
) -> dict[str, object]:
    """Return top facet values with counts inside the current filter document."""

    document: _MessagesQueryDocument = parse_messages_document(
        MessagesQueryRequest(
            mode=request.mode,
            predicates=request.predicates,
            limit=request.limit,
            cursor=None,
            timeColumn=request.timeColumn,
            previewPaths=[],
        )
    )
    facet_path: tuple[str | int, ...] = tuple(request.facetPath)
    top_values_sql: str
    totals_sql: str
    top_values_sql, totals_sql = build_facets_sql(
        database=database,
        relation_name=relation_name,
        document=document,
        facet_path=facet_path,
    )
    value_rows: tuple[Mapping[str, object], ...] = connection.query(top_values_sql).named_rows()
    totals_rows: tuple[Mapping[str, object], ...] = connection.query(totals_sql).named_rows()
    total_count: int = 0 if not totals_rows else int(str(totals_rows[0]["total"]))
    null_count: int = 0 if not totals_rows else int(str(totals_rows[0]["null_count"]))
    values: list[dict[str, object]] = [
        {"value": str(row["facet_value"]), "count": int(str(row["n"]))} for row in value_rows
    ]
    shown_count: int = sum(int(str(row["n"])) for row in value_rows)
    return {
        "values": values,
        "nullCount": null_count,
        "otherCount": max(total_count - null_count - shown_count, 0),
        "totalCount": total_count,
        "windowSeconds": (
            _FACET_NEWEST_WINDOW_SECONDS if document.mode_kind == _MODE_KIND_NEWEST else None
        ),
    }


def ensure_header_columns(
    *, connection: AdapterConnection, database: str, relation_name: str
) -> None:
    """Fail with an actionable reset message when the raw table predates header capture."""

    query: str = (
        "SELECT count() AS present FROM system.columns "
        f"WHERE database = '{_sql_literal(database)}' "
        f"AND table = '{_sql_literal(relation_name)}' "
        f"AND name = '{_HEADER_KEYS_COLUMN_NAME}'"
    )
    rows: tuple[Mapping[str, object], ...] = connection.query(query).named_rows()
    present: bool = bool(rows) and int(str(rows[0]["present"])) > 0
    if not present:
        raise MessageSchemaError(
            f"{database}.{relation_name} was created before StreamBuild captured Kafka "
            "headers; drop this pre-production raw table (direct mode) or redeploy the "
            "source (virtual mode) so StreamBuild can recreate it, then retry"
        )


def _predicate_condition(predicate: MessageQueryPredicate) -> str:
    handlers: dict[str, Callable[[MessageQueryPredicate], str]] = {
        "partition": _partition_condition,
        "key": _key_condition,
        "value": _value_condition,
        "json": _json_condition,
        "header": _header_condition,
    }
    handler: Callable[[MessageQueryPredicate], str] | None = handlers.get(predicate.field)
    if handler is None:
        raise MessageQueryValidationError(f"unsupported predicate field '{predicate.field}'")
    return handler(predicate)


def _partition_condition(predicate: MessageQueryPredicate) -> str:
    if predicate.op != _OP_IN:
        raise MessageQueryValidationError(f"unsupported op '{predicate.op}' for field 'partition'")
    if not predicate.values:
        raise MessageQueryValidationError("field 'partition' requires at least one value")
    for value in predicate.values:
        _require_non_negative(value=value, field_name="partition")
    rendered: str = ", ".join(str(value) for value in predicate.values)
    return f"_replay_partition IN ({rendered})"


def _key_condition(predicate: MessageQueryPredicate) -> str:
    literal: str = _string_value(predicate=predicate, field_name="key")
    conditions: dict[str, str] = {
        "eq": f"kafka_key = '{literal}'",
        "contains": f"position(kafka_key, '{literal}') > 0",
        "prefix": f"startsWith(kafka_key, '{literal}')",
    }
    condition: str | None = conditions.get(predicate.op)
    if condition is None:
        raise MessageQueryValidationError(f"unsupported op '{predicate.op}' for field 'key'")
    return condition


def _value_condition(predicate: MessageQueryPredicate) -> str:
    if predicate.op != _OP_CONTAINS:
        raise MessageQueryValidationError(f"unsupported op '{predicate.op}' for field 'value'")
    literal: str = _string_value(predicate=predicate, field_name="value")
    return f"position(kafka_value, '{literal}') > 0"


def _json_condition(predicate: MessageQueryPredicate) -> str:
    path: tuple[str | int, ...] = tuple(predicate.path)
    string_expression: str = _json_string_expression(path=path, field_name="json")
    if predicate.op == _OP_EXISTS:
        return f"JSONHas(kafka_value, {_json_path_arguments(path=path, field_name='json')})"
    if predicate.op in _NUMERIC_JSON_OPERATORS:
        number: float = _numeric_value(predicate=predicate, field_name="json")
        operator: str = _NUMERIC_JSON_OPERATORS[predicate.op]
        path_arguments: str = _json_path_arguments(path=path, field_name="json")
        return f"JSONExtractFloat(kafka_value, {path_arguments}) {operator} {number}"
    literal: str = _string_value(predicate=predicate, field_name="json")
    conditions: dict[str, str] = {
        "eq": f"{string_expression} = '{literal}'",
        "ne": f"{string_expression} != '{literal}'",
        "contains": f"position({string_expression}, '{literal}') > 0",
    }
    condition: str | None = conditions.get(predicate.op)
    if condition is None:
        raise MessageQueryValidationError(f"unsupported op '{predicate.op}' for field 'json'")
    return condition


def _header_condition(predicate: MessageQueryPredicate) -> str:
    literal: str = _string_value(predicate=predicate, field_name="header")
    conditions: dict[str, str] = {
        "eq": f"has(kafka_header_keys, '{literal}')",
        "contains": f"arrayExists(v -> position(v, '{literal}') > 0, kafka_header_values)",
    }
    condition: str | None = conditions.get(predicate.op)
    if condition is None:
        raise MessageQueryValidationError(f"unsupported op '{predicate.op}' for field 'header'")
    return condition


def _mode_conditions(*, mode: MessageQueryMode, time_column: str) -> tuple[str, ...]:
    if mode.kind == _MODE_KIND_NEWEST:
        return ()
    if mode.kind == _MODE_KIND_TIME_RANGE:
        return _time_range_conditions(mode=mode, time_column=time_column)
    return _offset_range_conditions(mode=mode)


def _time_range_conditions(*, mode: MessageQueryMode, time_column: str) -> tuple[str, ...]:
    if mode.fromTime is None and mode.toTime is None:
        raise MessageQueryValidationError("timeRange mode requires fromTime or toTime")
    conditions: list[str] = []
    if mode.fromTime is not None:
        conditions.append(
            f"{time_column} >= {_time_literal(value=mode.fromTime, field_name='fromTime')}"
        )
    if mode.toTime is not None:
        conditions.append(
            f"{time_column} <= {_time_literal(value=mode.toTime, field_name='toTime')}"
        )
    return tuple(conditions)


def _offset_range_conditions(*, mode: MessageQueryMode) -> tuple[str, ...]:
    if mode.partition is None:
        raise MessageQueryValidationError("offsetRange mode requires exactly one partition")
    _require_non_negative(value=mode.partition, field_name="partition")
    conditions: list[str] = [f"_replay_partition = {mode.partition}"]
    if mode.fromOffset is not None:
        _require_non_negative(value=mode.fromOffset, field_name="fromOffset")
        conditions.append(f"_replay_offset >= {mode.fromOffset}")
    if mode.toOffset is not None:
        _require_non_negative(value=mode.toOffset, field_name="toOffset")
        conditions.append(f"_replay_offset <= {mode.toOffset}")
    if (
        mode.fromOffset is not None
        and mode.toOffset is not None
        and mode.fromOffset > mode.toOffset
    ):
        raise MessageQueryValidationError("fromOffset must not exceed toOffset")
    return tuple(conditions)


def _cursor_condition(cursor: MessageQueryCursor) -> str:
    _require_non_negative(value=cursor.partition, field_name="cursor.partition")
    _require_non_negative(value=cursor.offset, field_name="cursor.offset")
    landed_literal: str = _time_literal(value=cursor.landedAt, field_name="cursor.landedAt")
    return (
        "(_replay_landed_at, _replay_partition, _replay_offset) < "
        f"({landed_literal}, {cursor.partition}, {cursor.offset})"
    )


def _where_clause(*, document: _MessagesQueryDocument, window_seconds: int | None) -> str:
    conditions: list[str] = list(document.conditions)
    if window_seconds is not None:
        conditions.append(f"_replay_landed_at >= now64(3) - INTERVAL {window_seconds} SECOND")
    if document.cursor_condition is not None:
        conditions.append(document.cursor_condition)
    return "" if not conditions else f" WHERE {' AND '.join(conditions)}"


def _json_string_expression(*, path: tuple[str | int, ...], field_name: str) -> str:
    return (
        f"JSONExtractString(kafka_value, {_json_path_arguments(path=path, field_name=field_name)})"
    )


def _json_path_arguments(*, path: tuple[str | int, ...], field_name: str) -> str:
    if not path:
        raise MessageQueryValidationError(f"field '{field_name}' requires a JSON path")
    if len(path) > _PATH_MAX_DEPTH:
        raise MessageQueryValidationError(
            f"field '{field_name}' allows JSON paths of depth at most {_PATH_MAX_DEPTH}"
        )
    return ", ".join(_json_path_segment(segment=segment, field_name=field_name) for segment in path)


def _json_path_segment(*, segment: str | int, field_name: str) -> str:
    if isinstance(segment, int):
        _require_non_negative(value=segment, field_name=field_name)
        return str(segment)
    if not segment or len(segment) > _PATH_SEGMENT_MAX_CHARS:
        raise MessageQueryValidationError(
            f"field '{field_name}' requires path segments of 1 to "
            f"{_PATH_SEGMENT_MAX_CHARS} characters"
        )
    invalid: bool = any(
        character in _FORBIDDEN_SEGMENT_CHARS or ord(character) < _CONTROL_CHARACTER_LIMIT
        for character in segment
    )
    if invalid:
        raise MessageQueryValidationError(
            f"field '{field_name}' path segments cannot contain quotes, backslashes, "
            "backticks, or control characters"
        )
    return f"'{segment}'"


def _string_value(*, predicate: MessageQueryPredicate, field_name: str) -> str:
    if not isinstance(predicate.value, str):
        raise MessageQueryValidationError(f"field '{field_name}' requires a string value")
    return _sql_literal(predicate.value)


def _numeric_value(*, predicate: MessageQueryPredicate, field_name: str) -> float:
    if isinstance(predicate.value, bool) or not isinstance(predicate.value, int | float):
        raise MessageQueryValidationError(
            f"field '{field_name}' requires a numeric value for gt/lt"
        )
    return float(predicate.value)


def _time_literal(*, value: str, field_name: str) -> str:
    try:
        _ = datetime.fromisoformat(value.replace(" ", "T").removesuffix("Z"))
    except ValueError as error:
        raise MessageQueryValidationError(
            f"field '{field_name}' requires an ISO 8601 timestamp"
        ) from error
    return f"parseDateTime64BestEffort('{_sql_literal(value)}', 3)"


def _require_non_negative(*, value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MessageQueryValidationError(f"field '{field_name}' requires non-negative integers")


def _row_payload(*, row: Mapping[str, object], preview_count: int) -> dict[str, object]:
    value_bytes: int = int(str(row["value_bytes"]))
    return {
        "landedAt": str(row["landed_at"]),
        "kafkaTimestamp": _optional_str(row["kafka_timestamp"]),
        "partition": int(str(row["partition"])),
        "offset": int(str(row["offset"])),
        "key": str(row["key"]),
        "keyBytes": int(str(row["key_bytes"])),
        "valuePreview": str(row["value_preview"]),
        "valueBytes": value_bytes,
        "valueTruncated": value_bytes > _VALUE_PREVIEW_BYTES,
        "headers": _header_pairs(row),
        "previewValues": [str(row[f"preview_{index}"]) for index in range(preview_count)],
    }


def _next_cursor(*, row_payloads: list[dict[str, object]], limit: int) -> dict[str, object] | None:
    if len(row_payloads) < limit:
        return None
    last: dict[str, object] = row_payloads[-1]
    return {
        "landedAt": last["landedAt"],
        "partition": last["partition"],
        "offset": last["offset"],
    }


def _header_pairs(row: Mapping[str, object]) -> list[list[str]]:
    keys: object = row["header_keys"]
    values: object = row["header_values"]
    if not isinstance(keys, list | tuple) or not isinstance(values, list | tuple):
        return []
    return [[str(key), str(value)] for key, value in zip(keys, values, strict=False)]


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _sql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
