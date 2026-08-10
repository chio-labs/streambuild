import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.src.streambuild.conftest import (
    E2EClickHouseConnectionSettings,
    E2EKafkaConnectionSettings,
)
from tests.e2e.src.streambuild.dev_server.helpers import (
    available_port,
    start_dev_process,
    stop_process,
    wait_for_state_api,
)
from tests.e2e.src.streambuild.executor.helpers import (
    E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
    prepare_authored_e2e_project,
)


@pytest.fixture
def running_lineage_server(
    e2e_clickhouse_connection_settings: E2EClickHouseConnectionSettings,
    e2e_kafka_connection_settings: E2EKafkaConnectionSettings,
    e2e_clickhouse_database: str,
    output_path: str,
    tmp_path: Path,
) -> Iterator[tuple[str, dict[str, object], Path]]:
    project_dir: Path = prepare_authored_e2e_project(
        fixture_project_dir=E2E_KAFKA_TIMESTAMP_PROJECT_DIR,
        tmp_path=tmp_path,
        kafka_broker_list=e2e_kafka_connection_settings.bootstrap_server,
        topic_suffix=e2e_clickhouse_database,
    )
    api_port: int = available_port()
    log_path: Path = Path(output_path) / "stb-dev.log"
    process: subprocess.Popen[str] = start_dev_process(
        repository_root=Path(__file__).resolve().parents[5],
        project_dir=project_dir,
        host=e2e_clickhouse_connection_settings.host,
        port=e2e_clickhouse_connection_settings.port,
        username=e2e_clickhouse_connection_settings.username,
        password=e2e_clickhouse_connection_settings.password,
        database=e2e_clickhouse_database,
        api_port=api_port,
        log_path=log_path,
    )
    try:
        state_payload: dict[str, object] = wait_for_state_api(
            process=process, api_port=api_port, log_path=log_path
        )
        yield f"http://127.0.0.1:{api_port}", state_payload, log_path
    finally:
        stop_process(process)
