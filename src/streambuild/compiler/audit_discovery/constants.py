"""Constants for SQL audit discovery."""

from __future__ import annotations

import re

ALLOWED_AUDIT_KEYS: frozenset[str] = frozenset(
    {"severity", "description", "name", "every", "warmup", "scheduled"}
)
ALLOWED_AUDIT_SEVERITIES: frozenset[str] = frozenset({"error", "warning"})
AUDIT_COLUMN_ARGUMENT_KEY: str = "column"
AUDIT_MODEL_ARGUMENT_KEY: str = "model"
AUDIT_SEVERITY_KEY: str = "severity"
AUDIT_EVERY_KEY: str = "every"
AUDIT_WARMUP_KEY: str = "warmup"
AUDIT_SCHEDULED_KEY: str = "scheduled"
DEFAULT_AUDIT_SEVERITY: str = "error"
WARNING_AUDIT_SEVERITY: str = "warning"
GENERIC_AUDIT_QUOTED_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"@'(?P<name>[A-Za-z_][A-Za-z0-9_]*)'"
)
GENERIC_AUDIT_RAW_PARAMETER_PATTERN: re.Pattern[str] = re.compile(
    r"@(?!')(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
)
