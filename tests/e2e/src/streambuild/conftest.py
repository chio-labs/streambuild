import os
import socket
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import NoReturn, Self

import clickhouse_connect
import pytest
from clickhouse_connect.driver.client import Client
from docker.errors import DockerException
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network
from testcontainers.core.wait_strategies import LogMessageWaitStrategy
from testcontainers.kafka._redpanda import RedpandaContainer

os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

CLICKHOUSE_USERNAME: str = "streambuild"
CLICKHOUSE_PASSWORD: str = "streambuild"
KAFKA_NETWORK_ALIAS: str = "kafka"
KAFKA_INTERNAL_PORT: int = 29092
KAFKA_INTERNAL_BOOTSTRAP_SERVER: str = f"{KAFKA_NETWORK_ALIAS}:{KAFKA_INTERNAL_PORT}"
REDPANDA_IMAGE: str = "redpandadata/redpanda:v24.2.7"
CONTAINER_STARTUP_TIMEOUT_SECONDS: int = 90
NO_ACTIVITY_LOG_CONFIG: Path = Path("tests/fixtures/clickhouse/no_activity_logs.xml").resolve()


def _stop_for_docker_unavailable(*, service: str, error: DockerException) -> NoReturn:
    message: str = f"Docker is not available for {service} E2E tests: {error}"
    if os.environ.get("CI", "").lower() == "true":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


class E2ERedpandaContainer(RedpandaContainer):
    """Redpanda that advertises its internal listener on the shared network alias.

    The stock container advertises PLAINTEXT on 127.0.0.1, which a sibling
    container such as ClickHouse cannot reach. ClickHouse consumes over the
    docker network, so the internal listener must advertise the alias.
    """

    def start(self, timeout: int = CONTAINER_STARTUP_TIMEOUT_SECONDS) -> Self:
        script: str = RedpandaContainer.TC_START_SCRIPT
        self.with_command(f'-c "while [ ! -f {script} ]; do sleep 0.1; done; sh {script}"')
        _ = DockerContainer.start(self)
        self.tc_start()
        LogMessageWaitStrategy(r".*Started Kafka API server.*").with_startup_timeout(
            timeout
        ).wait_until_ready(self)
        return self

    def tc_start(self) -> None:
        host: str = self.get_container_host_ip()
        port: int = self.get_exposed_port(self.redpanda_port)
        script: str = dedent(
            f"""
            #!/bin/bash
            /usr/bin/rpk redpanda start --mode dev-container --smp 1 --memory 512M \
            --kafka-addr PLAINTEXT://0.0.0.0:{KAFKA_INTERNAL_PORT},OUTSIDE://0.0.0.0:9092 \
            --advertise-kafka-addr \
            PLAINTEXT://{KAFKA_NETWORK_ALIAS}:{KAFKA_INTERNAL_PORT},OUTSIDE://{host}:{port}
            """
        ).strip()
        self.create_file(script.encode("utf-8"), RedpandaContainer.TC_START_SCRIPT)


@dataclass(frozen=True)
class E2EClickHouseConnectionSettings:
    host: str
    port: int
    username: str
    password: str
    container_id: str


@dataclass(frozen=True)
class E2EKafkaConnectionSettings:
    bootstrap_server: str
    internal_bootstrap_server: str


@pytest.fixture(scope="session")
def e2e_network() -> Iterator[Network]:
    with Network() as network:
        yield network


@pytest.fixture
def isolated_e2e_network() -> Iterator[Network]:
    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def e2e_kafka_connection_settings(e2e_network: Network) -> Iterator[E2EKafkaConnectionSettings]:
    try:
        host_port: int = _reserve_host_port()
        with (
            E2ERedpandaContainer(REDPANDA_IMAGE)
            .with_network(e2e_network)
            .with_bind_ports(KAFKA_INTERNAL_PORT, host_port)
            .with_network_aliases(KAFKA_NETWORK_ALIAS) as redpanda_container
        ):
            yield E2EKafkaConnectionSettings(
                bootstrap_server=redpanda_container.get_bootstrap_server(),
                internal_bootstrap_server=KAFKA_INTERNAL_BOOTSTRAP_SERVER,
            )
    except DockerException as error:
        _stop_for_docker_unavailable(service="Kafka", error=error)


@pytest.fixture
def isolated_e2e_kafka_connection_settings(
    isolated_e2e_network: Network,
) -> Iterator[E2EKafkaConnectionSettings]:
    try:
        host_port: int = _reserve_host_port()
        with (
            E2ERedpandaContainer(REDPANDA_IMAGE)
            .with_network(isolated_e2e_network)
            .with_bind_ports(KAFKA_INTERNAL_PORT, host_port)
            .with_network_aliases(KAFKA_NETWORK_ALIAS) as redpanda_container
        ):
            yield E2EKafkaConnectionSettings(
                bootstrap_server=redpanda_container.get_bootstrap_server(),
                internal_bootstrap_server=KAFKA_INTERNAL_BOOTSTRAP_SERVER,
            )
    except DockerException as error:
        _stop_for_docker_unavailable(service="Kafka", error=error)


@pytest.fixture(scope="session")
def e2e_clickhouse_connection_settings(
    e2e_network: Network,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
) -> Iterator[E2EClickHouseConnectionSettings]:
    del e2e_kafka_connection_settings
    try:
        host_port: int = _reserve_host_port()
        container: DockerContainer = DockerContainer("clickhouse/clickhouse-server:24.8")
        container.with_bind_ports(8123, host_port)
        container.with_env("CLICKHOUSE_USER", CLICKHOUSE_USERNAME)
        container.with_env("CLICKHOUSE_PASSWORD", CLICKHOUSE_PASSWORD)
        container.with_network(e2e_network)
        container.with_network_aliases("clickhouse")
        with container:
            host: str = container.get_container_host_ip()
            port: int = int(container.get_exposed_port(8123))
            client: Client = _wait_for_clickhouse_client(host=host, port=port)
            client.close()
            yield E2EClickHouseConnectionSettings(
                host=host,
                port=port,
                username=CLICKHOUSE_USERNAME,
                password=CLICKHOUSE_PASSWORD,
                container_id=container.get_wrapped_container().id,
            )
    except DockerException as error:
        _stop_for_docker_unavailable(service="ClickHouse", error=error)


