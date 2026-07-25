from dataclasses import dataclass


@dataclass(frozen=True)
class RenderCreateViewDdlTestCase:
    description: str
    database: str
    view_name: str
    target_table_name: str
    expected_fragments: tuple[str, ...]
