import threading
from collections.abc import Callable
from typing import cast
from unittest.mock import MagicMock

import pytest

from streambuild.adapter.classes.adapter_connection import AdapterConnection
from streambuild.dev_server.classes.warehouse_runtime import WarehouseRuntime
from tests.unit.src.streambuild.dev_server.classes._test_types import (
    WarehouseRuntimeRecoveryTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        WarehouseRuntimeRecoveryTestCase(
            description="initial warehouse failure recovers in the background",
            failure_message="warehouse is starting",
            expected_attempts=2,
            expected_state="connected",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_connection_failure_when_recovering_then_runtime_connects(
    test_case: WarehouseRuntimeRecoveryTestCase,
) -> None:
    connection_mock: MagicMock = MagicMock()
    observation_connection_mock: MagicMock = MagicMock()
    connection: AdapterConnection = cast(AdapterConnection, connection_mock)
    observation_connection: AdapterConnection = cast(AdapterConnection, observation_connection_mock)
    connect: MagicMock = MagicMock(
        side_effect=[RuntimeError(test_case.failure_message), connection]
    )

    runtime: WarehouseRuntime = WarehouseRuntime(
        connection=None,
        observation_connection=observation_connection,
        connection_factory=cast(Callable[[], AdapterConnection], connect),
        observation_connection_factory=None,
        database="analytics",
    )

    runtime.start()
    threading.Event().wait(timeout=2.0)
    status: dict[str, object] = runtime.status()
    runtime.close()

    assert connect.call_count == test_case.expected_attempts
    assert status["state"] == test_case.expected_state
    assert status["connected"] is True
    assert status["error"] is None
    connection_mock.close.assert_called_once()
    observation_connection_mock.close.assert_not_called()


@pytest.mark.parametrize(
    "test_case",
    [
        WarehouseRuntimeRecoveryTestCase(
            description="established connection degrades and recovers without replacement",
            failure_message="warehouse stopped",
            expected_attempts=2,
            expected_state="connected",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_established_connection_when_probe_fails_then_same_client_can_recover(
    test_case: WarehouseRuntimeRecoveryTestCase,
) -> None:
    connection_mock: MagicMock = MagicMock()
    connection_mock.capture_warehouse_timestamp.side_effect = [
        RuntimeError(test_case.failure_message),
        "2026-08-18 03:00:00.000",
    ]
    runtime: WarehouseRuntime = WarehouseRuntime(
        connection=cast(AdapterConnection, connection_mock),
        observation_connection=None,
        connection_factory=None,
        observation_connection_factory=None,
        database="analytics",
    )

    first_probe: bool = runtime.connect_now()
    degraded: dict[str, object] = runtime.status()
    recovered: bool = runtime.connect_now()
    status: dict[str, object] = runtime.status()
    runtime.close()

    assert first_probe is False
    assert degraded["connected"] is False
    assert test_case.failure_message in str(degraded["error"])
    assert recovered is True
    assert connection_mock.capture_warehouse_timestamp.call_count == test_case.expected_attempts
    assert status["state"] == test_case.expected_state
    assert status["error"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
