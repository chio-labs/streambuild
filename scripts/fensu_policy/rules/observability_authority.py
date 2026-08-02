"""Rule preventing UI history from becoming lifecycle authority."""

from fensu import Family, Fault, RuleContext, rule

from scripts.fensu_policy.classes.observability_authority_policy import (
    ObservabilityAuthorityPolicy,
)


@rule(
    code="XSTB008",
    family=Family.CUSTOM,
    slug="observability-non-authority",
    message="planner and lifecycle code must not read non-authoritative observability history",
    remediation=(
        "Use authoritative ownership, replay, deployment, publication, object-state, and live "
        "catalog evidence for lifecycle decisions; reserve invocation and node-result history "
        "for UI."
    ),
)
def observability_non_authority(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    return ObservabilityAuthorityPolicy(ctx=ctx).check()
