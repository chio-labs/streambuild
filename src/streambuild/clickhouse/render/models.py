"""Rendered ClickHouse DDL models."""

from dataclasses import dataclass

from streambuild.compiler.shared.models import ObjectKey


@dataclass(frozen=True)
class RenderedClickHouseDdl:
    """A rendered DDL statement paired with its desired object identity."""

    key: ObjectKey
    ddl: str
