import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from shutil import copytree
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from clickhouse_connect.driver.client import Client

LINEAGE_BROWSER_PROJECT_DIR: Path = Path("tests/fixtures/lineage_browser_project")


def read_json_url(url: str, *, timeout_seconds: float = 10) -> object:
    try:
        with urlopen(  # noqa: S310 - loopback test server only
            url, timeout=timeout_seconds
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(error.read().decode("utf-8")) from error


def post_json_url(url: str, payload: dict[str, object]) -> object:
    request: Request = Request(  # noqa: S310 - loopback test server only
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310 - loopback test server only
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise RuntimeError(error.read().decode("utf-8")) from error


def prepare_lineage_browser_project(*, tmp_path: Path) -> Path:
    project_dir: Path = tmp_path / LINEAGE_BROWSER_PROJECT_DIR.name
    _ = copytree(LINEAGE_BROWSER_PROJECT_DIR, project_dir)
    return project_dir


def prepare_catalog_pipeline_browser_project(*, tmp_path: Path) -> Path:
    project_dir: Path = prepare_lineage_browser_project(tmp_path=tmp_path)
    (project_dir / "pipelines" / "moving_events" / "derived_moving_orders.sql").write_text(
        'MODEL (\n  engine "MergeTree()",\n  order_by ["order_id"]\n);\n\n'
        "SELECT\n  order_id::String AS order_id,\n"
        "  _replay_timestamp::DateTime64(3) AS _replay_timestamp\n"
        'FROM __ref("moving_orders")\n',
        encoding="utf-8",
    )
    return project_dir


def create_lineage_browser_source_tables(*, client: Client, database: str) -> None:
    for relation_name in (
        "browser_moving_events",
        "browser_idle_events",
        "browser_stalled_events",
    ):
        client.command(
            f"CREATE TABLE {database}.{relation_name} "
            "(order_id String, event_timestamp DateTime64(3), "
            "_replay_partition Int64 DEFAULT 0, _replay_offset Int64 DEFAULT 0, "
            "_replay_landed_at DateTime64(3) DEFAULT now64(3)) "
            "ENGINE = MergeTree ORDER BY (event_timestamp, order_id)"
        )


def run_lineage_browser_build(
    *,
    repository_root: Path,
    project_dir: Path,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
) -> None:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(repository_root / ".venv" / "bin" / "stb"),
            "build",
            "--project-dir",
            str(project_dir),
            "--host",
            host,
            "--port",
            str(port),
            "--username",
            username,
            "--password",
            password,
            "--database",
            database,
            "--auto-approve",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"lineage browser build failed with code {result.returncode}. "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def seed_lineage_exact_activity(*, client: Client, database: str) -> None:
    client.command(
        f"INSERT INTO {database}.browser_moving_events (order_id, event_timestamp) "
        "VALUES ('101', now64(3))"
    )
    client.command(
        f"INSERT INTO {database}.browser_idle_events (order_id, event_timestamp) "
        "VALUES ('idle', now64(3))"
    )
    try:
        client.command(
            f"INSERT INTO {database}.browser_stalled_events (order_id, event_timestamp) "
            "VALUES ('not-a-number', now64(3))"
        )
    except Exception as error:
        assert "Cannot parse" in str(error) or "CANNOT_PARSE" in str(error)
    else:
        raise AssertionError("stalled activity probe unexpectedly succeeded")
    client.command("SYSTEM FLUSH LOGS")


def seed_lineage_approximate_activity(*, client: Client, database: str) -> None:
    client.command(
        f"INSERT INTO {database}.browser_moving_events (order_id, event_timestamp) "
        "VALUES ('101', now64(3))"
    )


def seed_lineage_plan_replay_data(*, client: Client, database: str) -> None:
    client.command(
        f"INSERT INTO {database}.browser_moving_events "
        "(order_id, event_timestamp, _replay_landed_at) VALUES "
        "('plan-oldest', now64(3) - INTERVAL 3 DAY, now64(3) - INTERVAL 3 DAY), "
        "('plan-middle', now64(3) - INTERVAL 2 DAY, now64(3) - INTERVAL 2 DAY), "
        "('plan-newest', now64(3) - INTERVAL 1 DAY, now64(3) - INTERVAL 1 DAY)"
    )


def start_dev_process(
    *,
    repository_root: Path,
    project_dir: Path,
    host: str,
    port: int,
    username: str,
    password: str,
    database: str,
    api_port: int,
    log_path: Path,
) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        return subprocess.Popen(
            [
                str(repository_root / ".venv" / "bin" / "stb"),
                "dev",
                "--project-dir",
                str(project_dir),
                "--host",
                host,
                "--port",
                str(port),
                "--username",
                username,
                "--password",
                password,
                "--database",
                database,
                "--ui-host",
                "127.0.0.1",
                "--ui-port",
                str(api_port),
            ],
            cwd=repository_root,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )


def wait_for_scheduler_api(
    *, process: subprocess.Popen[str], api_port: int, log_path: Path
) -> dict[str, object]:
    deadline: float = time.monotonic() + 30
    while True:
        try:
            return cast(
                dict[str, object],
                read_json_url(f"http://127.0.0.1:{api_port}/api/audit-scheduler"),
            )
        except (OSError, RuntimeError):
            pass
        assert process.poll() is None, _process_failure(
            message="stb dev exited before API readiness", process=process, log_path=log_path
        )
        assert time.monotonic() < deadline, _process_failure(
            message="stb dev API did not become ready before timeout",
            process=process,
            log_path=log_path,
        )
        time.sleep(0.1)


def wait_for_state_api(
    *, process: subprocess.Popen[str], api_port: int, log_path: Path
) -> dict[str, object]:
    deadline: float = time.monotonic() + 30
    while True:
        try:
            payload: object = read_json_url(
                f"http://127.0.0.1:{api_port}/api/state", timeout_seconds=1
            )
            assert isinstance(payload, dict), "state payload is not an object"
            state_payload: dict[str, object] = cast(dict[str, object], payload)
            assert isinstance(state_payload.get("capturedAt"), str), (
                "state payload has no capturedAt timestamp"
            )
            assert isinstance(state_payload.get("models"), dict), (
                "state payload has no models object"
            )
            assert isinstance(state_payload.get("sources"), dict), (
                "state payload has no sources object"
            )
            return state_payload
        except (AssertionError, OSError, RuntimeError):
            pass
        assert process.poll() is None, _process_failure(
            message="stb dev exited before state API readiness",
            process=process,
            log_path=log_path,
        )
        assert time.monotonic() < deadline, _process_failure(
            message="stb dev state API did not become ready before timeout",
            process=process,
            log_path=log_path,
        )
        time.sleep(0.1)


def wait_for_scheduled_result(
    *,
    processes: tuple[subprocess.Popen[str], ...],
    client: Client,
    database: str,
    expected_count: int = 1,
) -> None:
    deadline: float = time.monotonic() + 30
    result_count = 0
    while result_count < expected_count:
        assert time.monotonic() < deadline, "scheduled result did not arrive before timeout"
        assert all(process.poll() is None for process in processes), (
            f"stb dev exited before scheduling completed: "
            f"{tuple(process.returncode for process in processes)}"
        )
        result_count = int(
            client.query(
                "SELECT coalesce(sum(rows), 0) FROM system.parts "
                f"WHERE database = '{database}' "
                "AND table = '_streambuild_node_results' AND active = 1"
            ).result_rows[0][0]
        )
        time.sleep(0.1)
    assert result_count == expected_count


def stop_process(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def _process_failure(*, message: str, process: subprocess.Popen[str], log_path: Path) -> str:
    try:
        log_contents: str = log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        log_contents = "<log file was not created>"
    return (
        f"{message}: returncode={process.poll()}, log={log_path}\n"
        f"--- stb dev output ---\n{log_contents}"
    )


def available_port() -> int:
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        return int(port_socket.getsockname()[1])
