"""Create the StreamBuild metadata tables when they do not yet exist."""

from streambuild.adapter.classes.adapter_connection import AdapterConnection


def ensure_metadata_tables(*, client: AdapterConnection, metadata_database: str) -> None:
    """Create metadata state tables required for backfill bootstrap."""

    client.migrate_metadata_state(metadata_database)
