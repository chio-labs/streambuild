"""Discovery entry point for SQL audit files."""

from __future__ import annotations

from pathlib import Path

from streambuild.compiler.discovery.helpers.auditing.helpers.generic import (
    discover_generic_sql_audit_definitions,
    discover_schema_bound_generic_sql_audit_instances,
    render_generic_sql_audits,
)
from streambuild.compiler.discovery.helpers.auditing.helpers.parsing import parse_sql_audit_file
from streambuild.compiler.shared.models import LoadedSqlAudit


def discover_sql_audits(root: Path) -> list[LoadedSqlAudit]:
    """Discover and parse SQL audit files under a project audits root."""

    if not root.exists():
        return []
    loaded_audits: list[LoadedSqlAudit] = []
    generic_root: Path = root / "generic"
    file_path: Path
    for file_path in sorted(root.rglob("*.sql")):
        if generic_root in file_path.parents:
            continue
        loaded_audits.extend(parse_sql_audit_file(file_path))
    loaded_audits.extend(
        render_generic_sql_audits(
            definitions=discover_generic_sql_audit_definitions(generic_root),
            instances=discover_schema_bound_generic_sql_audit_instances(root.parent),
        )
    )
    return loaded_audits
