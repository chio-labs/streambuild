from collections.abc import Iterator

import pytest

from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.main.connect_clickhouse import (
    connect_clickhouse,
)
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from tests.integration.src.streambuild.conftest import ClickHouseConnectionSettings


@pytest.fixture
def managed_clickhouse_client(
    clickhouse_connection_settings: ClickHouseConnectionSettings,
) -> Iterator[ClickHouseClient]:
    client: ClickHouseClient = connect_clickhouse(
        ClickHouseConnectionConfig(
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
