from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response

from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.main._create_dev_app import create_dev_app
from tests.unit.src.streambuild.dev_server._test_types import (
    DevAppLifespanTestCase,
    StateRouteErrorTestCase,
    StatusEndpointTestCase,
)
from tests.unit.src.streambuild.dev_server.helpers import (
    break_project_compile,
    build_compile_callable,
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


@pytest.mark.parametrize(
    "test_case",
    [
        StateRouteErrorTestCase(
            description="state route reports a missing warehouse as unavailable",
            expected_status=503,
            expected_detail="no warehouse connection",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_warehouse_when_reading_state_then_route_returns_explicit_error(
    test_case: StateRouteErrorTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    client: TestClient = build_test_client(project_dir=tmp_path)

    response: Response = client.get("/api/state")

    assert response.status_code == test_case.expected_status
    assert response.json() == {"detail": test_case.expected_detail}


@pytest.mark.parametrize(
    "test_case",
    [
        DevAppLifespanTestCase(
            description="application lifespan starts and closes every owned background resource",
            expected_status=200,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dev_app_context_when_lifespan_exits_then_owned_resources_are_closed(
    test_case: DevAppLifespanTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    state: DevServerState = DevServerState(run_compile=build_compile_callable(project_dir=tmp_path))
    with (
        patch("streambuild.dev_server.main._create_dev_app.AuditScheduler") as scheduler_class,
        patch("streambuild.dev_server.main._create_dev_app.BuildProcessManager") as builds_class,
        patch("streambuild.dev_server.main._create_dev_app.KafkaLagReader") as lag_reader_class,
        patch("streambuild.dev_server.main._create_dev_app.KafkaTopicReader") as topic_reader_class,
    ):
        scheduler: MagicMock = scheduler_class.return_value
        builds: MagicMock = builds_class.return_value
        lag_reader: MagicMock = lag_reader_class.return_value
        topic_reader: MagicMock = topic_reader_class.return_value
        lag_reader.read.return_value = None
        topic_reader.read.return_value = None
        app: FastAPI = create_dev_app(state=state, project_dir=tmp_path)

        with TestClient(app) as client:
            response: Response = client.get("/api/status")
            assert response.status_code == test_case.expected_status
            scheduler.start.assert_called_once_with()

        scheduler.close.assert_called_once_with()
        lag_reader.close.assert_called_once_with()
        topic_reader.close.assert_called_once_with()
        builds.close.assert_called_once_with()
