"""Parsing helpers for authored SQL audit files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from sqlglot import exp, parse
from sqlglot.errors import ParseError

from streambuild.compiler.compile.helpers.refs import extract_refs
from streambuild.compiler.compile.models import ParsedRef
from streambuild.compiler.discovery.helpers.auditing.constants import (
    ALLOWED_AUDIT_KEYS,
    ALLOWED_AUDIT_SEVERITIES,
    AUDIT_BLOCK_PATTERN,
    GENERIC_AUDIT_QUOTED_PARAMETER_PATTERN,
    GENERIC_AUDIT_RAW_PARAMETER_PATTERN,
)
from streambuild.compiler.discovery.helpers.auditing.exceptions import SqlAuditParseError
from streambuild.compiler.discovery.shared.helpers.macros.main import expand_project_sql_macros
from streambuild.compiler.shared.models import LoadedGenericSqlAuditDefinition, LoadedSqlAudit
from streambuild.spec.models.types import SqlRelationType


def parse_sql_audit_file(file_path: Path) -> tuple[LoadedSqlAudit, ...]:
    """Parse one authored SQL audit file into one or more discovered audit specs."""

    contents: str = file_path.read_text(encoding="utf-8")
    matched_blocks: tuple[tuple[int, str, str], ...] = tuple(
        (match.start(), match.group("header"), match.group("sql"))
        for match in AUDIT_BLOCK_PATTERN.finditer(contents)
    )
    if not matched_blocks:
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' must start with an AUDIT(...) header as the first "
            "non-whitespace content"
        )
    if contents[: matched_blocks[0][0]].strip():
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' must not contain content before the first AUDIT(...) block"
        )
    loaded_audits: list[LoadedSqlAudit] = []
    block_index: int
    header: str
    sql: str
    _start_index: int
    for block_index, (_start_index, header, sql) in enumerate(matched_blocks, start=1):
        loaded_audits.append(
            _parse_concrete_audit_block(
                file_path=file_path,
                header=header,
                sql=sql,
                audit_index=block_index,
            )
        )
    if len(loaded_audits) > 1:
        _validate_multi_audit_names(file_path=file_path, loaded_audits=tuple(loaded_audits))
    return tuple(loaded_audits)


def parse_generic_sql_audit_definition(file_path: Path) -> LoadedGenericSqlAuditDefinition:
    """Parse one generic SQL audit definition from `audits/generic/`."""

    contents: str = file_path.read_text(encoding="utf-8")
    matched_blocks: tuple[tuple[str, str], ...] = tuple(
        (match.group("header"), match.group("sql"))
        for match in AUDIT_BLOCK_PATTERN.finditer(contents)
    )
    if len(matched_blocks) != 1:
        raise SqlAuditParseError(
            f"Generic SQL audit definition '{file_path}' must contain exactly one AUDIT(...) block"
        )
    first_header: str
    first_sql: str
    first_header, first_sql = matched_blocks[0]
    header_values: dict[str, Any] = _parse_audit_header(
        header=first_header,
        file_path=file_path,
    )
    if header_values:
        raise SqlAuditParseError(
            f"Generic SQL audit definition '{file_path}' must not define AUDIT() header fields"
        )
    query: str = expand_project_sql_macros(sql=first_sql.strip(), file_path=file_path)
    if not query:
        raise SqlAuditParseError(
            f"Generic SQL audit definition '{file_path}' must define a query after AUDIT(...)"
        )
    _validate_single_query(file_path=file_path, sql=query)
    return LoadedGenericSqlAuditDefinition(
        file_path=file_path,
        query=query,
        raw_parameter_names=_discover_raw_generic_sql_audit_parameter_names(query),
        quoted_parameter_names=_discover_quoted_generic_sql_audit_parameter_names(query),
        name=file_path.stem,
    )


def _parse_concrete_audit_block(
    *,
    file_path: Path,
    header: str,
    sql: str,
    audit_index: int,
) -> LoadedSqlAudit:
    header_values: dict[str, Any] = _parse_audit_header(header=header, file_path=file_path)
    query: str = expand_project_sql_macros(sql=sql.strip(), file_path=file_path)
    if not query:
        raise SqlAuditParseError(f"SQL audit '{file_path}' must define a query after AUDIT(...)")
    _validate_single_query(file_path=file_path, sql=query)
    parsed_refs: tuple[ParsedRef, ...] = tuple(extract_refs(query))
    if not parsed_refs:
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' must reference at least one model with __ref(...)"
        )
    parsed_ref: ParsedRef
    for parsed_ref in parsed_refs:
        if parsed_ref.relation_type != SqlRelationType.REF:
            raise SqlAuditParseError(
                f"SQL audit '{file_path}' may only use __ref(...); __source(...) is not allowed"
            )
    referenced_model_names: tuple[str, ...] = tuple(dict.fromkeys(ref.name for ref in parsed_refs))
    return LoadedSqlAudit(
        file_path=file_path,
        query=query,
        referenced_model_names=referenced_model_names,
        severity=_parse_audit_severity(header_values=header_values, file_path=file_path),
        description=_parse_audit_description(header_values=header_values, file_path=file_path),
        name=_parse_audit_name(header_values=header_values, file_path=file_path),
        audit_index=audit_index,
    )


def _parse_audit_header(*, header: str, file_path: Path) -> dict[str, Any]:
    stripped_header: str = header.strip()
    if not stripped_header:
        return {}
    try:
        parsed_header: Any = yaml.safe_load(f"{{{stripped_header}}}")
    except yaml.YAMLError as error:
        raise SqlAuditParseError(
            f"AUDIT() header in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(parsed_header, dict) or not all(
        isinstance(key, str) for key in parsed_header
    ):
        raise SqlAuditParseError(
            f"AUDIT() header in '{file_path}' must be a mapping of key: value pairs"
        )
    unknown_keys: tuple[str, ...] = tuple(
        sorted(str(key) for key in parsed_header if key not in ALLOWED_AUDIT_KEYS)
    )
    if unknown_keys:
        raise SqlAuditParseError(
            f"AUDIT() in '{file_path}' contains unsupported keys: {', '.join(unknown_keys)}"
        )
    return parsed_header


def _parse_audit_severity(*, header_values: dict[str, Any], file_path: Path) -> str:
    severity_value: Any = header_values.get("severity", "error")
    if not isinstance(severity_value, str) or severity_value not in ALLOWED_AUDIT_SEVERITIES:
        raise SqlAuditParseError(
            f"AUDIT() in '{file_path}' must define severity as 'error' or 'warning'"
        )
    return severity_value


def _parse_audit_description(*, header_values: dict[str, Any], file_path: Path) -> str | None:
    description_value: Any = header_values.get("description")
    if description_value is None:
        return None
    if not isinstance(description_value, str) or not description_value.strip():
        raise SqlAuditParseError(
            f"AUDIT() in '{file_path}' must define description as a non-empty string when set"
        )
    return description_value.strip()


def _parse_audit_name(*, header_values: dict[str, Any], file_path: Path) -> str | None:
    name_value: Any = header_values.get("name")
    if name_value is None:
        return None
    if not isinstance(name_value, str) or not name_value.strip():
        raise SqlAuditParseError(
            f"AUDIT() in '{file_path}' must define name as a non-empty string when set"
        )
    return name_value


def _discover_raw_generic_sql_audit_parameter_names(query: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            match.group("name") for match in GENERIC_AUDIT_RAW_PARAMETER_PATTERN.finditer(query)
        )
    )


def _discover_quoted_generic_sql_audit_parameter_names(query: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            match.group("name") for match in GENERIC_AUDIT_QUOTED_PARAMETER_PATTERN.finditer(query)
        )
    )


def _validate_single_query(*, file_path: Path, sql: str) -> None:
    try:
        parsed_statements: list[exp.Expr | None] = parse(sql, read="clickhouse")
    except ParseError as error:
        raise SqlAuditParseError(f"SQL audit '{file_path}' could not be parsed: {error}") from error
    statements: tuple[exp.Expr, ...] = tuple(
        statement for statement in parsed_statements if statement is not None
    )
    if len(statements) != 1:
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' must contain exactly one top-level query after AUDIT()"
        )


def _validate_multi_audit_names(
    *,
    file_path: Path,
    loaded_audits: tuple[LoadedSqlAudit, ...],
) -> None:
    missing_named_indexes: tuple[int, ...] = tuple(
        loaded_audit.audit_index for loaded_audit in loaded_audits if loaded_audit.name is None
    )
    if missing_named_indexes:
        raise SqlAuditParseError(
            f"SQL audit '{file_path}' contains multiple AUDIT(...) blocks; each must define name"
        )
    seen_names: set[str] = set()
    loaded_audit: LoadedSqlAudit
    for loaded_audit in loaded_audits:
        if loaded_audit.name in seen_names:
            raise SqlAuditParseError(
                f"SQL audit '{file_path}' contains duplicate audit name '{loaded_audit.name}'"
            )
        seen_names.add(loaded_audit.name or "")
