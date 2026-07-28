"""Public runtime SQL-test artifact path contract."""

from pathlib import Path

from streambuild.cli.compile._helpers.paths import runtime_test_path as _runtime_test_path
from streambuild.compiler.testing.models import SqlTestCase


def runtime_test_path(*, test_case: SqlTestCase) -> Path:
    """Return the target-relative runtime artifact path for one SQL test."""

    return _runtime_test_path(test_case=test_case)
