"""Persist direct fingerprints adopted by reconciliation."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.adapter.models import AdapterDirectFingerprintRecord
from streambuild.compiler.compile.models import CompiledModel
from streambuild.executor.direct._helpers.fingerprints import (
    build_direct_fingerprint_records,
    persist_direct_fingerprint_records,
)


def persist_reconciled_direct_fingerprints(
    *,
    models: tuple[CompiledModel, ...],
    target_database: str,
    metadata_database: str,
    workflow_id: str,
    tool_version: str,
    connection: AdapterConnection,
) -> None:
    """Persist verified direct model baselines without changing warehouse relations."""

    records: tuple[AdapterDirectFingerprintRecord, ...] = build_direct_fingerprint_records(
        models=models,
        database=target_database,
        workflow_id=workflow_id,
        tool_version=tool_version,
    )
    persist_direct_fingerprint_records(
        records=records,
        database=metadata_database,
        connection=connection,
    )
