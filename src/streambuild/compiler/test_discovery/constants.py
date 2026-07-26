"""Constants for SQL-native test discovery."""

from __future__ import annotations

import re

EXPECTED_CTE_PREFIX: str = "__expected__"
REF_CTE_PREFIX: str = "__ref__"
SOURCE_CTE_PREFIX: str = "__source__"
TEST_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*TEST\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)$",
    re.DOTALL,
)
TEST_HEADER_ONLY_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*TEST\s*\((?P<header>.*?)\)\s*;\s*",
    re.DOTALL | re.MULTILINE,
)
RESERVED_SQL_TEST_CTE_NAMES: frozenset[str] = frozenset(
    {
        "__actual",
        "__expected__typed",
        "__actual__projected",
        "__missing__",
        "__unexpected__",
    }
)

TEST_HEADER_NAME_KEY: str = "name"
CEREMONIAL_SELECT_LITERAL: str = "1"
