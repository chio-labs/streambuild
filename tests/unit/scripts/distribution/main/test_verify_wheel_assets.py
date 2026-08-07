from pathlib import Path

import pytest

from scripts.distribution.exceptions import DistributionVerificationError
from scripts.distribution.main.verify_wheel_assets import verify_wheel_assets
from tests.unit.scripts.distribution.main._test_types import (
    InvalidWheelAssetsTestCase,
    ValidWheelAssetsTestCase,
)
from tests.unit.scripts.distribution.main.helpers import write_wheel

_WHEEL_NAME: str = "streambuild-0.8.1-py3-none-any.whl"


@pytest.mark.parametrize(
    "test_case",
    [
        ValidWheelAssetsTestCase(
            description="wheel contains the development UI entry point and application bundle",
            archive_names=(
                "streambuild/dev_server/static/index.html",
                "streambuild/dev_server/static/_app/immutable/entry/start.js",
            ),
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_complete_wheel_when_verifying_assets_then_returns_success(
    tmp_path: Path, test_case: ValidWheelAssetsTestCase
) -> None:
    _ = write_wheel(
        distribution_dir=tmp_path,
        wheel_name=_WHEEL_NAME,
        archive_names=test_case.archive_names,
    )

    result: int = verify_wheel_assets(distribution_dir=tmp_path)

    assert result == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidWheelAssetsTestCase(
            description="wheel omits the development UI entry point",
            archive_names=("streambuild/dev_server/static/_app/immutable/entry/start.js",),
            expected_message_fragment="missing required UI asset",
        ),
        InvalidWheelAssetsTestCase(
            description="wheel omits the development UI application bundle",
            archive_names=("streambuild/dev_server/static/index.html",),
            expected_message_fragment="missing the UI application bundle",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_incomplete_wheel_when_verifying_assets_then_raises_error(
    tmp_path: Path, test_case: InvalidWheelAssetsTestCase
) -> None:
    _ = write_wheel(
        distribution_dir=tmp_path,
        wheel_name=_WHEEL_NAME,
        archive_names=test_case.archive_names,
    )

    with pytest.raises(DistributionVerificationError) as error_info:
        _ = verify_wheel_assets(distribution_dir=tmp_path)

    assert test_case.expected_message_fragment in str(error_info.value)
