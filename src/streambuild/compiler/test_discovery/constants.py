"""Constants for SQL-native test discovery."""

from __future__ import annotations

import re

from streambuild.compiler.test_discovery.types import SqlTestMode

EXPECTED_CTE_PREFIX: str = "__expected__"
REF_CTE_PREFIX: str = "__ref__"
SOURCE_CTE_PREFIX: str = "__source__"
ASSERT_CTE_PREFIX: str = "__assert__"
MACRO_ACTUAL_CTE_NAME: str = "__macro_actual__"
MACRO_EXPECTED_CTE_NAME: str = "__macro_expected__"
MACRO_TARGET_LABEL_PREFIX: str = "macro "
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
UNSUPPORTED_MODE_CTE_NAMES: frozenset[str] = frozenset(
    {
        "__udf_actual__",
        "__udf_expected__",
        "__table_fn_actual__",
        "__table_fn_expected__",
    }
)
UNSUPPORTED_MODE_CTE_PREFIXES: tuple[str, ...] = ("__macro__", "__seed__", "__dbt_ref__")
MODEL_MODE_CTE_PREFIXES: tuple[str, ...] = (
    REF_CTE_PREFIX,
    SOURCE_CTE_PREFIX,
    EXPECTED_CTE_PREFIX,
    ASSERT_CTE_PREFIX,
)

TEST_HEADER_NAME_KEY: str = "name"
TEST_HEADER_MODE_KEY: str = "mode"
TEST_HEADER_SUPPORTED_KEYS: frozenset[str] = frozenset({TEST_HEADER_NAME_KEY, TEST_HEADER_MODE_KEY})
DEFAULT_SQL_TEST_MODE: SqlTestMode = SqlTestMode.MODEL
SUPPORTED_SQL_TEST_MODES: str = ", ".join(mode.value for mode in SqlTestMode)
CEREMONIAL_SELECT_KEYWORD: str = "SELECT"
CEREMONIAL_SELECT_LITERAL: str = "1"
SQL_TEST_SCANNER_CONTEXT: str = "SQL test"
