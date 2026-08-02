"""Workflow ordering and execution intent types."""

from enum import StrEnum


class WorkflowMode(StrEnum):
    DIRECT = "direct"
    VIRTUAL_ENVIRONMENT = "virtual_environment"


class WorkflowPhase(StrEnum):
    PREFLIGHT = "preflight"
    PREPARATION = "preparation"
    OWNERSHIP = "ownership"
    TEARDOWN = "teardown"
    REALIZATION = "realization"
    STABILIZATION = "stabilization"
    BOUNDARY = "boundary"
    REPLAY = "replay"
    AUDIT = "audit"
    FINALIZATION = "finalization"


class StatementIntent(StrEnum):
    ASSERTION = "assertion"
    QUERY = "query"
    MUTATION = "mutation"
    WAIT = "wait"
