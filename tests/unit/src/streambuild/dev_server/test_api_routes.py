from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.unit.src.streambuild.dev_server._test_types import StatusEndpointTestCase
from tests.unit.src.streambuild.dev_server.helpers import (
    break_project_compile,
    build_test_client,
    write_dev_server_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StatusEndpointTestCase(
            description="reports a servable compile and a missing warehouse",
            break_compile=False,
            expected_state="ok",
            expected_warehouse_connected=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_clean_project_when_reading_status_then_reports_ok(
    test_case: StatusEndpointTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    client: TestClient = build_test_client(project_dir=tmp_path)

    payload: dict = client.get("/api/status").json()

    assert payload["compile"]["state"] == test_case.expected_state
    assert payload["compile"]["error"] is None
    assert payload["warehouse"]["connected"] is test_case.expected_warehouse_connected


@pytest.mark.parametrize(
    "test_case",
    [
        StatusEndpointTestCase(
            description="reload reports the failure with its source location",
            break_compile=True,
            expected_state="failing",
            expected_warehouse_connected=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_broken_project_when_reloading_then_reports_failure_location(
    test_case: StatusEndpointTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    client: TestClient = build_test_client(project_dir=tmp_path)
    first_version: str = client.get("/api/status").json()["compile"]["versionKey"]
    break_project_compile(project_dir=tmp_path)

    payload: dict = client.post("/api/reload").json()

    assert payload["compile"]["state"] == test_case.expected_state
    assert payload["compile"]["versionKey"] != first_version
    assert "broken.sql" in payload["compile"]["error"]["message"]
    definitions_status: int = client.get("/api/definitions").status_code
    assert definitions_status == 409
