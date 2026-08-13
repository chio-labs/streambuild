"""Build a stable semantic access-policy fingerprint."""

import hashlib
import json

from streambuild.compiler.access.models import CompiledAccessRole


def access_policy_fingerprint(*, roles: tuple[CompiledAccessRole, ...]) -> str:
    """Hash normalized role and grant semantics independently of YAML ordering."""

    payload: list[dict[str, object]] = []
    for role in roles:
        grants: list[dict[str, object]] = []
        for grant in role.grants:
            grants.append(
                {
                    "scope": None if grant.scope is None else grant.scope.value,
                    "pipelines": list(grant.pipelines),
                    "permissions": [permission.value for permission in grant.permissions],
                }
            )
        payload.append(
            {
                "name": role.name,
                "description": role.description,
                "grants": grants,
            }
        )
    canonical: str = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
