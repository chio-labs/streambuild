"""Audit model-reference collection."""

from streambuild.compiler.audit_discovery.models import LoadedSqlAudit


def referenced_model_names(audits: tuple[LoadedSqlAudit, ...]) -> tuple[str, ...]:
    model_names: set[str] = set()
    for audit in audits:
        model_names.update(audit.referenced_model_names)
    return tuple(sorted(model_names))
