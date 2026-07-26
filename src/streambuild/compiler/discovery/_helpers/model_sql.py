"""SQL model parsing helpers for authored pipeline folders."""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent
from typing import Any

import yaml

from streambuild.compiler.compile._helpers.refs import extract_refs
from streambuild.compiler.compile.models import ParsedRef
from streambuild.compiler.discovery._helpers.constants import (
    ALLOWED_MODEL_KEYS,
    DEFAULT_SQL_MODEL_ENGINE,
    DEFAULT_SQL_MODEL_ORDER_BY,
    MODEL_HEADER_PATTERN,
)
from streambuild.compiler.discovery.shared._helpers.macros.main import expand_project_sql_macros
from streambuild.spec.models.steps import (
    SchemaChangeBackfillPolicy,
    SchemaChangeBackfillRule,
    TransformStep,
)
from streambuild.spec.models.types import (
    BoundedReplayFallback,
    ReplayAnchorMode,
    SchemaChangeBackfillMode,
    SchemaChangeKind,
    SqlRelationType,
)


def load_transform_from_sql_file(file_path: Path) -> TransformStep:
    """Load one authored SQL model file into an internal transform step."""

    contents: str = file_path.read_text(encoding="utf-8")
    header_values, query = parse_model_sql(contents=contents, file_path=file_path)
    return TransformStep(
        name=file_path.stem,
        source=infer_transform_source(query=query, file_path=file_path),
        engine=_sql_model_engine(header_values=header_values, file_path=file_path),
        order_by=_sql_model_order_by(header_values=header_values, file_path=file_path),
        partition_by=_optional_string(
            header_values=header_values, key="partition_by", file_path=file_path
        ),
        ttl=_optional_string(header_values=header_values, key="ttl", file_path=file_path),
        settings=_optional_string_mapping(
            header_values=header_values, key="settings", file_path=file_path
        ),
        replay_anchor=_optional_replay_anchor(header_values=header_values, file_path=file_path),
        schema_change_backfill=_optional_schema_change_backfill(
            header_values=header_values, file_path=file_path
        ),
        bounded_replay_fallback=_optional_bounded_replay_fallback(
            header_values=header_values, file_path=file_path
        ),
        query=query,
    )


def parse_model_sql(*, contents: str, file_path: Path) -> tuple[dict[str, Any], str]:
    """Parse the required `MODEL(...)` header and SQL query body."""

    header_match: re.Match[str] | None = MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        raise ValueError(
            f"SQL model '{file_path}' must start with a MODEL(...) header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, Any] = _parse_model_header(
        header=header_match.group("header"), file_path=file_path
    )
    query: str = expand_project_sql_macros(
        sql=header_match.group("sql").strip(),
        file_path=file_path,
    )
    if not query:
        raise ValueError(f"SQL model '{file_path}' must contain a SELECT query after MODEL(...)")
    return header_values, query


def infer_transform_source(*, query: str, file_path: Path) -> str:
    """Infer the driving source from the single untyped relation reference."""

    parsed_refs: tuple[ParsedRef, ...] = tuple(extract_refs(query))
    if not parsed_refs:
        raise ValueError(
            f"SQL model '{file_path}' must reference exactly one driving input using "
            "__source(...) or __ref(...)"
        )
    unique_ref_names: set[str] = {parsed_ref.name for parsed_ref in parsed_refs}
    source_ref_names: set[str] = {
        parsed_ref.name
        for parsed_ref in parsed_refs
        if parsed_ref.relation_type == SqlRelationType.SOURCE
    }
    driving_ref_names: set[str] = {
        parsed_ref.name for parsed_ref in parsed_refs if parsed_ref.ref_type is None
    }
    if source_ref_names:
        if len(source_ref_names) != 1:
            raise ValueError(
                f"SQL model '{file_path}' must contain exactly one unique __source(...) "
                "when source refs are present"
            )
        untyped_ref_names: set[str] = {
            parsed_ref.name
            for parsed_ref in parsed_refs
            if parsed_ref.relation_type == SqlRelationType.REF and parsed_ref.ref_type is None
        }
        if untyped_ref_names:
            raise ValueError(
                f"SQL model '{file_path}' must not mix __source(...) with untyped __ref(...)"
            )
        return next(iter(source_ref_names))
    if len(unique_ref_names) == 1 and all(
        parsed_ref.ref_type is not None for parsed_ref in parsed_refs
    ):
        raise ValueError(
            f"SQL model '{file_path}' must not declare ref_type for its driving input "
            f"'{next(iter(unique_ref_names))}'"
        )
    if len(driving_ref_names) != 1:
        raise ValueError(
            f"SQL model '{file_path}' must contain exactly one unique untyped driving input "
            "when multiple relations are present"
        )
    return next(iter(driving_ref_names))


