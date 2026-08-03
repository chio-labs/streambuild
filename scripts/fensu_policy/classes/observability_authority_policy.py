"""Semantic implementation for non-authoritative observability enforcement."""

from fensu import Fault, ImportFact, RuleContext

from scripts.fensu_policy.constants import (
    OBSERVABILITY_AUTHORITY_ALLOWED_PATH_PREFIXES,
    OBSERVABILITY_QUERY_CALL_NAMES,
    OBSERVABILITY_TABLE_CONSTANT_NAMES,
    OBSERVABILITY_TABLE_NAMES,
    PRODUCT_SCOPE_NAME,
    QUALITY_MODULE_PREFIX,
)


class ObservabilityAuthorityPolicy:
    """Prevent planning and lifecycle code from reading UI history."""

    def __init__(self, *, ctx: RuleContext) -> None:
        self._ctx: RuleContext = ctx

    def check(self) -> list[Fault]:
        """Report observability reads from authoritative decision domains."""
        if self._ctx.scope() != PRODUCT_SCOPE_NAME:
            return []
        path_parts: tuple[str, ...] = self._ctx.repo_relative_parts()
        if any(
            path_parts[: len(prefix)] == prefix
            for prefix in OBSERVABILITY_AUTHORITY_ALLOWED_PATH_PREFIXES
        ):
            return []
        faults: list[Fault] = []
        imports_quality: bool = False
        imported: ImportFact
        for imported in self._ctx.facts.references().imports:
            imported_parts: tuple[tuple[str, ...], ...] = (imported.module_parts,) + tuple(
                imported.module_parts + alias.imported_parts
                if imported.from_import
                else alias.imported_parts
                for alias in imported.aliases
            )
            if any(
                parts[: len(QUALITY_MODULE_PREFIX)] == QUALITY_MODULE_PREFIX
                for parts in imported_parts
            ):
                imports_quality = True
        quality_module_name: str = ".".join(QUALITY_MODULE_PREFIX)
        if imports_quality or quality_module_name in self._ctx.text.source:
            faults.append(self._ctx.path_fault())
        query_name: str
        for query_name in sorted(OBSERVABILITY_QUERY_CALL_NAMES):
            if query_name in self._ctx.text.source:
                faults.append(self._ctx.path_fault())
        constant_name: str
        for constant_name in sorted(OBSERVABILITY_TABLE_CONSTANT_NAMES):
            if constant_name in self._ctx.text.source:
                faults.append(self._ctx.path_fault())
        table_name: str
        for table_name in sorted(OBSERVABILITY_TABLE_NAMES):
            if table_name in self._ctx.text.source:
                faults.append(self._ctx.path_fault())
        return faults
