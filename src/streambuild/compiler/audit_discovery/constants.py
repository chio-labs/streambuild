"""Constants for SQL audit discovery."""

from __future__ import annotations

import re

ALLOWED_AUDIT_KEYS: frozenset[str] = frozenset({"severity", "description", "name"})
ALLOWED_AUDIT_SEVERITIES: frozenset[str] = frozenset({"error", "warning"})
GENERIC_AUDIT_QUOTED_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"@'(?P<name>[A-Za-z_][A-Za-z0-9_]*)'"
)
GENERIC_AUDIT_RAW_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"@(?!')(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)
