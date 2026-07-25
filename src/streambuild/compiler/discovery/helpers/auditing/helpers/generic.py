"""Helpers for generic SQL audit definitions and schema-attached instances."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from sqlglot import exp

from streambuild.compiler.compile.helpers.refs import extract_refs
from streambuild.compiler.compile.models import ParsedRef
from streambuild.compiler.discovery.helpers.auditing.constants import ALLOWED_AUDIT_SEVERITIES
from streambuild.compiler.discovery.helpers.auditing.exceptions import SqlAuditParseError
from streambuild.compiler.discovery.helpers.auditing.helpers.parsing import (
    parse_generic_sql_audit_definition,
)
from streambuild.compiler.shared.models import (
    LoadedGenericSqlAuditDefinition,
    LoadedGenericSqlAuditInstance,
    LoadedSqlAudit,
)
from streambuild.spec.models.types import SqlRelationType


def discover_generic_sql_audit_definitions(
    root: Path,
) -> tuple[LoadedGenericSqlAuditDefinition, ...]:
    """Load generic SQL audit definitions from `audits/generic/`."""

    if not root.exists():
        return ()
    definitions: list[LoadedGenericSqlAuditDefinition] = []
    file_path: Path
    for file_path in sorted(root.rglob("*.sql")):
        definitions.append(parse_generic_sql_audit_definition(file_path))
    duplicate_names: tuple[str, ...] = _find_duplicate_names(
        tuple(definition.name for definition in definitions)
    )
    if duplicate_names:
        raise SqlAuditParseError(
            f"Duplicate generic SQL audit definitions found: {', '.join(duplicate_names)}"
        )
    return tuple(definitions)


def discover_schema_bound_generic_sql_audit_instances(
    project_root: Path,
) -> tuple[LoadedGenericSqlAuditInstance, ...]:
    """Load generic SQL audit instances from `pipelines/**/schema.yml`."""

    pipelines_root: Path = project_root / "pipelines"
    if not pipelines_root.exists():
        return ()
    instances: list[LoadedGenericSqlAuditInstance] = []
    schema_file_path: Path
    for schema_file_path in sorted(pipelines_root.rglob("schema.yml")):
        instances.extend(_load_schema_file_generic_sql_audit_instances(schema_file_path))
    return tuple(instances)


def render_generic_sql_audits(
    *,
    definitions: tuple[LoadedGenericSqlAuditDefinition, ...],
    instances: tuple[LoadedGenericSqlAuditInstance, ...],
) -> tuple[LoadedSqlAudit, ...]:
    """Render concrete SQL audits from generic definitions and schema-bound instances."""

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
        parsed_refs: tuple[ParsedRef, ...] = tuple(extract_refs(rendered_query))
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
            )
        )
    return tuple(rendered_audits)


def _load_schema_file_generic_sql_audit_instances(
    file_path: Path,
) -> list[LoadedGenericSqlAuditInstance]:
    raw_values: Any = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if raw_values is None:
        return []
    if not isinstance(raw_values, dict) or not all(isinstance(key, str) for key in raw_values):
        raise SqlAuditParseError(f"Schema file '{file_path}' must define a top-level mapping")
    model_entries: Any = raw_values.get("models")
    if model_entries is None:
        return []
    if not isinstance(model_entries, list):
        raise SqlAuditParseError(f"Schema file '{file_path}' must define models as a list")
    instances: list[LoadedGenericSqlAuditInstance] = []
    raw_model_entry: object
    for raw_model_entry in model_entries:
        instances.extend(_load_model_generic_sql_audit_instances(file_path, raw_model_entry))
    return instances


def _load_model_generic_sql_audit_instances(
    file_path: Path,
    raw_model_entry: object,
) -> list[LoadedGenericSqlAuditInstance]:
    if not isinstance(raw_model_entry, dict) or not all(
        isinstance(key, str) for key in raw_model_entry
    ):
        raise SqlAuditParseError(f"Schema file '{file_path}' must use mapping items under models")
    typed_model_entry: dict[str, Any] = cast(dict[str, Any], raw_model_entry)
    model_name: Any = typed_model_entry.get("name")
    if not isinstance(model_name, str) or not model_name:
        raise SqlAuditParseError(f"Schema file '{file_path}' must define model name as a string")
    instances: list[LoadedGenericSqlAuditInstance] = []
    model_audits: Any = typed_model_entry.get("audits", [])
    instances.extend(
        _build_generic_sql_audit_instances(
            file_path=file_path,
            raw_audits=model_audits,
            implicit_arguments={"model": model_name},
            default_name_prefix=model_name,
        )
    )
    raw_columns: Any = typed_model_entry.get("columns", [])
    if raw_columns in (None, []):
        return instances
    if not isinstance(raw_columns, list):
        raise SqlAuditParseError(f"Schema file '{file_path}' must define columns as a list")
    raw_column_entry: object
    for raw_column_entry in raw_columns:
        if not isinstance(raw_column_entry, dict) or not all(
            isinstance(key, str) for key in raw_column_entry
        ):
            raise SqlAuditParseError(
                f"Schema file '{file_path}' must use mapping items under columns"
            )
        typed_column_entry: dict[str, Any] = raw_column_entry
        column_name: Any = typed_column_entry.get("name")
        if not isinstance(column_name, str) or not column_name:
            raise SqlAuditParseError(
                f"Schema file '{file_path}' must define column name as a string"
            )
        instances.extend(
            _build_generic_sql_audit_instances(
                file_path=file_path,
                raw_audits=typed_column_entry.get("audits", []),
                implicit_arguments={"model": model_name, "column": column_name},
                default_name_prefix=f"{model_name}.{column_name}",
            )
        )
    return instances


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
        raise SqlAuditParseError(f"Schema file '{file_path}' must define audits as a list")
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
                    f"Schema file '{file_path}' audit items must be a string or single-key mapping"
                )
            definition_name, raw_arguments = next(iter(typed_audit_entry.items()))
            if raw_arguments is None:
                explicit_arguments = {}
            elif not isinstance(raw_arguments, dict) or not all(
                isinstance(key, str) for key in raw_arguments
            ):
                raise SqlAuditParseError(
                    f"Schema file '{file_path}' audit '{definition_name}' must define "
                    "arguments as a mapping"
                )
            else:
                explicit_arguments = {key: value for key, value in raw_arguments.items()}
        else:
            raise SqlAuditParseError(
                f"Schema file '{file_path}' audit items must be a string or single-key mapping"
            )
        if not definition_name:
            raise SqlAuditParseError(
                f"Schema file '{file_path}' must use non-empty audit names under audits"
            )
        merged_arguments: dict[str, object] = _merge_implicit_and_explicit_arguments(
            file_path=file_path,
            definition_name=definition_name,
            implicit_arguments=implicit_arguments,
            explicit_arguments=explicit_arguments,
        )
        severity: str = _pop_audit_string_argument(
            key="severity",
            arguments=merged_arguments,
            default_value="error",
            file_path=file_path,
            definition_name=definition_name,
            allowed_values=ALLOWED_AUDIT_SEVERITIES,
        )
        description: str | None = _pop_optional_audit_string_argument(
            key="description",
            arguments=merged_arguments,
            file_path=file_path,
            definition_name=definition_name,
        )
        name: str | None = _pop_optional_audit_string_argument(
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
                f"Schema file '{file_path}' audit '{definition_name}' must not override implicit "
                f"{argument_name} from schema context"
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
) -> str:
    value: object = arguments.pop(key, default_value)
    if not isinstance(value, str) or value not in allowed_values:
        raise SqlAuditParseError(
            f"Schema file '{file_path}' audit '{definition_name}' must define {key} as one of: "
            f"{', '.join(sorted(allowed_values))}"
        )
    return value


def _pop_optional_audit_string_argument(
    *,
    key: str,
    arguments: dict[str, object],
    file_path: Path,
    definition_name: str,
) -> str | None:
    value: object = arguments.pop(key, None)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SqlAuditParseError(
            f"Schema file '{file_path}' audit '{definition_name}' must define {key} "
            "as a non-empty string"
        )
    return value.strip()


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
            f"Schema file '{file_path}' is missing arguments for generic audit "
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
            f"Schema file '{file_path}' has unsupported arguments for generic audit "
            f"'{definition.name}': "
            f"{', '.join(unknown_parameter_names)}"
        )
    rendered_query: str = definition.query
    parameter_name: str
    for parameter_name in definition.quoted_parameter_names:
        rendered_query = rendered_query.replace(
            f"@'{parameter_name}'",
            _render_quoted_generic_sql_audit_argument(
                arguments[parameter_name], file_path, parameter_name
            ),
        )
    for parameter_name in definition.raw_parameter_names:
        rendered_query = rendered_query.replace(
            f"@{parameter_name}",
            _render_raw_generic_sql_audit_argument(
                arguments[parameter_name], file_path, parameter_name
            ),
        )
    return rendered_query


def _render_raw_generic_sql_audit_argument(
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
            exp.Literal.string(item).sql(dialect="clickhouse") for item in argument_value
        )
    if isinstance(argument_value, str):
        return exp.Literal.string(argument_value).sql(dialect="clickhouse")
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
