from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from streambuild.dev_server.classes.dev_server_state import DevServerState
from streambuild.dev_server.main._create_dev_app import create_dev_app
from tests.unit.src.streambuild.dev_server._test_types import (
    ChecksRunTestCase,
    PlanEndpointTestCase,
)
from tests.unit.src.streambuild.dev_server.helpers import (
    FakeEmptyResultConnection,
    build_compile_callable,
    build_fake_state_connection,
    build_state_test_client,
    write_dev_server_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PlanEndpointTestCase(
            description="plans the selected model closure against the fake warehouse",
            selectors=("orders_clean",),
            expected_status=200,
            expected_entry_names=("orders_clean",),
            expected_command="stb build --select orders_clean",
        ),
        PlanEndpointTestCase(
            description="expands a pipeline selector to its models",
            selectors=("pipeline:order_events",),
            expected_status=200,
            expected_entry_names=("orders_clean",),
            expected_command="stb build --select pipeline:order_events",
        ),
        PlanEndpointTestCase(
            description="rejects an unknown selector with a clear message",
            selectors=("nonsense+",),
            expected_status=400,
            expected_entry_names=(),
            expected_command="",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selectors_when_planning_then_returns_expected_plan(
    test_case: PlanEndpointTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    client: TestClient = build_state_test_client(project_dir=tmp_path)
    params: list[tuple[str, str]] = [("select", selector) for selector in test_case.selectors]

    response: object = client.get("/api/plan", params=params)

    assert response.status_code == test_case.expected_status
    payload_entries: tuple = tuple(
        entry["modelName"] for entry in response.json().get("entries", ())
    )
    assert payload_entries == test_case.expected_entry_names
    assert response.json().get("command", "") == test_case.expected_command


@pytest.mark.parametrize(
    "test_case",
    [
        ChecksRunTestCase(
            description="runs one audit and reports a pass on zero failing rows",
            kind="audit",
            name="orders_clean.order_id.not_null.1",
            expected_status=200,
            expected_passed=True,
        ),
        ChecksRunTestCase(
            description="rejects an unknown audit name",
            kind="audit",
            name="missing_audit",
            expected_status=400,
            expected_passed=False,
        ),
        ChecksRunTestCase(
            description="rejects an unsupported check kind",
            kind="lint",
            name="anything",
            expected_status=400,
            expected_passed=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_check_request_when_running_then_returns_expected_result(
    test_case: ChecksRunTestCase,
    tmp_path: Path,
) -> None:
    write_dev_server_project(project_dir=tmp_path)
    state: DevServerState = DevServerState(run_compile=build_compile_callable(project_dir=tmp_path))
    connection: FakeEmptyResultConnection = FakeEmptyResultConnection(
        catalog=build_fake_state_connection()._catalog,
        ownership=(),
        results_by_query={},
        warehouse_timestamp="2026-08-03 12:00:00.000",
    )
    client: TestClient = TestClient(
        create_dev_app(state=state, connection=connection, database="analytics")
    )

    response: object = client.post(
        "/api/checks/run", json={"kind": test_case.kind, "name": test_case.name}
    )

    assert response.status_code == test_case.expected_status
    assert response.json().get("passed", False) is test_case.expected_passed