def _parse_model_header(*, header: str, file_path: Path) -> dict[str, Any]:
    normalized_header: str = _normalize_model_header_yaml(header)
    parsed_header: Any = yaml.safe_load(normalized_header)
    if parsed_header is None:
        return {}
    if not isinstance(parsed_header, dict) or not all(
        isinstance(key, str) for key in parsed_header
    ):
        raise ValueError(f"MODEL(...) in '{file_path}' must define a mapping of key: value pairs")
    typed_parsed_header: dict[str, Any] = parsed_header

    unknown_keys: list[str] = [
        key for key in typed_parsed_header.keys() if key not in ALLOWED_MODEL_KEYS
    ]
    if unknown_keys:
        unknown_key_list: str = ", ".join(sorted(unknown_keys))
        raise ValueError(
            f"MODEL(...) in '{file_path}' contains unsupported keys: {unknown_key_list}"
        )
    return typed_parsed_header


def _normalize_model_header_yaml(header: str) -> str:
    """Normalize SQL-model header syntax into valid YAML block mapping text."""

    normalized_header: str = dedent(header).strip()
    return re.sub(r",(?=\s*(?:\n|$))", "", normalized_header)


def _require_string(*, header_values: dict[str, Any], key: str, file_path: Path) -> str:
    value: Any = header_values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"MODEL(...) in '{file_path}' must define '{key}' as a non-empty string")
    return value


def _sql_model_engine(*, header_values: dict[str, Any], file_path: Path) -> str:
    value: Any = header_values.get("engine")
    if value is None:
        return DEFAULT_SQL_MODEL_ENGINE
    return _require_string(header_values=header_values, key="engine", file_path=file_path)


def _require_string_list(*, header_values: dict[str, Any], key: str, file_path: Path) -> list[str]:
    value: Any = header_values.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise ValueError(
            f"MODEL(...) in '{file_path}' must define '{key}' as a non-empty list of strings"
        )
    return value


def _sql_model_order_by(*, header_values: dict[str, Any], file_path: Path) -> list[str]:
    value: Any = header_values.get("order_by")
    if value is None:
        return list(DEFAULT_SQL_MODEL_ORDER_BY)
    return _require_string_list(header_values=header_values, key="order_by", file_path=file_path)


def _optional_string(*, header_values: dict[str, Any], key: str, file_path: Path) -> str | None:
    value: Any = header_values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"MODEL(...) in '{file_path}' must define '{key}' as a string when set")
    return value


def _optional_string_mapping(
    *, header_values: dict[str, Any], key: str, file_path: Path
) -> dict[str, str] | None:
    value: Any = header_values.get(key)
    if value is None:
        return None
    if not isinstance(value, dict) or not all(isinstance(map_key, str) for map_key in value):
        raise ValueError(f"MODEL(...) in '{file_path}' must define '{key}' as a mapping when set")
    return {map_key: str(map_value) for map_key, map_value in value.items()}


