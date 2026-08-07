import subprocess
from typing import cast

import pytest

from streambuild.dev_server.classes.build_process import BuildProcessManager
from streambuild.dev_server.classes.silent_reporter import SilentDevServerReporter
from tests.unit.src.streambuild.dev_server.classes._test_types import (
    BuildCancellationStateTestCase,
)
from tests.unit.src.streambuild.dev_server.classes.helpers import (
    CancellingProcess,
    expected_interrupt_signal,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildCancellationStateTestCase(
            description="force availability survives cancellation request completion",
            invocation_id="owned-invocation",
            expected_cancel_status="cancelling",
            expected_force_available=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_graceful_cancel_timeout_when_polling_then_force_action_remains_available(
    test_case: BuildCancellationStateTestCase,
) -> None:
    process: CancellingProcess = CancellingProcess()
    manager: BuildProcessManager = BuildProcessManager(reporter=SilentDevServerReporter())
    manager._process = cast(subprocess.Popen[str], process)
    manager._invocation_id = test_case.invocation_id

    result: dict[str, object] = manager.cancel(invocation_id=test_case.invocation_id)
    feed: dict[str, object] = manager.feed(after=0)
    repeated: dict[str, object] = manager.cancel(invocation_id=test_case.invocation_id)

    assert result["status"] == test_case.expected_cancel_status
    assert result["forceAvailable"] is test_case.expected_force_available
    assert feed["forceAvailable"] is test_case.expected_force_available
    assert repeated["forceAvailable"] is test_case.expected_force_available
    assert process.signal_received == expected_interrupt_signal()
    assert process.terminated is True
