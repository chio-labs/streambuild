"""Kafka admin result models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConsumerGroupOffsetReset:
    """The durable outcome of one committed-offset reset ahead of a fresh landing table."""

    consumer_group: str
    landing_relation_name: str
    deleted: bool
    error: str | None
    notice: str | None
