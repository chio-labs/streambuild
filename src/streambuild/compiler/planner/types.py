"""Planner runtime domain types."""

from enum import StrEnum


class PlannedChangeType(StrEnum):
    REBUILD = "rebuild"
    CREATE = "create"
    REPLACE = "replace"
    NO_OP = "no_op"


class TableSchemaChangeKind(StrEnum):
    NON_BREAKING = "non_breaking"
    BREAKING = "breaking"


class TableSchemaSeedCompatibility(StrEnum):
    SEEDABLE = "seedable"
    NON_SEEDABLE = "non_seedable"


class SchemaChangeBackfillMode(StrEnum):
    FULL = "full"
    BOUNDED = "bounded"


class RebuildStrategy(StrEnum):
    SHADOW_REBUILD = "shadow_rebuild"
    OFFLINE_REBUILD = "offline_rebuild"


class RebuildExecutionMode(StrEnum):
    FULL_REBUILD = "full_rebuild"
    SEEDED_BOUNDED_REBUILD = "seeded_bounded_rebuild"
    UNSEEDED_BOUNDED_REBUILD = "unseeded_bounded_rebuild"


class DeploymentPhase(StrEnum):
    PLAN = "plan"
    BACKFILL = "backfill"
    AUDIT = "audit"
    PUBLISH = "publish"


class DeploymentAction(StrEnum):
    PLAN_SHADOW_TABLE = "plan_shadow_table"
    PLAN_SHADOW_MATERIALIZED_VIEW = "plan_shadow_materialized_view"
    BACKFILL_SUBTREE = "backfill_subtree"
    AUDIT_SUBTREE = "audit_subtree"
    PUBLISH_SUBTREE = "publish_subtree"
