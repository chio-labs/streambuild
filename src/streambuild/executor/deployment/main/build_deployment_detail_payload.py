"""Entry returning one deployment with staged versus live comparison."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.executor.deployment._helpers.payload import build_detail_payload


def build_deployment_detail_payload(
    *,
    connection: AdapterConnection,
    database: str,
    metadata_database: str,
    deployment_id: str,
) -> dict[str, object] | None:
    """Return one deployment payload, or None when the identifier is unknown."""

    return build_detail_payload(
        connection=connection,
        database=database,
        metadata_database=metadata_database,
        deployment_id=deployment_id,
    )
