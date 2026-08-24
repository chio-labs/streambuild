"""Bound persisted observation payloads and errors."""

import json

from streambuild.executor.observability.constants import (
    MAX_OBSERVATION_ERROR_LENGTH,
    MAX_OBSERVATION_JSON_BYTES,
)


def bounded_json(payload: dict[str, object]) -> str:
    """Serialize a deterministic payload and replace oversized diagnostics with a marker."""

    rendered: str = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    if len(rendered.encode()) <= MAX_OBSERVATION_JSON_BYTES:
        return rendered
    retained: dict[str, object] = {}
    key: str
    for key in ("missing_count", "unexpected_count"):
        if key in payload:
            retained[key] = payload[key]
    retained.update({"payload_truncated": True, "original_bytes": len(rendered.encode())})
    return json.dumps(
        retained,
        sort_keys=True,
        separators=(",", ":"),
    )


def complete_json(payload: dict[str, object]) -> str:
    """Serialize evidence that must remain complete regardless of payload size."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def concise_error(error_message: str | None) -> str | None:
    """Bound one persisted error without altering the command's rendered diagnostics."""

    return None if error_message is None else error_message[:MAX_OBSERVATION_ERROR_LENGTH]
