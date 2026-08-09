import subprocess
from pathlib import Path
from typing import cast

import pytest

from streambuild.dev_server.classes.build_process import BuildProcessManager
from streambuild.dev_server.classes.silent_reporter import SilentDevServerReporter
from streambuild.executor.observability.constants import RUN_INVOCATION_ID_ENV_VAR
from tests.unit.src.streambuild.dev_server.classes._test_types import (
    BuildCancellationStateTestCase,
    BuildStartTestCase,
)
from tests.unit.src.streambuild.dev_server.classes.helpers import (
    CancellingProcess,
    PendingBuildProcess,
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


@pytest.mark.parametrize(
    "test_case",
    [
        BuildStartTestCase(
            description="child launch returns its owned identity before run start",
            selector="orders",
            expected_status="starting",
            expected_running=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_child_has_not_started_when_launching_then_returns_owned_identity_immediately(
    test_case: BuildStartTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process: PendingBuildProcess = PendingBuildProcess()
    child_environment: dict[str, str] = {}

    def start_process(*args: object, **kwargs: object) -> PendingBuildProcess:
        del args
        child_environment.update(cast(dict[str, str], kwargs["env"]))
        return process

    monkeypatch.setattr(subprocess, "Popen", start_process)
    manager: BuildProcessManager = BuildProcessManager(reporter=SilentDevServerReporter())

    result: dict[str, object] = manager.start(
        project_dir=Path("/project"),
        selectors=(test_case.selector,),
        start_time=None,
    )
    feed: dict[str, object] = manager.feed(after=0)

    assert result["status"] == test_case.expected_status
    assert result["invocationId"] == feed["invocationId"]
    assert feed["running"] is test_case.expected_running
    assert feed["currentInvocationId"] is None
    assert child_environment[RUN_INVOCATION_ID_ENV_VAR] == result["invocationId"]
    process.finish()
