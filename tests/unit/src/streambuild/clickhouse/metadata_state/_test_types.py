from dataclasses import dataclass


@dataclass(frozen=True)
class RenderMetadataStateDdlTestCase:
    description: str
    statement_index: int
    expected_sql: str


@dataclass(frozen=True)
class MetadataStateInsertStatementTestCase:
    description: str
    statement_index: int
    expected_sql: str
    expected_row: dict[str, object]
