"""Build the normalized fingerprint recorded for an object-state value."""

import json


def build_normalized_fingerprint(value: object) -> str:
    """Build a deterministic comparable fingerprint payload string."""

    return json.dumps(value, sort_keys=True)
