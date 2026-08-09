"""Publish compact logical identities for authoritative run scopes."""

from streambuild.compiler.compile.models import LogicalResourceKey


def logical_resource_identities(keys: tuple[LogicalResourceKey, ...]) -> tuple[str, ...]:
    """Serialize stable logical keys in their graph-node identity form."""

    return tuple(f"{key.resource_type}:{key.name}" for key in keys)
