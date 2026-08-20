from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from streambuild.dev_server.classes.state_snapshot import StateSnapshot
from tests.unit.src.streambuild.dev_server._test_types import (
    StateSnapshotTestCase,
    WarehouseRefreshSnapshotTestCase,
)
from tests.unit.src.streambuild.dev_server.helpers import (
    build_snapshot_counting_client,
    failing_state_build,
    recording_state_build,
    sequenced_state_build,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StateSnapshotTestCase(
            description="serves the held overlay to every later request",
            request_count=5,
            expected_build_count=1,
        ),
        StateSnapshotTestCase(
            description="builds once for a single request",
            request_count=1,
            expected_build_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_repeated_requests_when_reading_snapshot_then_one_build_is_reused(
    test_case: StateSnapshotTestCase,
) -> None:
    calls: list[str] = []
    snapshot: StateSnapshot = StateSnapshot(build=recording_state_build(calls))

    _ = [snapshot.current() for _ in range(test_case.request_count)]

    assert len(calls) == test_case.expected_build_count


@pytest.mark.parametrize(
    "test_case",
    [
        StateSnapshotTestCase(
            description="rebuilds after invalidation so new definitions are picked up",
            request_count=2,
            expected_build_count=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalidated_snapshot_when_reading_then_it_rebuilds(
    test_case: StateSnapshotTestCase,
) -> None:
    calls: list[str] = []
    snapshot: StateSnapshot = StateSnapshot(build=recording_state_build(calls))

    _ = snapshot.current()
    snapshot.invalidate()
    reread: dict[str, object] = snapshot.current()

    assert reread["capturedAt"] == "build-2"
    assert len(calls) == test_case.expected_build_count


@pytest.mark.parametrize(
    "test_case",
    [
        StateSnapshotTestCase(
            description="a forced refresh replaces the held overlay",
            request_count=1,
            expected_build_count=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_forced_refresh_when_reading_snapshot_then_latest_overlay_is_served(
    test_case: StateSnapshotTestCase,
) -> None:
    calls: list[str] = []
    snapshot: StateSnapshot = StateSnapshot(build=recording_state_build(calls))

    _ = snapshot.current()
    refreshed: dict[str, object] = snapshot.refresh()

    assert refreshed["capturedAt"] == "build-2"
    assert snapshot.current()["capturedAt"] == "build-2"
    assert len(calls) == test_case.expected_build_count


@pytest.mark.parametrize(
    "test_case",
    [
        StateSnapshotTestCase(
            description="a failing first build propagates instead of serving nothing",
            request_count=1,
            expected_build_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_first_build_when_reading_snapshot_then_error_propagates(
    test_case: StateSnapshotTestCase,
) -> None:
    calls: list[str] = []
    snapshot: StateSnapshot = StateSnapshot(build=failing_state_build(calls))

    with pytest.raises(RuntimeError, match="warehouse unavailable"):
        _ = snapshot.current()

    assert len(calls) == test_case.expected_build_count


@pytest.mark.parametrize(
    "test_case",
    [
        StateSnapshotTestCase(
            description="a failing refresh keeps serving the last good overlay",
            request_count=1,
            expected_build_count=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_refresh_when_reading_snapshot_then_last_good_overlay_survives(
    test_case: StateSnapshotTestCase,
) -> None:
    calls: list[str] = []
    snapshot: StateSnapshot = StateSnapshot(
        build=sequenced_state_build([recording_state_build(calls), failing_state_build(calls)])
    )
    _ = snapshot.current()

    with pytest.raises(RuntimeError, match="warehouse unavailable"):
        _ = snapshot.refresh()

    assert snapshot.current()["capturedAt"] == "build-1"
    assert len(calls) == test_case.expected_build_count


@pytest.mark.parametrize(
    "test_case",
    [
        WarehouseRefreshSnapshotTestCase(
            description="an explicit warehouse refresh discards the held overlay",
            refresh_count=1,
            expected_build_count=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_warehouse_refresh_when_reading_state_then_overlay_is_rebuilt(
    test_case: WarehouseRefreshSnapshotTestCase,
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    client: TestClient = build_snapshot_counting_client(project_dir=tmp_path, calls=calls)
    _ = client.get("/api/state")

    _ = [client.post("/api/warehouse/refresh") for _ in range(test_case.refresh_count)]
    _ = client.get("/api/state")

    assert len(calls) == test_case.expected_build_count
