"""Rule keeping event derivation inside the one event catalog module."""

from fensu import Family, Fault, RuleContext, rule

from scripts.fensu_policy.constants import (
    EVENT_CATALOG_PATH_PREFIX,
    EVENT_CONSTRUCTION_CALL_NAMES,
    PRODUCT_SCOPE_NAME,
)


@rule(
    code="XSTB009",
    family=Family.CUSTOM,
    slug="event-catalog-authority",
    message="sensor events are constructed only inside the streambuild.events catalog",
    remediation=(
        "Derive events from persisted observations via streambuild.events entry points; "
        "handlers consume events and never construct or re-emit them."
    ),
)
def event_catalog_authority(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    if ctx.scope() != PRODUCT_SCOPE_NAME:
        return []
    path_parts: tuple[str, ...] = ctx.repo_relative_parts()
    if path_parts[: len(EVENT_CATALOG_PATH_PREFIX)] == EVENT_CATALOG_PATH_PREFIX:
        return []
    faults: list[Fault] = []
    for construction in sorted(EVENT_CONSTRUCTION_CALL_NAMES):
        if construction in ctx.text.source:
            faults.append(ctx.path_fault())
    return faults
