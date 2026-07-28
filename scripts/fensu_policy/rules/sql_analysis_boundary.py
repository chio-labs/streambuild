"""Import ownership for mandatory Polyglot SQL analysis."""

from __future__ import annotations

from fensu import Family, Fault, ImportFact, LiteralArgumentFact, NamedCallFact, RuleContext, rule

from scripts.fensu_policy.constants import (
    DYNAMIC_IMPORT_CALL_NAMES,
    POLYGLOT_ROOT_MODULE,
    PRODUCT_SCOPE_NAME,
    SQL_ANALYSIS_PATH_PREFIX,
    SQLGLOT_ROOT_MODULE,
)


@rule(
    code="XSTB003",
    family=Family.CUSTOM,
    slug="sql-analysis-import-ownership",
    message="SQL analysis engines must remain inside their migration boundary",
    remediation=(
        "Import Polyglot only from src/streambuild/compiler/sql_analysis/, and do not "
        "reintroduce a removed SQL analysis engine."
    ),
)
def sql_analysis_import_ownership(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() != PRODUCT_SCOPE_NAME:
        return []
    path_parts: tuple[str, ...] = ctx.repo_relative_parts()
    is_analysis_module: bool = (
        path_parts[: len(SQL_ANALYSIS_PATH_PREFIX)] == SQL_ANALYSIS_PATH_PREFIX
    )
    faults: list[Fault] = []
    imported: ImportFact
    for imported in ctx.facts.references().imports:
        imported_roots: tuple[str, ...] = imported.module_parts[:1] + tuple(
            alias.imported_parts[0] for alias in imported.aliases if alias.imported_parts
        )
        imports_polyglot_outside_boundary: bool = (
            POLYGLOT_ROOT_MODULE in imported_roots and not is_analysis_module
        )
        imports_removed_engine: bool = SQLGLOT_ROOT_MODULE in imported_roots
        if imports_polyglot_outside_boundary or imports_removed_engine:
            faults.append(ctx.fault_at(location=imported.location))
    called: NamedCallFact
    for called in ctx.facts.named_calls():
        literal_argument: LiteralArgumentFact
        for literal_argument in called.literal_arguments:
            literal_module_name: str = str(literal_argument.value)
            imports_polyglot: bool = (
                literal_module_name == POLYGLOT_ROOT_MODULE
                or literal_module_name.startswith(f"{POLYGLOT_ROOT_MODULE}.")
            )
            imports_removed_engine: bool = (
                literal_module_name == SQLGLOT_ROOT_MODULE
                or literal_module_name.startswith(f"{SQLGLOT_ROOT_MODULE}.")
            )
            if (
                called.name in DYNAMIC_IMPORT_CALL_NAMES
                and literal_argument.position == 0
                and isinstance(literal_argument.value, str)
                and ((imports_polyglot and not is_analysis_module) or imports_removed_engine)
            ):
                faults.append(ctx.fault_at(location=called.location))
    return faults
