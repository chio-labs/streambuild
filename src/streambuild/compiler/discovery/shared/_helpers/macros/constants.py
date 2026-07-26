"""Constants for authored Python SQL macros."""

import re

PROJECT_FILE_NAME: str = "streambuild_project.yml"
MACRO_DIRECTORY_NAME: str = "macros"
UNEXPANDED_MACRO_PATTERN: re.Pattern[str] = re.compile(r"@[A-Za-z_][A-Za-z0-9_]*\s*\(")

DOUBLE_QUOTE: str = '"'
SINGLE_QUOTE: str = "'"
BACKTICK: str = "`"
PYTHON_LITERAL_NAMES: frozenset[str] = frozenset({"True", "False", "None"})
