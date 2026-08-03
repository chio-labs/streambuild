"""Helpers for generic SQL audit definitions and model-header instances."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from streambuild.compiler.audit_discovery._helpers.parsing import (
    parse_generic_sql_audit_definition,
)
from streambuild.compiler.audit_discovery.constants import ALLOWED_AUDIT_SEVERITIES
from streambuild.compiler.audit_discovery.exceptions import SqlAuditParseError
from streambuild.compiler.audit_discovery.models import (
    LoadedGenericSqlAuditDefinition,
    LoadedGenericSqlAuditInstance,
    LoadedSqlAudit,
)
from streambuild.compiler.compile.main._extract_refs import extract_refs
from streambuild.compiler.compile.models import ParsedRef
from streambuild.compiler.discovery.models import ModelColumnSpec, TransformStep, ViewStep
from streambuild.compiler.discovery.types import SqlRelationType
from streambuild.compiler.macros.models import MacroContext, MacroRegistry
from streambuild.compiler.sql_analysis.main._render_string_literal import render_string_literal


def discover_generic_sql_audit_definitions(
    *,
    root: Path,
    contents_by_path: Mapping[Path, str] | None = None,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
) -> tuple[LoadedGenericSqlAuditDefinition, ...]:
    """Load generic SQL audit definitions from `audits/generic/`."""

    if not root.exists():
        return ()
    definitions: list[LoadedGenericSqlAuditDefinition] = []
    file_path: Path
    for file_path in sorted(root.rglob("*.sql")):
        definitions.append(
            parse_generic_sql_audit_definition(
                file_path=file_path,
                contents=None if contents_by_path is None else contents_by_path[file_path],
                macro_registry=macro_registry,
                macro_context=macro_context,
            )
        )
    duplicate_names: tuple[str, ...] = _find_duplicate_names(
        tuple(definition.name for definition in definitions)
    )
    if duplicate_names:
        raise SqlAuditParseError(
            f"Duplicate generic SQL audit definitions found: {', '.join(duplicate_names)}"
        )
    return tuple(definitions)


def build_model_header_generic_sql_audit_instances(
    *,
    models: tuple[TransformStep | ViewStep, ...],
) -> tuple[LoadedGenericSqlAuditInstance, ...]:
    """Build generic audit instances declared in MODEL(...) headers."""

    instances: list[LoadedGenericSqlAuditInstance] = []
    model: TransformStep | ViewStep
    for model in models:
        file_path: Path = (
            model.source_file_path
            if model.source_file_path is not None
            else Path(f"{model.name}.sql")
        )
        instances.extend(
            _build_generic_sql_audit_instances(
                file_path=file_path,
                raw_audits=list(model.audits),
                implicit_arguments={"model": model.name},
                default_name_prefix=model.name,
            )
        )
        column: ModelColumnSpec
        for column in model.columns:
            instances.extend(
                _build_generic_sql_audit_instances(
                    file_path=file_path,
                    raw_audits=list(column.audits),
                    implicit_arguments={"model": model.name, "column": column.name},
                    default_name_prefix=f"{model.name}.{column.name}",
                )
            )
    return tuple(instances)


def render_generic_sql_audits(
    *,
    definitions: tuple[LoadedGenericSqlAuditDefinition, ...],
    instances: tuple[LoadedGenericSqlAuditInstance, ...],
) -> tuple[LoadedSqlAudit, ...]:
    """Render concrete SQL audits from generic definitions and header-bound instances."""

    definitions_by_name: dict[str, LoadedGenericSqlAuditDefinition] = {
        definition.name: definition for definition in definitions
    }
    rendered_audits: list[LoadedSqlAudit] = []
    instance: LoadedGenericSqlAuditInstance
    for instance in instances:
        definition: LoadedGenericSqlAuditDefinition | None = definitions_by_name.get(
            instance.definition_name
        )
        if definition is None:
            raise SqlAuditParseError(
                f"Generic SQL audit instance '{instance.file_path}' references unknown definition "
                f"'{instance.definition_name}'"
            )
        rendered_query: str = _render_generic_sql_audit_query(
            definition=definition,
            arguments=instance.arguments,
            file_path=instance.file_path,
        )
        parsed_refs: tuple[ParsedRef, ...] = tuple(
            extract_refs(sql=rendered_query, source_path=instance.file_path)
        )
        if not parsed_refs:
            raise SqlAuditParseError(
                f"Rendered generic SQL audit '{instance.name}' must reference at least one model"
            )
        parsed_ref: ParsedRef
        for parsed_ref in parsed_refs:
            if parsed_ref.relation_type != SqlRelationType.REF:
                raise SqlAuditParseError(
                    f"Rendered generic SQL audit '{instance.name}' may only use __ref(...)"
                )
        rendered_audits.append(
            LoadedSqlAudit(
                file_path=instance.file_path,
                query=rendered_query,
                referenced_model_names=tuple(dict.fromkeys(ref.name for ref in parsed_refs)),
                severity=instance.severity,
                description=instance.description,
                name=instance.name,
                generic_definition_name=instance.definition_name,
            )
        )
    return tuple(rendered_audits)


def _build_generic_sql_audit_instances(
    *,
    file_path: Path,
    raw_audits: object,
    implicit_arguments: dict[str, object],
    default_name_prefix: str,
) -> list[LoadedGenericSqlAuditInstance]:
    if raw_audits in (None, []):
        return []
    if not isinstance(raw_audits, list):
        raise SqlAuditParseError(f"Model '{file_path}' must define audits as a list")
    instances: list[LoadedGenericSqlAuditInstance] = []
    audit_index: int
    raw_audit_entry: object
    for audit_index, raw_audit_entry in enumerate(raw_audits, start=1):
        explicit_arguments: dict[str, object]
        if isinstance(raw_audit_entry, str):
            definition_name: str = raw_audit_entry
            explicit_arguments = {}
        elif isinstance(raw_audit_entry, dict) and all(
            isinstance(key, str) for key in raw_audit_entry
        ):
            typed_audit_entry: dict[str, Any] = cast(dict[str, Any], raw_audit_entry)
            if len(typed_audit_entry) != 1:
                raise SqlAuditParseError(
                    f"Model '{file_path}' audit items must be a string or single-key mapping"
                )
            definition_name, raw_arguments = next(iter(typed_audit_entry.items()))
            if raw_arguments is None:
                explicit_arguments = {}
            elif not isinstance(raw_arguments, dict) or not all(
                isinstance(key, str) for key in raw_arguments
            ):
                raise SqlAuditParseError(
                    f"Model '{file_path}' audit '{definition_name}' must define "
                    "arguments as a mapping"
                )
            else:
                explicit_arguments = {key: value for key, value in raw_arguments.items()}
        else:
            raise SqlAuditParseError(
                f"Model '{file_path}' audit items must be a string or single-key mapping"
            )
        if not definition_name:
            raise SqlAuditParseError(
                f"Model '{file_path}' must use non-empty audit names under audits"
            )
        merged_arguments: dict[str, object] = _merge_implicit_and_explicit_arguments(
            file_path=file_path,
            definition_name=definition_name,
            implicit_arguments=implicit_arguments,
            explicit_arguments=explicit_arguments,
        )
        severity: str
        severity, merged_arguments = _pop_audit_string_argument(
            key="severity",
            arguments=merged_arguments,
            default_value="error",
            file_path=file_path,
            definition_name=definition_name,
            allowed_values=ALLOWED_AUDIT_SEVERITIES,
        )
        description: str | None
        description, merged_arguments = _pop_optional_audit_string_argument(
            key="description",
            arguments=merged_arguments,
            file_path=file_path,
            definition_name=definition_name,
        )
        name: str | None
        name, merged_arguments = _pop_optional_audit_string_argument(
            key="name",
            arguments=merged_arguments,
            file_path=file_path,
            definition_name=definition_name,
        )
        instances.append(
            LoadedGenericSqlAuditInstance(
                file_path=file_path,
                definition_name=definition_name,
                arguments=merged_arguments,
                name=name or f"{default_name_prefix}.{definition_name}.{audit_index}",
                severity=severity,
                description=description,
            )
        )
    return instances


def _merge_implicit_and_explicit_arguments(
    *,
    file_path: Path,
    definition_name: str,
    implicit_arguments: dict[str, object],
    explicit_arguments: dict[str, object],
) -> dict[str, object]:
    merged_arguments: dict[str, object] = dict(implicit_arguments)
    argument_name: str
    for argument_name, argument_value in explicit_arguments.items():
        if (
            argument_name in implicit_arguments
            and implicit_arguments[argument_name] != argument_value
        ):
            raise SqlAuditParseError(
                f"Model '{file_path}' audit '{definition_name}' must not override implicit "
                f"{argument_name} from its header context"
            )
        merged_arguments[argument_name] = argument_value
    return merged_arguments


def _pop_audit_string_argument(
    *,
    key: str,
    arguments: dict[str, object],
    default_value: str,
    file_path: Path,
    definition_name: str,
    allowed_values: frozenset[str],
) -> tuple[str, dict[str, object]]:
    remaining_arguments: dict[str, object] = dict(arguments)
    value: object = remaining_arguments.pop(key, default_value)
    if not isinstance(value, str) or value not in allowed_values:
        raise SqlAuditParseError(
            f"Model '{file_path}' audit '{definition_name}' must define {key} as one of: "
            f"{', '.join(sorted(allowed_values))}"
        )
    return value, remaining_arguments


def _pop_optional_audit_string_argument(
    *,
    key: str,
    arguments: dict[str, object],
    file_path: Path,
    definition_name: str,
) -> tuple[str | None, dict[str, object]]:
    remaining_arguments: dict[str, object] = dict(arguments)
    value: object = remaining_arguments.pop(key, None)
    if value is None:
        return None, remaining_arguments
    if not isinstance(value, str) or not value.strip():
        raise SqlAuditParseError(
            f"Model '{file_path}' audit '{definition_name}' must define {key} as a non-empty string"
        )
    return value.strip(), remaining_arguments


def _render_generic_sql_audit_query(
    *,
    definition: LoadedGenericSqlAuditDefinition,
    arguments: dict[str, object],
    file_path: Path,
) -> str:
    required_parameter_names: tuple[str, ...] = tuple(
        dict.fromkeys(definition.raw_parameter_names + definition.quoted_parameter_names)
    )
    missing_parameter_names: tuple[str, ...] = tuple(
        parameter_name
        for parameter_name in required_parameter_names
        if parameter_name not in arguments
    )
    if missing_parameter_names:
        raise SqlAuditParseError(
            f"Model '{file_path}' is missing arguments for generic audit "
            f"'{definition.name}': "
            f"{', '.join(missing_parameter_names)}"
        )
    unknown_parameter_names: tuple[str, ...] = tuple(
        sorted(
            argument_name
            for argument_name in arguments
            if argument_name not in required_parameter_names
        )
    )
    if unknown_parameter_names:
        raise SqlAuditParseError(
            f"Model '{file_path}' has unsupported arguments for generic audit "
            f"'{definition.name}': "
            f"{', '.join(unknown_parameter_names)}"
        )
    rendered_query: str = definition.query
    parameter_name: str
    for parameter_name in definition.quoted_parameter_names:
        rendered_query = rendered_query.replace(
            f"@'{parameter_name}'",
            _render_quoted_generic_sql_audit_argument(
                argument_value=arguments[parameter_name],
                file_path=file_path,
                parameter_name=parameter_name,
            ),
        )
    for parameter_name in definition.raw_parameter_names:
        rendered_query = rendered_query.replace(
            f"@{parameter_name}",
            _render_raw_generic_sql_audit_argument(
                argument_value=arguments[parameter_name],
                file_path=file_path,
                parameter_name=parameter_name,
            ),
        )
    return rendered_query


def _render_raw_generic_sql_audit_argument(
    *,
    argument_value: object,
    file_path: Path,
    parameter_name: str,
) -> str:
    if isinstance(argument_value, list):
        if not all(isinstance(item, (str, int, float)) for item in argument_value):
            raise SqlAuditParseError(
                f"Generic SQL audit arg '{parameter_name}' in '{file_path}' must be a "
                "list of strings or numbers"
            )
        return ", ".join(str(item) for item in argument_value)
    if isinstance(argument_value, (str, int, float)):
        return str(argument_value)
    raise SqlAuditParseError(
        f"Generic SQL audit arg '{parameter_name}' in '{file_path}' must be a string, "
        "number, or list"
    )


def _render_quoted_generic_sql_audit_argument(
    *,
    argument_value: object,
    file_path: Path,
    parameter_name: str,
) -> str:
    if isinstance(argument_value, list):
        if not all(isinstance(item, str) for item in argument_value):
            raise SqlAuditParseError(
                f"Generic SQL audit arg '{parameter_name}' in '{file_path}' must be a "
                "list of strings"
            )
        return ", ".join(
            render_string_literal(value=cast(str, item), dialect="clickhouse")
            for item in argument_value
        )
    if isinstance(argument_value, str):
        return render_string_literal(value=argument_value, dialect="clickhouse")
    raise SqlAuditParseError(
        f"Generic SQL audit arg '{parameter_name}' in '{file_path}' must be a string "
        "or list of strings"
    )


def _find_duplicate_names(names: tuple[str, ...]) -> tuple[str, ...]:
    seen_names: set[str] = set()
    duplicate_names: list[str] = []
    name: str
    for name in names:
        if name in seen_names and name not in duplicate_names:
            duplicate_names.append(name)
        seen_names.add(name)
    return tuple(duplicate_names)
