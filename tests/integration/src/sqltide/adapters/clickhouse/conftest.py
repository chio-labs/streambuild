from collections.abc import Iterator

import pytest

from sqltide.adapter.classes.adapter_connection import AdapterConnection
from sqltide.adapter.models import AdapterConnectionConfig
from sqltide.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.integration.src.sqltide.conftest import ClickHouseConnectionSettings


@pytest.fixture
def managed_clickhouse_client(
    clickhouse_connection_settings: ClickHouseConnectionSettings,
) -> Iterator[AdapterConnection]:
    client: AdapterConnection = ClickHouseAdapter().connect(
        AdapterConnectionConfig(
            host=clickhouse_connection_settings.host,
            port=clickhouse_connection_settings.port,
            username=clickhouse_connection_settings.username,
            password=clickhouse_connection_settings.password,
        )
    )
    try:
        yield client
    finally:
        client.close()
