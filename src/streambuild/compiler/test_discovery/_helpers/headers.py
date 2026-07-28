"""Apache-2.0: SQLBuild discovery/_helpers/sql/tests.py header parsing@7e3b2f854f05."""

from __future__ import annotations

from pathlib import Path

import yaml

from streambuild.compiler.test_discovery.constants import (
    DEFAULT_SQL_TEST_MODE,
    SUPPORTED_SQL_TEST_MODES,
    TEST_HEADER_MODE_KEY,
    TEST_HEADER_NAME_KEY,
    TEST_HEADER_SUPPORTED_KEYS,
)
from streambuild.compiler.test_discovery.exceptions import SqlTestParseError
from streambuild.compiler.test_discovery.models import SqlTestHeader
from streambuild.compiler.test_discovery.types import SqlTestMode


def parse_test_header(*, file_path: Path, header_contents: str) -> SqlTestHeader:
    """Parse one TEST(...) header into its optional name and effective mode."""

    stripped_header_contents: str = header_contents.strip()
    if not stripped_header_contents:
        return SqlTestHeader(name=None, mode=DEFAULT_SQL_TEST_MODE)
    parsed_header: dict[str, object] = _parse_header_mapping(
        file_path=file_path, header_contents=stripped_header_contents
    )
    _reject_unsupported_keys(file_path=file_path, parsed_header=parsed_header)
    return SqlTestHeader(
        name=_parse_name(file_path=file_path, value=parsed_header.get(TEST_HEADER_NAME_KEY)),
        mode=_parse_mode(file_path=file_path, value=parsed_header.get(TEST_HEADER_MODE_KEY)),
    )


def _parse_header_mapping(*, file_path: Path, header_contents: str) -> dict[str, object]:
    try:
        parsed_header: object = yaml.safe_load(f"{{{header_contents}}}")
    except yaml.YAMLError as error:
        raise SqlTestParseError(
            f"TEST() header in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(parsed_header, dict):
        raise SqlTestParseError(
            f"TEST() header in '{file_path}' must be a mapping like `TEST (name: \"...\");`"
        )
    return {str(key): value for key, value in parsed_header.items()}


def _reject_unsupported_keys(*, file_path: Path, parsed_header: dict[str, object]) -> None:
    unsupported_keys: tuple[str, ...] = tuple(
        key for key in parsed_header if key not in TEST_HEADER_SUPPORTED_KEYS
    )
    if unsupported_keys:
        raise SqlTestParseError(
            f"TEST() in '{file_path}' only supports `name` and `mode`; unsupported keys: "
            f"{', '.join(unsupported_keys)}"
        )


def _parse_name(*, file_path: Path, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SqlTestParseError(f"TEST() name in '{file_path}' must be a non-empty string")
    return value.strip()


def _parse_mode(*, file_path: Path, value: object) -> SqlTestMode:
    if value is None:
        return DEFAULT_SQL_TEST_MODE
    if not isinstance(value, str) or value not in {mode.value for mode in SqlTestMode}:
        raise SqlTestParseError(
            f"TEST() mode in '{file_path}' must be one of: {SUPPORTED_SQL_TEST_MODES}"
        )
    return SqlTestMode(value)
