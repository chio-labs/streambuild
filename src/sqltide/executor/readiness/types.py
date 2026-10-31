"""Audit backfill domain types."""

from enum import StrEnum


class AuditAssessment(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    CAUTION = "caution"
