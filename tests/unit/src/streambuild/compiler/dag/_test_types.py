from dataclasses import dataclass


@dataclass(frozen=True)
class DagArtifactTestCase:
    description: str
    expected_node_types: tuple[str, ...]
    expected_source_node_count: int
    expected_model_node_count: int
    expected_has_test_edge: bool
    expected_has_audit_edge: bool
    expected_has_typed_lineage_edge: bool
