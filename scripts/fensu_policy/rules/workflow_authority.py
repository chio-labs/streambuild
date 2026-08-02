"""Rules enforcing workflow publication, construction, and execution authority."""

from fensu import Family, Fault, RuleContext, rule

from scripts.fensu_policy.classes.workflow_authority_policy import (
    WorkflowAuthorityPolicy,
)


@rule(
    code="XSTB004",
    family=Family.CUSTOM,
    slug="workflow-mutation-gateway",
    message="warehouse mutations must pass through the workflow gateway",
    remediation=(
        "Assemble exact SQL in an approved workflow assembler and execute it only through "
        "executor/workflow/main/_execute_warehouse_workflow.py."
    ),
)
def workflow_mutation_gateway(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    return WorkflowAuthorityPolicy(ctx=ctx).check_workflow_mutation_gateway()


@rule(
    code="XSTB005",
    family=Family.CUSTOM,
    slug="published-workflow-capability",
    message="build execution requires the artifact publication capability",
    remediation=(
        "Construct PublishedBuildWorkflow only in workflow artifact publication and pass that "
        "capability to execute_build_workflow."
    ),
)
def published_workflow_capability(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    return WorkflowAuthorityPolicy(ctx=ctx).check_published_workflow_capability()


@rule(
    code="XSTB006",
    family=Family.CUSTOM,
    slug="workflow-consumer-purity",
    message="workflow consumers must not derive SQL or execution order",
    remediation=(
        "Move rendering, planning, ordering, and statement construction into an approved command "
        "workflow assembler."
    ),
)
def workflow_consumer_purity(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    return WorkflowAuthorityPolicy(ctx=ctx).check_workflow_consumer_purity()


@rule(
    code="XSTB007",
    family=Family.CUSTOM,
    slug="workflow-statement-ownership",
    message="workflow statements must be constructed by approved command assemblers",
    remediation=(
        "Construct WarehouseStatement values only in a path listed by WORKFLOW_ASSEMBLER_PATHS."
    ),
)
def workflow_statement_ownership(*, module: object, ctx: RuleContext) -> list[Fault]:
    del module
    return WorkflowAuthorityPolicy(ctx=ctx).check_workflow_statement_ownership()
