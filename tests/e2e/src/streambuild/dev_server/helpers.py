import json
import os
import signal
import socket
import subprocess
import time
from pathlib import Path
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from clickhouse_connect.driver.client import Client


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
) -> None:
    deadline: float = time.monotonic() + 30
    result_count = 0
    while result_count != 1:
        assert time.monotonic() < deadline, "scheduled result did not arrive before timeout"
        assert all(process.poll() is None for process in processes), (
            f"stb dev exited before scheduling completed: "
            f"{tuple(process.returncode for process in processes)}"
        )
        result_count = int(
            client.query(
                f"SELECT count() FROM {database}._streambuild_node_results "
                "WHERE trigger = 'scheduled'"
            ).result_rows[0][0]
        )
        time.sleep(0.1)


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
