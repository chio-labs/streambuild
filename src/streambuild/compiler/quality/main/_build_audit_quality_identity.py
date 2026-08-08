"""Build the stable identity of one compiled SQL audit."""

from streambuild.compiler.audit_discovery.models import LoadedSqlAudit
from streambuild.compiler.quality._helpers.identity import build_identity, quality_node_name
from streambuild.compiler.quality.models import QualityNodeIdentity
from streambuild.compiler.quality.types import QualityNodeKind
from streambuild.compiler.sql_analysis.main._canonicalize_sql import canonicalize_sql


def build_audit_quality_identity(
    *, audit: LoadedSqlAudit, resolved_query: str, dialect: str
) -> QualityNodeIdentity:
    """Build target-neutral and target-resolved identity for one compiled audit."""

    node_name: str = quality_node_name(name=audit.name, file_stem=audit.file_path.stem)
    binding_payload: dict[str, object] = {
        "attached_column": audit.attached_column,
        "attached_model": audit.attached_model,
        "attachment_kind": audit.attachment_kind,
        "node_kind": QualityNodeKind.AUDIT,
        "node_name": node_name,
        "referenced_models": sorted(audit.referenced_model_names),
        "severity": audit.severity,
    }
    return build_identity(
        node_kind=QualityNodeKind.AUDIT,
        node_name=node_name,
        binding_payload=binding_payload,
        definition={"sql": canonicalize_sql(sql=audit.query, dialect=dialect)},
        execution={"sql": canonicalize_sql(sql=resolved_query, dialect=dialect)},
    )