@pytest.fixture(scope="session")
def no_activity_log_clickhouse_connection_settings() -> Iterator[E2EClickHouseConnectionSettings]:
    try:
        host_port: int = _reserve_host_port()
        container: DockerContainer = DockerContainer("clickhouse/clickhouse-server:24.8")
        container.with_bind_ports(8123, host_port)
        container.with_env("CLICKHOUSE_USER", CLICKHOUSE_USERNAME)
        container.with_env("CLICKHOUSE_PASSWORD", CLICKHOUSE_PASSWORD)
        container.with_volume_mapping(
            NO_ACTIVITY_LOG_CONFIG,
            "/etc/clickhouse-server/config.d/no_activity_logs.xml",
        )
        with container:
            host: str = container.get_container_host_ip()
            port: int = int(container.get_exposed_port(8123))
            client: Client = _wait_for_clickhouse_client(host=host, port=port)
            client.close()
            yield E2EClickHouseConnectionSettings(
                host=host,
                port=port,
                username=CLICKHOUSE_USERNAME,
                password=CLICKHOUSE_PASSWORD,
                container_id=container.get_wrapped_container().id,
            )
    except DockerException as error:
        _stop_for_docker_unavailable(service="ClickHouse", error=error)


@pytest.fixture
def isolated_e2e_clickhouse_connection_settings(
    isolated_e2e_network: Network,
    isolated_e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
) -> Iterator[E2EClickHouseConnectionSettings]:
    del isolated_e2e_kafka_connection_settings
    try:
        host_port: int = _reserve_host_port()
        container: DockerContainer = DockerContainer("clickhouse/clickhouse-server:24.8")
        container.with_bind_ports(8123, host_port)
        container.with_env("CLICKHOUSE_USER", CLICKHOUSE_USERNAME)
        container.with_env("CLICKHOUSE_PASSWORD", CLICKHOUSE_PASSWORD)
        container.with_network(isolated_e2e_network)
        container.with_network_aliases("clickhouse")
        with container:
            host: str = container.get_container_host_ip()
            port: int = int(container.get_exposed_port(8123))
            client: Client = _wait_for_clickhouse_client(host=host, port=port)
            client.close()
            yield E2EClickHouseConnectionSettings(
                host=host,
                port=port,
                username=CLICKHOUSE_USERNAME,
                password=CLICKHOUSE_PASSWORD,
                container_id=container.get_wrapped_container().id,
            )
    except DockerException as error:
        _stop_for_docker_unavailable(service="ClickHouse", error=error)


@pytest.fixture(scope="session")
def e2e_clickhouse_client(
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
) -> Iterator[Client]:
    client: Client = clickhouse_connect.get_client(
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="session")
def no_activity_log_clickhouse_client(
    no_activity_log_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
) -> Iterator[Client]:
    client: Client = clickhouse_connect.get_client(
        host=no_activity_log_clickhouse_connection_settings.host,
        port=no_activity_log_clickhouse_connection_settings.port,
        username=no_activity_log_clickhouse_connection_settings.username,
        password=no_activity_log_clickhouse_connection_settings.password,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def isolated_e2e_clickhouse_client(
    isolated_e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
) -> Iterator[Client]:
    client: Client = clickhouse_connect.get_client(
        host=isolated_e2e_clickhouse_connection_settings.host,
        port=isolated_e2e_clickhouse_connection_settings.port,
        username=isolated_e2e_clickhouse_connection_settings.username,
        password=isolated_e2e_clickhouse_connection_settings.password,
    )
    try:
        yield client
    finally:
        client.close()


@pytest.fixture
def e2e_clickhouse_database(e2e_clickhouse_client: Client) -> Iterator[str]:
    database_name: str = f"streambuild_e2e_{uuid.uuid4().hex[:12]}"
    e2e_clickhouse_client.command(f"CREATE DATABASE {database_name}")
    try:
        yield database_name
    finally:
        e2e_clickhouse_client.command(f"DROP DATABASE IF EXISTS {database_name} SYNC")


@pytest.fixture
def no_activity_log_clickhouse_database(
    no_activity_log_clickhouse_client: Client,
) -> Iterator[str]:
    database_name: str = f"streambuild_e2e_{uuid.uuid4().hex[:12]}"
    no_activity_log_clickhouse_client.command(f"CREATE DATABASE {database_name}")
    try:
        yield database_name
    finally:
        no_activity_log_clickhouse_client.command(f"DROP DATABASE IF EXISTS {database_name} SYNC")


@pytest.fixture
def isolated_e2e_clickhouse_database(isolated_e2e_clickhouse_client: Client) -> Iterator[str]:
    database_name: str = f"streambuild_e2e_{uuid.uuid4().hex[:12]}"
    isolated_e2e_clickhouse_client.command(f"CREATE DATABASE {database_name}")
    try:
        yield database_name
    finally:
        isolated_e2e_clickhouse_client.command(f"DROP DATABASE IF EXISTS {database_name} SYNC")


def _reserve_host_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_clickhouse_client(host: str, port: int) -> Client:
    deadline: float = time.time() + CONTAINER_STARTUP_TIMEOUT_SECONDS
    last_error: Exception | None = None
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
