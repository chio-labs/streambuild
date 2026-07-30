"""SQL model parsing helpers for authored pipeline folders."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from streambuild.compiler.compile.main._extract_refs import extract_refs
from streambuild.compiler.compile.models import ParsedRef
from streambuild.compiler.discovery._helpers.model_header import parse_model_header
from streambuild.compiler.discovery.constants import (
    ALLOWED_MODEL_KEYS,
    DEFAULT_SQL_MODEL_ENGINE,
    DEFAULT_SQL_MODEL_ORDER_BY,
    MODEL_HEADER_PATTERN,
    SCHEMA_CHANGE_RULE_KEYS,
    SECONDS_BY_DURATION_UNIT,
)
from streambuild.compiler.discovery.exceptions import ModelHeaderSyntaxError, PipelineDiscoveryError
from streambuild.compiler.discovery.models import (
    ReplayOnChangePolicy,
    ReplayOnChangeRule,
    TransformStep,
)
from streambuild.compiler.discovery.types import (
    BoundedReplayFallback,
    ReplayAnchorMode,
    ReplayOnChangeMode,
    SchemaChangeKind,
    SqlRelationType,
)
from streambuild.compiler.macros.main._expand_macro_calls import expand_macro_calls
from streambuild.compiler.macros.models import MacroContext, MacroRegistry
from streambuild.diagnostics.models import CompilerDiagnostic, SourceLocation
from streambuild.diagnostics.types import DiagnosticPhase, DiagnosticSeverity


def load_transform_from_sql_file(
    *,
    file_path: Path,
    contents: str | None = None,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
) -> TransformStep:
    """Load one authored SQL model file into an internal transform step."""

    source_contents: str = file_path.read_text(encoding="utf-8") if contents is None else contents
    try:
        return _load_transform_from_sql_contents(
            file_path=file_path,
            source_contents=source_contents,
            macro_registry=macro_registry,
            macro_context=macro_context,
        )
    except PipelineDiscoveryError as error:
        error.diagnostic = CompilerDiagnostic(
            phase=DiagnosticPhase.DISCOVERY,
            severity=DiagnosticSeverity.ERROR,
            code="STB-DISCOVERY-001",
            message=str(error),
            resource_name=file_path.stem,
            location=SourceLocation(path=file_path, line=1, column=1),
        )
        raise


def _load_transform_from_sql_contents(
    *,
    file_path: Path,
    source_contents: str,
    macro_registry: MacroRegistry | None,
    macro_context: MacroContext | None,
) -> TransformStep:
    header_values, query = parse_model_sql(
        contents=source_contents,
        file_path=file_path,
        macro_registry=macro_registry,
        macro_context=macro_context,
    )
    query_line: int
    query_column: int
    query_line, query_column = _query_source_position(source_contents)
    return TransformStep(
        name=file_path.stem,
        source=infer_transform_source(
            query=query,
            file_path=file_path,
            source_line=query_line,
            source_column=query_column,
        ),
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
        replay_on_change=_optional_replay_on_change(
            header_values=header_values, file_path=file_path
        ),
        bounded_replay_fallback=_optional_bounded_replay_fallback(
            header_values=header_values, file_path=file_path
        ),
        query=query,
        source_file_path=file_path,
        source_line=query_line,
        source_column=query_column,
    )


def parse_model_sql(
    *,
    contents: str,
    file_path: Path,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
) -> tuple[dict[str, Any], str]:
    """Parse the required `MODEL(...)` header and SQL query body."""

    header_match: re.Match[str] | None = MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        raise PipelineDiscoveryError(
            f"SQL model '{file_path}' must start with a MODEL(...) header as the first "
            "non-whitespace content"
        )

    header_values: dict[str, Any] = _parse_model_header(
        header=header_match.group("header"), file_path=file_path
    )
    query_line: int
    query_column: int
    query_line, query_column = _query_source_position(contents)
    query: str = _expanded_query(
        sql=header_match.group("sql").strip(),
        file_path=file_path,
        macro_registry=macro_registry,
        macro_context=macro_context,
        source_line=query_line,
        source_column=query_column,
    )
    if not query:
        raise PipelineDiscoveryError(
            f"SQL model '{file_path}' must contain a SELECT query after MODEL(...)"
        )
    return header_values, query


def _expanded_query(
    *,
    sql: str,
    file_path: Path,
    macro_registry: MacroRegistry | None,
    macro_context: MacroContext | None,
    source_line: int,
    source_column: int,
) -> str:
    if macro_registry is None or macro_context is None:
        return sql
    return expand_macro_calls(
        sql=sql,
        file_path=file_path,
        registry=macro_registry,
        context=macro_context,
        source_line=source_line,
        source_column=source_column,
    )


def _query_source_position(contents: str) -> tuple[int, int]:
    header_match: re.Match[str] | None = MODEL_HEADER_PATTERN.match(contents)
    if header_match is None:
        raise PipelineDiscoveryError("Cannot locate SQL model query after a valid MODEL header")
    raw_query: str = header_match.group("sql")
    leading_length: int = len(raw_query) - len(raw_query.lstrip())
    query_index: int = header_match.start("sql") + leading_length
    line: int = contents.count("\n", 0, query_index) + 1
    previous_newline_index: int = contents.rfind("\n", 0, query_index)
    column: int = query_index - previous_newline_index
    return line, column


def infer_transform_source(
    *, query: str, file_path: Path, source_line: int, source_column: int
) -> str:
    """Infer the driving source from the single untyped relation reference."""

    parsed_refs: tuple[ParsedRef, ...] = tuple(
        extract_refs(
            sql=query,
            source_path=file_path,
            source_line=source_line,
            source_column=source_column,
        )
    )
    if not parsed_refs:
        raise PipelineDiscoveryError(
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
            raise PipelineDiscoveryError(
                f"SQL model '{file_path}' must contain exactly one unique __source(...) "
                "when source refs are present"
            )
        untyped_ref_names: set[str] = {
            parsed_ref.name
            for parsed_ref in parsed_refs
            if parsed_ref.relation_type == SqlRelationType.REF and parsed_ref.ref_type is None
        }
        if untyped_ref_names:
            raise PipelineDiscoveryError(
                f"SQL model '{file_path}' must not mix __source(...) with untyped __ref(...)"
            )
        return next(iter(source_ref_names))
    if len(unique_ref_names) == 1 and all(
        parsed_ref.ref_type is not None for parsed_ref in parsed_refs
    ):
        raise PipelineDiscoveryError(
            f"SQL model '{file_path}' must not declare ref_type for its driving input "
            f"'{next(iter(unique_ref_names))}'"
        )
    if len(driving_ref_names) != 1:
        raise PipelineDiscoveryError(
            f"SQL model '{file_path}' must contain exactly one unique untyped driving input "
            "when multiple relations are present"
        )
    return next(iter(driving_ref_names))


def _parse_model_header(*, header: str, file_path: Path) -> dict[str, Any]:
    try:
        parsed_header: dict[str, object] = parse_model_header(header=header)
    except ModelHeaderSyntaxError as error:
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' contains invalid SQLBuild header syntax: {error}"
        ) from error

    unknown_keys: list[str] = [key for key in parsed_header if key not in ALLOWED_MODEL_KEYS]
    if unknown_keys:
        unknown_key_list: str = ", ".join(sorted(unknown_keys))
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' contains unsupported keys: {unknown_key_list}"
        )
    return parsed_header


def _require_string(*, header_values: dict[str, Any], key: str, file_path: Path) -> str:
    value: Any = header_values.get(key)
    if not isinstance(value, str) or not value:
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' must define '{key}' as a non-empty string"
        )
    return value


def _sql_model_engine(*, header_values: dict[str, Any], file_path: Path) -> str:
    value: Any = header_values.get("engine")
    if value is None:
        return DEFAULT_SQL_MODEL_ENGINE
    return _require_string(header_values=header_values, key="engine", file_path=file_path)


def _require_string_list(*, header_values: dict[str, Any], key: str, file_path: Path) -> list[str]:
    value: Any = header_values.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) for item in value):
        raise PipelineDiscoveryError(
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
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' must define '{key}' as a string when set"
        )
    return value


def _optional_string_mapping(
    *, header_values: dict[str, Any], key: str, file_path: Path
) -> dict[str, str] | None:
    value: Any = header_values.get(key)
    if value is None:
        return None
    if not isinstance(value, dict) or not all(isinstance(map_key, str) for map_key in value):
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' must define '{key}' as a mapping when set"
        )
    return {map_key: str(map_value) for map_key, map_value in value.items()}


def _optional_replay_anchor(*, header_values: dict[str, Any], file_path: Path) -> ReplayAnchorMode:
    value: Any = header_values.get("replay_anchor")
    if value is None:
        return ReplayAnchorMode(ReplayAnchorMode.AUTO)
    if value not in {ReplayAnchorMode.AUTO, ReplayAnchorMode.NEVER}:
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' must define 'replay_anchor' as 'auto' or 'never'"
        )
    return ReplayAnchorMode(value)


def _optional_replay_on_change(
    *, header_values: dict[str, Any], file_path: Path
) -> ReplayOnChangePolicy | None:
    value: Any = header_values.get("replay_on_change")
    if value is None:
        return None
    if not isinstance(value, dict) or not all(isinstance(map_key, str) for map_key in value):
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' must define 'replay_on_change' as a mapping when set"
        )
    rule_values: dict[str, Any] = value
    unknown_keys: list[str] = [key for key in rule_values if key not in SCHEMA_CHANGE_RULE_KEYS]
    if unknown_keys:
        unknown_key_list: str = ", ".join(sorted(unknown_keys))
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' contains unsupported replay_on_change keys: "
            f"{unknown_key_list}"
        )
    return ReplayOnChangePolicy(
        breaking=_optional_replay_on_change_rule(
            rule_values=rule_values,
            key=SchemaChangeKind(SchemaChangeKind.BREAKING),
            file_path=file_path,
        ),
        non_breaking=_optional_replay_on_change_rule(
            rule_values=rule_values,
            key=SchemaChangeKind(SchemaChangeKind.NON_BREAKING),
            file_path=file_path,
        ),
    )


def _optional_replay_on_change_rule(
    *,
    rule_values: dict[str, Any],
    key: SchemaChangeKind,
    file_path: Path,
) -> ReplayOnChangeRule | None:
    value: Any = rule_values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' must define replay_on_change.{key} as a string"
        )
    return _parse_replay_on_change_rule(value=value, key=key, file_path=file_path)


def _parse_replay_on_change_rule(
    *, value: str, key: SchemaChangeKind, file_path: Path
) -> ReplayOnChangeRule:
    normalized: str = value.strip()
    if normalized == ReplayOnChangeMode.FULL:
        return ReplayOnChangeRule(mode=ReplayOnChangeMode(ReplayOnChangeMode.FULL))
    bounded_match: re.Match[str] | None = re.fullmatch(r"bounded-(\d+)([dhms])", normalized)
    if bounded_match is None:
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' must define replay_on_change.{key} as 'full' "
            "or 'bounded-<duration>'"
        )
    duration_value: int = int(bounded_match.group(1))
    duration_unit: str = bounded_match.group(2)
    return ReplayOnChangeRule(
        mode=ReplayOnChangeMode(ReplayOnChangeMode.BOUNDED),
        lookback_seconds=_duration_seconds(
            duration_value=duration_value, duration_unit=duration_unit
        ),
    )


def _duration_seconds(*, duration_value: int, duration_unit: str) -> int:
    return duration_value * SECONDS_BY_DURATION_UNIT.get(duration_unit, 1)


def _optional_bounded_replay_fallback(
    *, header_values: dict[str, Any], file_path: Path
) -> BoundedReplayFallback | None:
    value: Any = header_values.get("bounded_replay_fallback")
    if value is None:
        return None
    if value not in {
        BoundedReplayFallback.FULL,
        BoundedReplayFallback.BOUNDED_WITHOUT_HISTORY,
    }:
        raise PipelineDiscoveryError(
            f"MODEL(...) in '{file_path}' has unsupported bounded_replay_fallback '{value}'"
        )
    return BoundedReplayFallback(value)
