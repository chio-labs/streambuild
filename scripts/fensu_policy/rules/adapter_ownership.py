"""Import-direction rules protecting the adapter contract and implementation boundary."""

from __future__ import annotations

from fensu import (
    Family,
    Fault,
    ImportFact,
    LiteralArgumentFact,
    NamedCallFact,
    RuleContext,
    rule,
)

from scripts.fensu_policy.constants import (
    ADAPTER_IMPLEMENTATION_MODULE_PREFIX,
    CLICKHOUSE_ADAPTER_PATH_PREFIX,
    CLICKHOUSE_DRIVER_ROOT_MODULE,
    COMPILER_PATH_PREFIX,
    DYNAMIC_IMPORT_CALL_NAMES,
    PRODUCT_SCOPE_NAME,
    RETIRED_CLICKHOUSE_INTEGRATION_MODULE_PREFIX,
    RETIRED_CLICKHOUSE_MODULE_PREFIX,
)


@rule(
    code="XSTB001",
    family=Family.CUSTOM,
    slug="adapter-package-ownership",
    message="modules must use the active adapter package boundaries",
    remediation=(
        "Depend on the neutral streambuild.adapter contract from compiler modules, and "
        "replace retired streambuild.clickhouse or streambuild.integrations.clickhouse "
        "imports with their streambuild.adapters.clickhouse owners."
    ),
)
def adapter_package_ownership(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() != PRODUCT_SCOPE_NAME:
        return []
    path_parts: tuple[str, ...] = ctx.repo_relative_parts()
    is_compiler_module: bool = path_parts[: len(COMPILER_PATH_PREFIX)] == COMPILER_PATH_PREFIX
    faults: list[Fault] = []
    imported: ImportFact
    for imported in ctx.facts.references().imports:
        alias_module_parts: tuple[tuple[str, ...], ...] = tuple(
            imported.module_parts + alias.imported_parts
            if imported.from_import
            else alias.imported_parts
            for alias in imported.aliases
        )
        imports_implementation: bool = is_compiler_module and (
            imported.module_parts[: len(ADAPTER_IMPLEMENTATION_MODULE_PREFIX)]
            == ADAPTER_IMPLEMENTATION_MODULE_PREFIX
            or any(
                parts[: len(ADAPTER_IMPLEMENTATION_MODULE_PREFIX)]
                == ADAPTER_IMPLEMENTATION_MODULE_PREFIX
                for parts in alias_module_parts
            )
        )
        imports_retired_clickhouse: bool = imported.module_parts[
            : len(RETIRED_CLICKHOUSE_MODULE_PREFIX)
        ] == RETIRED_CLICKHOUSE_MODULE_PREFIX or any(
            parts[: len(RETIRED_CLICKHOUSE_MODULE_PREFIX)] == RETIRED_CLICKHOUSE_MODULE_PREFIX
            for parts in alias_module_parts
        )
        imports_retired_integration: bool = imported.module_parts[
            : len(RETIRED_CLICKHOUSE_INTEGRATION_MODULE_PREFIX)
        ] == RETIRED_CLICKHOUSE_INTEGRATION_MODULE_PREFIX or any(
            parts[: len(RETIRED_CLICKHOUSE_INTEGRATION_MODULE_PREFIX)]
            == RETIRED_CLICKHOUSE_INTEGRATION_MODULE_PREFIX
            for parts in alias_module_parts
        )
        if imports_implementation or imports_retired_clickhouse or imports_retired_integration:
            faults.append(ctx.fault_at(location=imported.location))
    retired_clickhouse_name: str = ".".join(RETIRED_CLICKHOUSE_MODULE_PREFIX)
    retired_integration_name: str = ".".join(RETIRED_CLICKHOUSE_INTEGRATION_MODULE_PREFIX)
    called: NamedCallFact
    for called in ctx.facts.named_calls():
        literal_argument: LiteralArgumentFact
        for literal_argument in called.literal_arguments:
            if (
                called.name in DYNAMIC_IMPORT_CALL_NAMES
                and literal_argument.position == 0
                and isinstance(literal_argument.value, str)
                and (
                    literal_argument.value == retired_clickhouse_name
                    or literal_argument.value.startswith(f"{retired_clickhouse_name}.")
                    or literal_argument.value == retired_integration_name
                    or literal_argument.value.startswith(f"{retired_integration_name}.")
                )
            ):
                faults.append(ctx.fault_at(location=called.location))
    return faults


@rule(
    code="XSTB002",
    family=Family.CUSTOM,
    slug="warehouse-driver-ownership",
    message="only the ClickHouse adapter may import the ClickHouse driver",
    remediation=(
        "Move driver access and driver-exception translation into "
        "src/streambuild/adapters/clickhouse/ and depend on neutral adapter exceptions."
    ),
)
def warehouse_driver_ownership(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() != PRODUCT_SCOPE_NAME:
        return []
    path_parts: tuple[str, ...] = ctx.repo_relative_parts()
    if path_parts[: len(CLICKHOUSE_ADAPTER_PATH_PREFIX)] == CLICKHOUSE_ADAPTER_PATH_PREFIX:
        return []
    faults: list[Fault] = []
    imported: ImportFact
    for imported in ctx.facts.references().imports:
        imports_driver: bool = imported.module_parts[:1] == (CLICKHOUSE_DRIVER_ROOT_MODULE,) or any(
            alias.imported_parts[:1] == (CLICKHOUSE_DRIVER_ROOT_MODULE,)
            for alias in imported.aliases
        )
        if imports_driver:
            faults.append(ctx.fault_at(location=imported.location))
    called: NamedCallFact
    for called in ctx.facts.named_calls():
        literal_argument: LiteralArgumentFact
        for literal_argument in called.literal_arguments:
            if (
                called.name in DYNAMIC_IMPORT_CALL_NAMES
                and literal_argument.position == 0
                and isinstance(literal_argument.value, str)
                and (
                    literal_argument.value == CLICKHOUSE_DRIVER_ROOT_MODULE
                    or literal_argument.value.startswith(f"{CLICKHOUSE_DRIVER_ROOT_MODULE}.")
                )
            ):
                faults.append(ctx.fault_at(location=called.location))
    return faults
