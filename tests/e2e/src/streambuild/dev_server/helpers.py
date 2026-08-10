import json
import socket
import subprocess
import time
from pathlib import Path
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from clickhouse_connect.driver.client import Client


def read_json_url(url: str) -> object:
    try:
        with urlopen(url, timeout=10) as response:  # noqa: S310 - loopback test server only
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
) -> subprocess.Popen[str]:
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_scheduler_api(*, process: subprocess.Popen[str], api_port: int) -> dict[str, object]:
    deadline: float = time.monotonic() + 30
    while True:
        try:
            return cast(
                dict[str, object],
                read_json_url(f"http://127.0.0.1:{api_port}/api/audit-scheduler"),
            )
        except (OSError, RuntimeError):
            pass
        assert process.poll() is None, f"stb dev exited before API readiness: {process.returncode}"
        assert time.monotonic() < deadline, "stb dev API did not become ready before timeout"
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
                "SELECT coalesce(sum(rows), 0) FROM system.parts "
                f"WHERE database = '{database}' "
                "AND table = '_streambuild_node_results' AND active = 1"
            ).result_rows[0][0]
        )
        time.sleep(0.1)


def stop_process(process: subprocess.Popen[str]) -> None:
    try:
        process.terminate()
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def available_port() -> int:
    with socket.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        return int(port_socket.getsockname()[1])
