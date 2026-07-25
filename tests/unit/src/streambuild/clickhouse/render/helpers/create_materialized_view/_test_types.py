from dataclasses import dataclass


@dataclass(frozen=True)
class RenderCreateMaterializedViewDdlTestCase:
    description: str
    query: str
    expected_source_reference: str
    expected_target_reference: str
    expected_query_fragments: tuple[str, ...]
    expected_absent_fragments: tuple[str, ...] = ()
