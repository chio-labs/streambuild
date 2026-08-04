from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.unit.src.streambuild.dev_server._test_types import StateFieldTestCase
from tests.unit.src.streambuild.dev_server.helpers import (
    build_state_test_client,
    write_dev_server_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StateFieldTestCase(
            description="assembles the live overlay from batched warehouse reads",
            expected_source_freshness="fresh",
            expected_model_freshness="lagging",
            expected_model_lag_seconds=7200.0,
            expected_drift_reasons=("columns", "engine"),
            expected_source_rows_per_second=0.083,
            expected_partition_max_offset=91822,
            expected_bucket_count=60,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_warehouse_reads_when_reading_state_then_assembles_expected_overlay(
    test_case: StateFieldTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    client: TestClient = build_state_test_client(project_dir=tmp_path)

    payload: dict = client.get("/api/state").json()

    model: dict = payload["models"]["orders_clean"]
    assert model["freshness"] == test_case.expected_model_freshness
    assert model["lagSeconds"] == test_case.expected_model_lag_seconds
    assert tuple(sorted(model["driftReasons"])) == test_case.expected_drift_reasons
    assert model["drift"] is True
    source: dict = payload["sources"]["orders"]
    assert source["freshness"] == test_case.expected_source_freshness
    assert source["rowsPerSecond"] == test_case.expected_source_rows_per_second
    assert source["partitions"][0]["maxOffset"] == test_case.expected_partition_max_offset
    assert len(source["throughput"]["buckets"]) == test_case.expected_bucket_count
    assert sum(source["throughput"]["buckets"]) == 300
