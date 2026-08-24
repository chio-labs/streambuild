"""Closed operational permission and authored scope types."""

from enum import StrEnum


class Permission(StrEnum):
    """Finite operation vocabulary enforced by StreamBuild."""

    PROJECT_RELOAD = "project.reload"
    SOURCE_MESSAGES_READ = "source.messages.read"
    QUALITY_TEST_RUN = "quality.test.run"
    QUALITY_AUDIT_RUN = "quality.audit.run"
    BUILD_DIRECT_RUN = "build.direct.run"
    DEPLOYMENT_CREATE = "deployment.create"
    BUILD_CANCEL = "build.cancel"
    BUILD_KILL = "build.kill"
    DEPLOYMENT_PROMOTE = "deployment.promote"
    DEPLOYMENT_CLEANUP = "deployment.cleanup"
    PIPELINE_DESTROY = "pipeline.destroy"
    TARGET_RESET = "target.reset"
    AUTOMATION_MANAGE = "automation.manage"
    ACCOUNT_MANAGE = "account.manage"
    ROLE_ASSIGN = "role.assign"


class GrantScope(StrEnum):
    """Explicit non-pipeline grant scopes accepted in project policy."""

    PROJECT = "project"
    TARGET = "target"
