"""Persist optional logical direct SQL baselines after materialization."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.direct._helpers.fingerprints import (
    persist_direct_fingerprints as _persist_direct_fingerprints,
)
from streambuild.executor.direct.models import DirectBuildRequest


def persist_direct_fingerprints(
    *,
    request: DirectBuildRequest,
    connection: AdapterConnection,
    applied_model_names: frozenset[str] | None = None,
) -> str | None:
    """Return a warning when optional baseline persistence fails."""

    return _persist_direct_fingerprints(
        request=request,
        connection=connection,
        applied_model_names=applied_model_names,
    )
