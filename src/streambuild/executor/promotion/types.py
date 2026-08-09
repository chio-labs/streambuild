"""Promotion lifecycle domain types."""

from enum import StrEnum


class PublishOperation(StrEnum):
    """Reason stable bindings were published."""

    PROMOTE = "promote"
    ROLLBACK = "rollback"


class PromotionPreviewClassification(StrEnum):
    """Conservative UI classification for a binding replacement request."""

    INITIAL_PUBLISH = "initial_publish"
    PROMOTION = "promotion"
