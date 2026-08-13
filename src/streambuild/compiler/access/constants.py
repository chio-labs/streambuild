"""Strict access-policy schema and permission metadata."""

from streambuild.compiler.access.types import Permission

ACCESS_POLICY_FILE_NAME: str = "access.yml"
PROTECTED_ROLE_NAMES: frozenset[str] = frozenset({"admin", "viewer"})
TOP_LEVEL_KEYS: frozenset[str] = frozenset({"roles"})
ROLE_KEYS: frozenset[str] = frozenset({"description", "grants"})
GRANT_KEYS: frozenset[str] = frozenset({"pipelines", "scope", "permissions"})
PIPELINES_KEY: str = "pipelines"
SCOPE_KEY: str = "scope"
YAML_MERGE_TAG: str = "tag:yaml.org,2002:merge"

SYSTEM_ONLY_PERMISSIONS: frozenset[Permission] = frozenset(
    {Permission.ACCOUNT_MANAGE, Permission.ROLE_ASSIGN}
)
PIPELINE_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.QUALITY_TEST_RUN,
        Permission.QUALITY_AUDIT_RUN,
        Permission.BUILD_DIRECT_RUN,
        Permission.DEPLOYMENT_CREATE,
        Permission.BUILD_CANCEL,
        Permission.DEPLOYMENT_PROMOTE,
    }
)
PROJECT_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.PROJECT_RELOAD,
        Permission.SOURCE_MESSAGES_READ,
        Permission.QUALITY_TEST_RUN,
        Permission.QUALITY_AUDIT_RUN,
        Permission.AUTOMATION_MANAGE,
    }
)
TARGET_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.SOURCE_MESSAGES_READ,
        Permission.BUILD_KILL,
        Permission.DEPLOYMENT_CLEANUP,
        Permission.AUTOMATION_MANAGE,
    }
)
