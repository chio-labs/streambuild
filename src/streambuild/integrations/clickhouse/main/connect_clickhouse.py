"""Open a ClickHouse connection from resolved connection configuration."""

from typing import cast

import clickhouse_connect

from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig
from streambuild.integrations.clickhouse.types import RawClickHouseClient


def connect_clickhouse(config: ClickHouseConnectionConfig) -> ClickHouseClient:
    """Open a ClickHouse connection and wrap it in the client boundary.

    The driver types its `database` parameter as a required string, so an unset
    database must be omitted from the call rather than passed as None.
    """

    if config.database is None:
        raw_client: RawClickHouseClient = cast(
            RawClickHouseClient,
            clickhouse_connect.get_client(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password,
            ),
        )
    else:
        raw_client = cast(
            RawClickHouseClient,
            clickhouse_connect.get_client(
                host=config.host,
                port=config.port,
                username=config.username,
                password=config.password,
                database=config.database,
            ),
        )
    return ClickHouseClient(raw_client)
