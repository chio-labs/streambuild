from __future__ import annotations

import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib import request

from verify_demo import clickhouse_row

PROJECT_DIR = Path(__file__).resolve().parents[1]
API_ROOT = "http://127.0.0.1:8000/api"
AUDIT_NAME = "orders_no_future_events"


def get_json(path: str) -> dict[str, object]:
    with request.urlopen(f"{API_ROOT}{path}", timeout=20) as response:
        return cast(dict[str, object], json.loads(response.read()))


def run_audit() -> dict[str, object]:
    http_request = request.Request(
        f"{API_ROOT}/checks/run",
        data=json.dumps({"kind": "audit", "name": AUDIT_NAME}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=20) as response:
        return cast(dict[str, object], json.loads(response.read()))


def sensor_ticks() -> list[dict[str, object]]:
    payload = get_json("/sensors/quality_alerts/ticks")
    return cast(list[dict[str, object]], payload["ticks"])


def compose_message(event_id: str) -> str | None:
    escaped_event_id = event_id.replace("'", "''")
    row = clickhouse_row(
        f"""
        SELECT coalesce(argMax(result_json, recorded_at), '') AS result_json
        FROM _streambuild_sensor_steps
        WHERE sensor_name = 'quality_alerts'
          AND event_id = '{escaped_event_id}'
          AND step_key = 'compose'
          AND status = 'succeeded'
        """
    )
    encoded = str(row["result_json"])
    return None if not encoded else str(json.loads(encoded))


def main() -> None:
    previous_tick_ids = {str(tick["tickId"]) for tick in sensor_ticks()}
    injection = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker/compose.yml",
            "run",
            "--rm",
            "--no-deps",
            "-e",
            "FUTURE_EVENT_SECONDS=20",
            "producer",
            "python",
            "-u",
            "/app/producer/fake_orders_producer.py",
            "inject-future",
        ],
        cwd=PROJECT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    print(injection.stdout.strip())

    warning_deadline = time.monotonic() + 8
    warning = run_audit()
    while warning["passed"] is True and time.monotonic() < warning_deadline:
        time.sleep(0.5)
        warning = run_audit()
    assert warning["passed"] is False, warning
    assert warning["severity"] == "warning", warning
    assert int(cast(int, warning["failingRowCount"])) >= 1, warning
    assert cast(list[object], warning["sampleRows"]), warning

    sample_rows = cast(list[list[object]], warning["sampleRows"])
    sample_event_id = str(sample_rows[0][0])
    event_at = datetime.fromisoformat(str(sample_rows[0][2])).replace(tzinfo=UTC)
    time.sleep(max(0.0, event_at.timestamp() - time.time() + 1.0))
    recovery = run_audit()
    assert recovery["passed"] is True, recovery

    deadline = time.monotonic() + 25
    messages: list[str] = []
    while time.monotonic() < deadline:
        new_ticks = [
            tick
            for tick in sensor_ticks()
            if str(tick["tickId"]) not in previous_tick_ids and tick["status"] == "succeeded"
        ]
        messages = [
            message
            for tick in new_ticks
            if (message := compose_message(str(tick["eventId"]))) is not None
        ]
        if any(message.startswith("WARNING:") for message in messages) and any(
            message.startswith("RECOVERED:") for message in messages
        ):
            break
        time.sleep(1)
    warning_message = next(
        (message for message in messages if message.startswith("WARNING:")), None
    )
    recovery_message = next(
        (message for message in messages if message.startswith("RECOVERED:")), None
    )
    assert warning_message is not None, "warning sensor event was not handled successfully"
    assert recovery_message is not None, "recovery sensor event was not handled successfully"
    assert sample_event_id in warning_message
    assert "http://127.0.0.1:8000/quality?audit=orders_no_future_events" in warning_message
    assert "http://127.0.0.1:8000/quality?audit=orders_no_future_events" in recovery_message
    print("verified sampled warning, natural recovery, and two successful sensor deliveries")


if __name__ == "__main__":
    main()
