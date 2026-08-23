from __future__ import annotations

import base64
import json
import os
import subprocess
from pathlib import Path
from typing import cast
from urllib import request

PROJECT_DIR = Path(__file__).resolve().parents[1]
CLICKHOUSE_URL = (
    f"http://{os.getenv('STREAMBUILD_CLICKHOUSE_HOST', 'localhost')}:"
    f"{os.getenv('STREAMBUILD_CLICKHOUSE_PORT', '18123')}/?database=orders_demo"
)
STATE_URL = "http://127.0.0.1:8000/api/state"
TOPIC = "source.order_events.live"


def clickhouse_row(query: str) -> dict[str, object]:
    http_request = request.Request(
        CLICKHOUSE_URL,
        data=f"{query} FORMAT JSONEachRow".encode(),
        headers={
            "Authorization": "Basic "
            + base64.b64encode(
                (
                    f"{os.getenv('STREAMBUILD_CLICKHOUSE_USERNAME', 'clickhouse')}:"
                    f"{os.getenv('STREAMBUILD_CLICKHOUSE_PASSWORD', 'clickhouse')}"
                ).encode()
            ).decode("ascii")
        },
        method="POST",
    )
    with request.urlopen(http_request, timeout=20) as response:
        return cast(dict[str, object], json.loads(response.read()))


def state_payload() -> dict[str, object]:
    with request.urlopen(STATE_URL, timeout=20) as response:
        return cast(dict[str, object], json.loads(response.read()))


def topic_description() -> str:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker/compose.yml",
            "exec",
            "-T",
            "redpanda",
            "rpk",
            "topic",
            "describe",
            TOPIC,
        ],
        cwd=PROJECT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def main() -> None:
    topic = topic_description()
    assert "PARTITIONS  3" in topic, topic
    assert "retention.ms" in topic and "604800000" in topic, topic

    counts = clickhouse_row(
        """
        SELECT
          (SELECT uniqExact(JSONExtractString(kafka_value, 'event_id'))
           FROM raw__commerce_event_stream) AS source_events,
          (SELECT uniqExact(event_id) FROM tbl__commerce_events) AS commerce_events,
          (SELECT uniqExact(event_id) FROM tbl__order_events) AS order_events,
          (SELECT uniqExact(event_id) FROM tbl__order_event_facts) AS fact_events,
          (SELECT count() FROM tbl__order_events
           WHERE region_name NOT IN (
             'US East', 'US West', 'Europe West', 'Asia Pacific South'
           )) AS invalid_regions
        """
    )
    logical_counts = {
        int(str(counts["source_events"])),
        int(str(counts["commerce_events"])),
        int(str(counts["order_events"])),
        int(str(counts["fact_events"])),
    }
    assert len(logical_counts) == 1, counts
    assert int(str(counts["source_events"])) > 0, counts
    assert int(str(counts["invalid_regions"])) == 0, counts

    state = state_payload()
    models = cast(dict[str, dict[str, object]], state["models"])
    sources = cast(dict[str, dict[str, object]], state["sources"])
    source = sources["commerce_event_stream"]
    assert set(models) == {"commerce_events", "order_events", "order_event_facts", "commerce_kpis"}
    assert models["commerce_kpis"]["freshness"] is None
    assert all(not bool(model["drift"]) for model in models.values())
    partitions = cast(list[dict[str, object]], source["partitions"])
    assert len(partitions) == 3
    assert all(isinstance(partition["kafkaLagMessages"], int) for partition in partitions)

    print(
        "verified 3 retained Kafka partitions, 4 drift-free models, unknown view freshness, "
        f"and {counts['source_events']} consistent logical events"
    )


if __name__ == "__main__":
    main()
