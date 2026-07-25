from dataclasses import dataclass


@dataclass(frozen=True)
class RenderCreateTableDdlTestCase:
    description: str
    include_partition_by: bool
    include_ttl: bool
    include_settings: bool
    expected_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...]
