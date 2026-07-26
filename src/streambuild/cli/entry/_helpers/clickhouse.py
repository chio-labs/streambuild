from streambuild.cli.entry.models import ResolvedClickHouseConnection
from streambuild.integrations.clickhouse.classes.clickhouse_client import ClickHouseClient
from streambuild.integrations.clickhouse.main.connect_clickhouse import (
    connect_clickhouse,
)
from streambuild.integrations.clickhouse.models import ClickHouseConnectionConfig


def build_clickhouse_client(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str | None = None,
) -> ClickHouseClient:
    return connect_clickhouse(
        ClickHouseConnectionConfig(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )
    )


def build_clickhouse_client_for_connection(
    *,
    connection: ResolvedClickHouseConnection,
    database: str | None = None,
) -> ClickHouseClient:
    return build_clickhouse_client(
        host=connection.host,
        port=connection.port,
        username=connection.username,
        password=connection.password,
        database=database,
    )
