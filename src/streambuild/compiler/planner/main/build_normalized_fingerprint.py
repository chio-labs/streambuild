"""Build the normalized fingerprint recorded for an object-state value."""

import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass

from streambuild.compiler.planner.exceptions import DeploymentPlanError


def build_normalized_fingerprint(value: object) -> str:
    """Build a deterministic comparable fingerprint payload string."""

    return json.dumps(value, default=_json_default, sort_keys=True)


def _json_default(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: getattr(value, field.name) for field in fields(value)}
    if isinstance(value, Mapping):
        return dict(value)
    raise DeploymentPlanError(
        f"Cannot serialize {type(value).__name__} in a normalized fingerprint"
    )
