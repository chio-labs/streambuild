from dataclasses import dataclass


@dataclass(frozen=True)
class RenderCreateTableDdlTestCase:
    description: str
    partition_by: str | None
    ttl: str | None
    settings: dict[str, str] | None
    expected_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]