def _optional_replay_anchor(*, header_values: dict[str, Any], file_path: Path) -> ReplayAnchorMode:
    value: Any = header_values.get("replay_anchor")
    if value is None:
        return ReplayAnchorMode(ReplayAnchorMode.AUTO)
    if value not in {ReplayAnchorMode.AUTO, ReplayAnchorMode.NEVER}:
        raise ValueError(
            f"MODEL(...) in '{file_path}' must define 'replay_anchor' as 'auto' or 'never'"
        )
    return ReplayAnchorMode(value)


def _optional_schema_change_backfill(
    *, header_values: dict[str, Any], file_path: Path
) -> SchemaChangeBackfillPolicy | None:
    value: Any = header_values.get("schema_change_backfill")
    if value is None:
        return None
    if not isinstance(value, dict) or not all(isinstance(map_key, str) for map_key in value):
        raise ValueError(
            "MODEL(...) in "
            f"'{file_path}' must define 'schema_change_backfill' as a mapping when set"
        )
    rule_values: dict[str, Any] = value
    unknown_keys: list[str] = [
        key for key in rule_values if key not in {"breaking", "non_breaking"}
    ]
    if unknown_keys:
        unknown_key_list: str = ", ".join(sorted(unknown_keys))
        raise ValueError(
            f"MODEL(...) in '{file_path}' contains unsupported schema_change_backfill keys: "
            f"{unknown_key_list}"
        )
    return SchemaChangeBackfillPolicy(
        breaking=_optional_schema_change_backfill_rule(
            rule_values=rule_values,
            key=SchemaChangeKind(SchemaChangeKind.BREAKING),
            file_path=file_path,
        ),
        non_breaking=_optional_schema_change_backfill_rule(
            rule_values=rule_values,
            key=SchemaChangeKind(SchemaChangeKind.NON_BREAKING),
            file_path=file_path,
        ),
    )


def _optional_schema_change_backfill_rule(
    *,
    rule_values: dict[str, Any],
    key: SchemaChangeKind,
    file_path: Path,
) -> SchemaChangeBackfillRule | None:
    value: Any = rule_values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"MODEL(...) in '{file_path}' must define schema_change_backfill.{key} as a string"
        )
    return _parse_schema_change_backfill_rule(value=value, key=key, file_path=file_path)


def _parse_schema_change_backfill_rule(
    *, value: str, key: SchemaChangeKind, file_path: Path
) -> SchemaChangeBackfillRule:
    normalized: str = value.strip()
    if normalized == SchemaChangeBackfillMode.FULL:
        return SchemaChangeBackfillRule(
            mode=SchemaChangeBackfillMode(SchemaChangeBackfillMode.FULL)
        )
    bounded_match: re.Match[str] | None = re.fullmatch(r"bounded\((\d+)([dhms])\)", normalized)
    if bounded_match is None:
        raise ValueError(
            f"MODEL(...) in '{file_path}' must define schema_change_backfill.{key} as 'full' "
            "or 'bounded(<duration>)'"
        )
    duration_value: int = int(bounded_match.group(1))
    duration_unit: str = bounded_match.group(2)
    return SchemaChangeBackfillRule(
        mode=SchemaChangeBackfillMode(SchemaChangeBackfillMode.BOUNDED),
        lookback_seconds=_duration_seconds(
            duration_value=duration_value, duration_unit=duration_unit
        ),
    )


def _duration_seconds(*, duration_value: int, duration_unit: str) -> int:
    if duration_unit == "d":
        return duration_value * 24 * 60 * 60
    if duration_unit == "h":
        return duration_value * 60 * 60
    if duration_unit == "m":
        return duration_value * 60
    return duration_value


def _optional_bounded_replay_fallback(
    *, header_values: dict[str, Any], file_path: Path
) -> BoundedReplayFallback | None:
    value: Any = header_values.get("bounded_replay_fallback")
    if value is None:
        return None
    if value not in {
        BoundedReplayFallback.FULL_REFRESH,
        BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
    }:
        raise ValueError(
            f"MODEL(...) in '{file_path}' has unsupported bounded_replay_fallback '{value}'"
        )
    return BoundedReplayFallback(value)
