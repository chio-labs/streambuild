import logging
import os
import socket
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import clickhouse_connect
import pytest
from clickhouse_connect.driver.client import Client
from docker.errors import DockerException
from testcontainers.core.container import DockerContainer

# Docker Desktop under WSL can fail to report Ryuk's published port even when
# regular containers start correctly. Disable Ryuk for these local integration
# tests and rely on fixture cleanup instead.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

CLICKHOUSE_USERNAME: str = "streambuild"
CLICKHOUSE_PASSWORD: str = "streambuild"


@dataclass(frozen=True)
class ClickHouseConnectionSettings:
    host: str
    port: int
    username: str
    password: str


@pytest.fixture(scope="session")
def clickhouse_connection_settings() -> Iterator[ClickHouseConnectionSettings]:
    try:
        with start_clickhouse_container() as settings:
            yield settings
    except DockerException as error:
        pytest.skip(f"Docker is not available for ClickHouse integration tests: {error}")


@pytest.fixture(scope="session")
def clickhouse_client(
    clickhouse_connection_settings: ClickHouseConnectionSettings,
) -> Iterator[Client]:
    client: Client = clickhouse_connect.get_client(
        host=clickhouse_connection_settings.host,
        port=clickhouse_connection_settings.port,
        username=clickhouse_connection_settings.username,
        password=clickhouse_connection_settings.password,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def clickhouse_database(clickhouse_client: Client) -> Iterator[str]:
    database_name: str = f"streambuild_test_{uuid.uuid4().hex[:12]}"
    clickhouse_client.command(f"CREATE DATABASE {database_name}")
    try:
        yield database_name
    finally:
        clickhouse_client.command(f"DROP DATABASE IF EXISTS {database_name} SYNC")


def _reserve_host_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_clickhouse_client(host: str, port: int) -> Client:
    deadline: float = time.time() + 30
    last_error: Exception | None = None
    clickhouse_logger: logging.Logger = logging.getLogger("clickhouse_connect.driver.httpclient")
    previous_level: int = clickhouse_logger.level
    clickhouse_logger.setLevel(logging.CRITICAL)
    try:
        while time.time() < deadline:
            try:
                return clickhouse_connect.get_client(
                    host=host,
                    port=port,
                    username=CLICKHOUSE_USERNAME,
                    password=CLICKHOUSE_PASSWORD,
                )
            except Exception as error:  # pragma: no cover
                last_error = error
                time.sleep(1)

        raise RuntimeError(
            "Timed out waiting for ClickHouse container to accept connections"
        ) from last_error
    finally:
        clickhouse_logger.setLevel(previous_level)


@contextmanager
def start_clickhouse_container() -> Iterator[ClickHouseConnectionSettings]:
    host_port: int = _reserve_host_port()
    container: DockerContainer = DockerContainer("clickhouse/clickhouse-server:24.8")
    container.with_bind_ports(8123, host_port)
    container.with_env("CLICKHOUSE_USER", CLICKHOUSE_USERNAME)
    container.with_env("CLICKHOUSE_PASSWORD", CLICKHOUSE_PASSWORD)
    with container:
        host: str = container.get_container_host_ip()
        port: int = int(container.get_exposed_port(8123))
        client: Client = _wait_for_clickhouse_client(host=host, port=port)
        client.close()
        yield ClickHouseConnectionSettings(
            host=host,
            port=port,
            username=CLICKHOUSE_USERNAME,
            password=CLICKHOUSE_PASSWORD,
        )
