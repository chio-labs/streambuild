"""Import-direction rules protecting the adapter contract and implementation boundary."""

from __future__ import annotations

from fensu import Family, Fault, ImportFact, RuleContext, rule

from scripts.fensu_policy.constants import (
    ADAPTER_IMPLEMENTATION_MODULE_PREFIX,
    CLICKHOUSE_ADAPTER_PATH_PREFIX,
    CLICKHOUSE_DRIVER_ROOT_MODULE,
    COMPILER_PATH_PREFIX,
    PRODUCT_SCOPE_NAME,
)


@rule(
    code="XSTB001",
    family=Family.CUSTOM,
    slug="compiler-adapter-independence",
    message="compiler modules must not import adapter implementations",
    remediation=(
        "Depend on the neutral streambuild.adapter contract instead of "
        "streambuild.adapters.<engine>."
    ),
)
def compiler_adapter_independence(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() != PRODUCT_SCOPE_NAME:
        return []
    path_parts: tuple[str, ...] = ctx.repo_relative_parts()
    if path_parts[: len(COMPILER_PATH_PREFIX)] != COMPILER_PATH_PREFIX:
        return []
    prefix_length: int = len(ADAPTER_IMPLEMENTATION_MODULE_PREFIX)
    faults: list[Fault] = []
    imported: ImportFact
    for imported in ctx.facts.references().imports:
        imports_implementation: bool = imported.module_parts[
            :prefix_length
        ] == ADAPTER_IMPLEMENTATION_MODULE_PREFIX or any(
            alias.imported_parts[:prefix_length] == ADAPTER_IMPLEMENTATION_MODULE_PREFIX
            for alias in imported.aliases
        )
        if imports_implementation:
            faults.append(ctx.fault_at(location=imported.location))
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
    return faults
