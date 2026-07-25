from dataclasses import dataclass


@dataclass(frozen=True)
class RenderMetadataStateDdlTestCase:
    description: str
    expected_table_name: str
    expected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class MetadataStateInsertStatementTestCase:
    description: str
    expected_sql_fragment: str
    expected_row_count: int
    expected_first_row_fragments: tuple[tuple[str, object], ...]
