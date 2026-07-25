"""Constants for SQL audit discovery."""

from __future__ import annotations

import re

AUDIT_HEADER_PATTERN: re.Pattern[str] = re.compile(
    r"^\s*AUDIT\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*)$",
    re.DOTALL,
)
AUDIT_BLOCK_PATTERN: re.Pattern[str] = re.compile(
    r"AUDIT\s*\((?P<header>.*?)\)\s*;\s*(?P<sql>.*?)(?=\n\s*AUDIT\s*\(|\Z)",
    re.DOTALL,
)
ALLOWED_AUDIT_KEYS: frozenset[str] = frozenset({"severity", "description", "name"})
ALLOWED_AUDIT_SEVERITIES: frozenset[str] = frozenset({"error", "warning"})
GENERIC_AUDIT_QUOTED_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"@'(?P<name>[A-Za-z_][A-Za-z0-9_]*)'"
)
GENERIC_AUDIT_RAW_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"@(?!')(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)
