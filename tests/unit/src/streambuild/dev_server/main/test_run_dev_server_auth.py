from pathlib import Path
from unittest.mock import MagicMock

import pytest

from streambuild.auth.models import AuthSettings
from streambuild.auth.types import AuthenticationMode
from streambuild.dev_server.main.run_dev_server import _is_loopback_bind, run_dev_server
from tests.unit.src.streambuild.dev_server.main._test_types import AuthBindTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        AuthBindTestCase(
            description="only loopback names and addresses",
            expected_result=(True, True, True, False, False),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bind_host_when_checking_disabled_auth_then_only_loopback_is_allowed(
    test_case: AuthBindTestCase,
) -> None:
    assert (
        _is_loopback_bind("127.0.0.1"),
        _is_loopback_bind("::1"),
        _is_loopback_bind("localhost"),
        _is_loopback_bind("0.0.0.0"),
        _is_loopback_bind("streambuild.internal"),
    ) == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [AuthBindTestCase(description="disabled shared bind rejected", expected_result=1)],
    ids=lambda case: case.description,
)
def test_given_disabled_auth_when_starting_on_shared_bind_then_startup_is_rejected(
    test_case: AuthBindTestCase, tmp_path: Path
) -> None:
    result: int = run_dev_server(
        run_compile=MagicMock(),
        connection=None,
        observation_connection=None,
        database=None,
        project_dir=tmp_path,
        host="0.0.0.0",
        port=8000,
        reporter=MagicMock(),
        auth_settings=AuthSettings(
            mode=AuthenticationMode.DISABLED,
            control_store_url="unused",
        ),
    )

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [AuthBindTestCase(description="insecure shared cookie rejected", expected_result=1)],
    ids=lambda case: case.description,
)
def test_given_insecure_password_cookie_when_starting_on_shared_bind_then_startup_is_rejected(
    test_case: AuthBindTestCase, tmp_path: Path
) -> None:
    result: int = run_dev_server(
        run_compile=MagicMock(),
        connection=None,
        observation_connection=None,
        database=None,
        project_dir=tmp_path,
        host="0.0.0.0",
        port=8000,
        reporter=MagicMock(),
        auth_settings=AuthSettings(
            mode=AuthenticationMode.PASSWORD,
            control_store_url="unused",
            session_cookie_secure=False,
        ),
    )

    assert result == test_case.expected_result


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
