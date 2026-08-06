"""Discovery entry point for SQL audit files."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from streambuild.compiler.audit_discovery._helpers.generic import (
    discover_generic_sql_audit_definitions,
    render_generic_sql_audits,
)
from streambuild.compiler.audit_discovery._helpers.parsing import parse_sql_audit_file
from streambuild.compiler.audit_discovery.models import (
    LoadedGenericSqlAuditInstance,
    LoadedSqlAudit,
)
from streambuild.compiler.macros.models import MacroContext, MacroRegistry


def discover_sql_audits(
    *,
    root: Path,
    contents_by_path: Mapping[Path, str] | None = None,
    macro_registry: MacroRegistry | None = None,
    macro_context: MacroContext | None = None,
    generic_audit_instances: tuple[LoadedGenericSqlAuditInstance, ...] = (),
) -> list[LoadedSqlAudit]:
    """Discover and parse SQL audit files under a project audits root."""

    if not root.exists() and not generic_audit_instances:
        return []
    loaded_audits: list[LoadedSqlAudit] = []
    generic_root: Path = root / "generic"
    file_path: Path
    for file_path in sorted(root.rglob("*.sql")) if root.exists() else ():
        if generic_root in file_path.parents:
            continue
        loaded_audits.extend(
            parse_sql_audit_file(
                file_path=file_path,
                contents=None if contents_by_path is None else contents_by_path[file_path],
                macro_registry=macro_registry,
                macro_context=macro_context,
            )
        )
    loaded_audits.extend(
        render_generic_sql_audits(
            definitions=discover_generic_sql_audit_definitions(
                root=generic_root,
                contents_by_path=contents_by_path,
                macro_registry=macro_registry,
                macro_context=macro_context,
            ),
            instances=generic_audit_instances,
        )
    )
    return loaded_audits
